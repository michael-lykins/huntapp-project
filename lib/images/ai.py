import torch, numpy as np
import PIL.Image as PImage
import open_clip
import io

_PROMPTS = [
    ("buck", "a wildlife photo of a whitetail buck with antlers, outdoors"),
    ("doe",  "a wildlife photo of a whitetail doe without antlers"),
    ("fawn", "a wildlife photo of a whitetail fawn"),
    ("none", "a wildlife photo without any deer")
]

class CLIPModel:
    _model = None
    _preprocess = None
    _tokenizer = None
    _device = "cpu"

    @classmethod
    def load(cls):
        if cls._model is None:
            model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
            tokenizer = open_clip.get_tokenizer("ViT-B-32")
            cls._model = model.eval()
            cls._preprocess = preprocess
            cls._tokenizer = tokenizer
            cls._device = "cuda" if torch.cuda.is_available() else "cpu"
            cls._model.to(cls._device)
        return cls._model, cls._preprocess, cls._tokenizer, cls._device

def image_embedding_and_scores(raw: bytes):
    model, preprocess, tok, device = CLIPModel.load()
    img = PImage.open(io.BytesIO(raw)).convert("RGB")
    img_t = preprocess(img).unsqueeze(0).to(device)
    # embed image
    with torch.no_grad():
        img_feat = model.encode_image(img_t)
        img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
    embedding = img_feat.squeeze(0).cpu().numpy().astype(np.float32)

    # zero-shot scores
    texts = tok([p[1] for p in _PROMPTS]).to(device)
    with torch.no_grad():
        txt_feat = model.encode_text(texts)
        txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
        sims = (img_feat @ txt_feat.T).softmax(dim=-1).squeeze(0).cpu().numpy()  # probabilities

    scores = {k: float(sims[i]) for i, (k, _) in enumerate(_PROMPTS)}
    deer_kind = max(["buck","doe","fawn","none"], key=lambda k: scores[k])
    contains_deer = deer_kind != "none"
    # crude age bucket heuristic
    if deer_kind == "fawn":
        age_bucket = "fawn"
    elif deer_kind == "buck":
        age_bucket = "mature" if scores["buck"] > 0.65 else "young"
    else:
        age_bucket = "unknown"
    return embedding, contains_deer, deer_kind if contains_deer else "unknown", age_bucket, scores
