from typing import Any, Dict, List, Optional, Tuple, Protocol

class Search(Protocol):
    def index_trailcam(self, doc: Dict[str, Any]) -> Dict[str, Any]: ...
    def query_images(
        self,
        q: Optional[str],
        start: Optional[str],
        end: Optional[str],
        bbox: Optional[Tuple[float,float,float,float]],
        size: int,
    ) -> List[Dict[str, Any]]: ...
    def index_event_pin(self, doc: Dict[str, Any]) -> Dict[str, Any]: ...
    def index_geo_track(self, doc: Dict[str, Any]) -> Dict[str, Any]: ...
