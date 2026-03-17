import base64, os, json, requests
from typing import Optional, Dict
from .vision_provider import VisionProvider

class OpenAIVision(VisionProvider):
    def __init__(self, model: Optional[str] = None):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.model = model or os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
        self.endpoint = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")

    def describe(self, *, image_bytes: bytes, prompt_hint: Optional[str] = None) -> Dict:
        img_b64 = base64.b64encode(image_bytes).decode("utf-8")
        system_prompt = (
            "You are a wildlife identification assistant for trail-camera images. "
            "Return STRICT JSON: has_animal(bool), species(null|string), "
            "sex(male|female|unknown), age_estimate(fawn|yearling|2.5|3.5+|unknown), "
            "confidence(0..1), notes(short string)."
        )
        user_prompt = prompt_hint or "Analyze the image. If unsure, use 'unknown' and lower confidence."

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        r = requests.post(self.endpoint, json=payload, headers=headers, timeout=90)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content) if isinstance(content, str) else content
