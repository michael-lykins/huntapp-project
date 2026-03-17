from abc import ABC, abstractmethod
from typing import Optional, Dict

class VisionProvider(ABC):
    @abstractmethod
    def describe(self, *, image_bytes: bytes, prompt_hint: Optional[str] = None) -> Dict:
        """
        Return: {
          "has_animal": bool,
          "species": str|None,
          "sex": "male"|"female"|"unknown",
          "age_estimate": "fawn"|"yearling"|"2.5"|"3.5+"|"unknown",
          "confidence": float,  # 0..1
          "notes": str|None
        }
        """
        raise NotImplementedError
