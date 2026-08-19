import numpy as np
import pytest
from aic2026.retrieval.asr_bge_index import (
    BGE_DENSE_DIMENSION,
    BGE_MODEL_ID,
    encode_texts_bge_m3,
)


@pytest.fixture(scope="module")
def bge_model_and_tok():
    try:
        from transformers import AutoModel, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(BGE_MODEL_ID)
        mod = AutoModel.from_pretrained(BGE_MODEL_ID)
        mod.eval()
        return mod, tok
    except Exception as e:
        pytest.skip(f"Cannot load BGE-M3 model: {e}")


def test_bge_model_constants():
    assert BGE_MODEL_ID == "BAAI/bge-m3"
    assert BGE_DENSE_DIMENSION == 1024


def test_encode_texts_dense_contract(bge_model_and_tok):
    model, tokenizer = bge_model_and_tok
    texts = [
        "giá xăng dầu hôm nay",
        "kỳ thi tốt nghiệp trung học phổ thông",
        "thành phố Hồ Chí Minh",
    ]
    vecs = encode_texts_bge_m3(texts, model=model, tokenizer=tokenizer, batch_size=2)
    assert vecs.shape == (3, 1024)
    assert vecs.dtype == np.float32
    assert np.isfinite(vecs).all()

    # Norm validation
    norms = np.linalg.norm(vecs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-4)


def test_empty_texts_handling(bge_model_and_tok):
    model, tokenizer = bge_model_and_tok
    vecs = encode_texts_bge_m3([], model=model, tokenizer=tokenizer)
    assert vecs.shape == (0, 1024)
    assert vecs.dtype == np.float32
