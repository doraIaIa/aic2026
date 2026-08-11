from __future__ import annotations

import json

from aic2026.cli import main


def test_asr_cli_contract_errors_return_nonzero(tmp_path, capsys) -> None:
    assert main([
        "split-asr-shards",
        "--manifest", str(tmp_path / "missing.jsonl"),
        "--num-shards", "4",
        "--out-dir", str(tmp_path / "shards"),
    ]) == 2
    assert "REJECTED" in capsys.readouterr().out

    assert main([
        "validate-asr-shard", "--artifact-dir", str(tmp_path / "missing-artifact"),
    ]) == 3
    assert '"valid": false' in capsys.readouterr().out

    malformed = tmp_path / "segments.jsonl"
    malformed.write_text(json.dumps({
        "segment_id": "bad", "video_id": "V1", "start_sec": 5, "end_sec": 4, "text": "x",
    }) + "\n", encoding="utf-8")
    assert main([
        "build-asr-fts", "--segments", str(malformed), "--out", str(tmp_path / "fts"),
    ]) == 2
    assert "REJECTED" in capsys.readouterr().out
