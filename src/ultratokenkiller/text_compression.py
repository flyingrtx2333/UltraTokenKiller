"""Locally scored extractive text selection; no generative model calls."""
import re
from functools import lru_cache

from .assets import model_directory, verify_assets


@lru_cache(maxsize=2)
def load_encoder(directory: str):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    from pathlib import Path
    root = Path(directory)
    if not verify_assets(root.parents[1]):
        raise RuntimeError("Pinned text model assets are not verified")
    tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=256)
    tokenizer.enable_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    encoder = ort.InferenceSession(str(root / "onnx/model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
    return tokenizer, encoder


def summarize_text(text: str, query: str, home=None, aggressive=False) -> str:
    import numpy as np
    if not query or re.search(r"[\u3400-\u9fff]", text+query):
        return text  # Frozen encoder is English; do not claim multilingual semantic parity.
    chunks = re.split(r"(?<=\n)\n+|(?<=[.!?])\s+(?=[A-Z])", text)
    if len(chunks) < 8 or len(chunks) > 256 or any(len(chunk) > 2000 for chunk in chunks):
        return text
    tokenizer, model = load_encoder(str(model_directory(home)))
    vectors = []
    items = [query]+chunks
    names = {entry.name for entry in model.get_inputs()}
    for offset in range(0, len(items), 16):
        encoded = tokenizer.encode_batch(items[offset:offset+16])
        ids = np.array([item.ids for item in encoded], dtype=np.int64)
        mask = np.array([item.attention_mask for item in encoded], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.array([item.type_ids for item in encoded], dtype=np.int64)
        states = model.run(None, feed)[0]
        pooled = (states*mask[..., None]).sum(1)/np.maximum(mask.sum(1)[:, None], 1)
        pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        vectors.extend(pooled)
    query_vector = vectors[0]
    scores = [float(query_vector @ vector) for vector in vectors[1:]]
    keep = {0, len(chunks)-1}
    # Preserve headings, facts, negations, code, paths and explicit uncertainty independently of similarity.
    protected = re.compile(r"\d|\b(?:not|never|no|must|unless|except|may|might|unknown|error|failed|warning)\b|[/\\]|`|^#", re.I)
    keep.update(i for i, chunk in enumerate(chunks) if protected.search(chunk))
    count = max(2, int(len(chunks)*(.35 if aggressive else .6)))
    keep.update(sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:count])
    return "\n\n".join(chunk if i in keep else "[UTK: passage omitted]" for i, chunk in enumerate(chunks))
