from typing import Any, Dict, List, Optional, Tuple
from elasticsearch import Elasticsearch
from .config import SearchConfig

class ElasticSearchService:
    def __init__(self, cfg: SearchConfig):
        self.cfg = cfg
        self.es = Elasticsearch(
            hosts=[cfg.host],
            api_key=cfg.api_key,
            request_timeout=30,
        )

    # Some users deploy images into a data stream, others into time-suffixed indices;
    # search both patterns safely.
    def _image_indices(self) -> List[str]:
        return [self.cfg.images_index, f"{self.cfg.images_index}-*", "hunt-images-*"]

    def index_trailcam(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        # Keep “Elastic stuff” server-side: we just send a canonical doc.
        # Your serverless templates/pipelines can map/transform.
        return self.es.index(index=self.cfg.images_index, document=doc)

    def query_images(
        self,
        q: Optional[str],
        start: Optional[str],
        end: Optional[str],
        bbox: Optional[Tuple[float,float,float,float]],
        size: int,
    ) -> List[Dict[str, Any]]:
        must: List[dict] = []
        filt: List[dict] = []

        if start or end:
            rng = {}
            if start: rng["gte"] = start
            if end:   rng["lte"] = end
            filt.append({"range": {"@timestamp": rng}})

        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            # Try both field shapes commonly seen in your docs
            filt.append({
                "bool": {
                    "should": [
                        {"geo_bounding_box": {
                            "location": {
                                "top_left":     {"lat": max_lat, "lon": min_lon},
                                "bottom_right": {"lat": min_lat, "lon": max_lon},
                            }
                        }},
                        {"geo_bounding_box": {
                            "camera.location": {
                                "top_left":     {"lat": max_lat, "lon": min_lon},
                                "bottom_right": {"lat": min_lat, "lon": max_lon},
                            }
                        }},
                    ],
                    "minimum_should_match": 1
                }
            })

        if q:
            must.append({
                "multi_match": {
                    "query": q,
                    "fields": [
                        "labels^2", "labels.user^2", "species",
                        "camera_id", "camera.id", "camera.model", "camera.make"
                    ],
                }
            })

        body = {
            "query": {"bool": {"must": must, "filter": filt}},
            "size": size,
            "sort": [{"@timestamp": "desc"}],
        }

        res = self.es.search(
            index=self._image_indices(),
            body=body,
            ignore_unavailable=True,
            allow_no_indices=True,
        )

        items: List[Dict[str, Any]] = []
        for h in res.get("hits", {}).get("hits", []):
            s = h.get("_source", {})
            # Normalize common fields for UI
            items.append({
                "id": h.get("_id"),
                "timestamp": s.get("@timestamp"),
                "url": s.get("image_url") or s.get("media", {}).get("url"),
                "location": s.get("location") or s.get("camera", {}).get("location"),
                "labels": s.get("labels") or s.get("labels", {}).get("user"),
                "camera_id": s.get("camera_id") or s.get("camera", {}).get("id"),
            })
        return items

    def index_event_pin(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return self.es.index(index=self.cfg.events_index, document=doc)

    def index_geo_track(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        return self.es.index(index=self.cfg.tracks_index, document=doc)
