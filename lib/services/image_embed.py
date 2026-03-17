import io
import torch
import open_clip
from PIL import Image

_MODEL = None
_PRE = None

def _load():
    global _MODEL, _PRE
    if _MODEL is None:
        _MODEL, _, _PRE = open_clip.create_model_and_transforms(
            "ViT-B-32", pretrained="laion2b_s34b_b79k"
        )
        _MODEL.eval()

@torch.inference_mode()
def embed_image_bytes(image_bytes: bytes) -> list:
    _load()
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    t = _PRE(img).unsqueeze(0)
    feats = _MODEL.encode_image(t)
    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats[0].cpu().numpy().tolist()  # len=512
