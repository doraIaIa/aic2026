"""Unit test for Media Inspector Benchmark execution."""
from __future__ import annotations

import pytest
from aic2026.evaluation.media_inspector_benchmark import run_media_inspector_benchmark


def test_media_inspector_benchmark_execution():
    res = run_media_inspector_benchmark(run_id="test_run_m9")
    assert res["benchmark_id"] == "test_run_m9"
    assert res["range_checks"]["passed"] >= 3
    assert res["nearest_keyframe_probes"]["passed"] >= 20
    assert res["exact_frame_cases"]["passed"] >= 24
    assert res["exact_frame_cases"]["pixel_checks_passed"] >= 12
    assert res["quality_classification"] == "MEDIA_CORRECTNESS_FUNCTIONAL"
