from __future__ import annotations

import json
from pathlib import Path


def test_asr_worker_notebook_is_valid_and_sequential() -> None:
    path = Path("notebooks/asr_whisper_medium_worker.ipynb")
    notebook = json.loads(path.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["cells"]
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    for index, cell in enumerate(code_cells):
        compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    assert "NUM_SHARDS = 2" in source
    assert "SHARD_INDEX = 0 if WORKER == \"colab\" else 1" in source
    assert "--limit-videos" in source
    assert "validate-asr-shard" in source
    assert "make_archive" in source
