from typing import Optional, Dict
from .vision_provider import VisionProvider

class LocalZeroVision(VisionProvider):
    def describe(self, *, image_bytes: bytes, prompt_hint: Optional[str] = None) -> Dict:
        return {
            "has_animal": False, "species": None, "sex": "unknown",
            "age_estimate": "unknown", "confidence": 0.0, "notes": "Local placeholder"
        }
