import json

from aic2026.cli import main


def test_validate_eval_dataset_cli_exit_codes(tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")
    assert main(["validate-eval-dataset", "--dataset", str(invalid)]) == 2
    assert '"valid": false' in capsys.readouterr().out

    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_id": "unlabeled-reference",
                "dataset_version": "v1",
                "queries": [
                    {
                        "query_id": "q1",
                        "query_type": "KIS",
                        "query_text": "query chưa có nhãn",
                        "question_text": None,
                        "trap_category": "visual",
                        "split": "dev",
                        "label_status": "unlabeled_reference",
                        "gt_video_id": None,
                        "gt_frame_ranges": [],
                        "gt_answer": None,
                        "label_provenance": None,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert main(["validate-eval-dataset", "--dataset", str(valid)]) == 0
    output = capsys.readouterr().out
    assert "BLOCKED_BY_GROUND_TRUTH" in output


def test_eval_summary_cli_rejects_missing_artifact(tmp_path):
    assert main(["eval-summary", "--run-dir", str(tmp_path / "missing")]) == 3
