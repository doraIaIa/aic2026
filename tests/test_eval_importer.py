import json

import pytest

from aic2026.core.hashing import sha256_file
from aic2026.evaluation.contract import EvalContractError
from aic2026.evaluation.importers import import_combined_queries, parse_combined_queries


def _combined(count: int) -> str:
    types = ("trake", "kis", "qa")
    return "\n".join(
        f"===== query-p3-{index}-{types[(index - 1) % 3]}.txt =====\n"
        f"Nội dung query {index}\nDòng thứ hai {index}\n"
        for index in range(1, count + 1)
    )


def test_parse_combined_queries_preserves_text_order_and_type():
    queries = parse_combined_queries(_combined(3), expected_count=3)
    assert [query["query_id"] for query in queries] == [
        "query-p3-1-trake", "query-p3-2-kis", "query-p3-3-qa"
    ]
    assert [query["query_type"] for query in queries] == ["TRAKE", "KIS", "QA"]
    assert queries[0]["query_text"] == "Nội dung query 1\nDòng thứ hai 1"
    assert all(query["label_status"] == "unlabeled_reference" for query in queries)
    assert all(query["trap_category"] == "unclassified" for query in queries)


def test_import_combined_queries_writes_valid_provenance(tmp_path):
    source = tmp_path / "combined.txt"
    source.write_text(_combined(3), encoding="utf-8")
    output = tmp_path / "eval.json"
    dataset, summary = import_combined_queries(
        source,
        output,
        dataset_id="group-a",
        dataset_version="v1",
        source_relpath="inputs/combined.txt",
        expected_sha256=sha256_file(source),
        expected_count=3,
    )
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert persisted == dataset
    assert summary["total"] == 3 and summary["labeled"] == 0
    assert dataset["source_provenance"]["source_relpath"] == "inputs/combined.txt"
    assert dataset["source_provenance"]["source_sha256"] == sha256_file(source)
    assert dataset["source_provenance"]["parser_version"] == "group-a-combined-v1"


def test_import_combined_queries_fails_closed_on_checksum_and_sequence(tmp_path):
    source = tmp_path / "combined.txt"
    source.write_text(_combined(3), encoding="utf-8")
    with pytest.raises(EvalContractError, match="Checksum nguồn không khớp"):
        import_combined_queries(
            source, tmp_path / "out.json", dataset_id="x", dataset_version="v1",
            expected_sha256="0" * 64, expected_count=3,
        )
    malformed = _combined(3).replace("query-p3-2-kis", "query-p3-4-kis")
    with pytest.raises(EvalContractError, match="Thứ tự query"):
        parse_combined_queries(malformed, expected_count=3)
