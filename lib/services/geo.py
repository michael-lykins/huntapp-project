import math
from typing import List, Optional, Dict, Any, Tuple

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlmb/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def nearest_waypoint(lat: float, lon: float, waypoints: List[Dict[str, Any]], max_m: float = 150.0) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    best = None
    best_d = float("inf")
    for w in waypoints:
        d = haversine_m(lat, lon, w["lat"], w["lon"])
        if d < best_d:
            best, best_d = w, d
    if best is None or best_d > max_m:
        return None, None
    return best, best_d
