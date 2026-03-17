from typing import Optional, Dict
from .image_embed import embed_image_bytes
from .vision_provider_openai import OpenAIVision
from .vision_provider_local_zero import LocalZeroVision

async def _provider():
    import os
    return OpenAIVision() if os.getenv("OPENAI_API_KEY") else LocalZeroVision()

async def analyze_bytes(image_bytes: bytes, *, prompt_hint: Optional[str] = None) -> Dict:
    provider = await _provider()
    description = provider.describe(image_bytes=image_bytes, prompt_hint=prompt_hint)
    vector = embed_image_bytes(image_bytes)
    return {"analysis": description, "embedding": vector}
