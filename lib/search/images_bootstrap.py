from elasticsearch import Elasticsearch

IMAGES_INDEX = "images-v1"

MAPPING = {
    "mappings": {
        "properties": {
            "image_id": {"type": "keyword"},
            "s3_key": {"type": "keyword"},
            "sha256": {"type": "keyword"},
            "ingested_at": {"type": "date"},
            "source_type": {"type": "keyword"},  # trail_camera | cell_phone | digital_camera
            "timestamp": {"type": "date"},
            "gps": {"type": "geo_point"},
            "camera_make": {"type": "keyword"},
            "camera_model": {"type": "keyword"},
            # trail-cam extras (extend as needed)
            "trail": {
                "properties": {
                    "camera_id": {"type": "keyword"},
                    "manufacturer": {"type": "keyword"},
                    "temperature_c": {"type": "float"},
                    "moon_phase": {"type": "keyword"},
                    "trigger": {"type": "keyword"},  # motion | time-lapse | unknown
                    "exposure": {"type": "keyword"}
                }
            },
            # AI signals
            "ai": {
                "properties": {
                    "contains_deer": {"type": "boolean"},
                    "deer_kind": {"type": "keyword"},  # buck | doe | fawn | unknown
                    "age_bucket": {"type": "keyword"}, # fawn | yearling | young | mature | unknown
                    "scores": {
                        "properties": {
                            "buck": {"type": "float"},
                            "doe": {"type": "float"},
                            "fawn": {"type": "float"},
                            "none": {"type": "float"}
                        }
                    }
                }
            },
            # Vector for ANN search (ViT-B/32 => 512 dims)
            "embedding": {
                "type": "dense_vector",
                "dims": 512,
                "index": True,
                "similarity": "cosine"
            }
        }
    }
}

def ensure_index(es: Elasticsearch):
    if not es.indices.exists(index=IMAGES_INDEX):
        es.indices.create(index=IMAGES_INDEX, **MAPPING)
