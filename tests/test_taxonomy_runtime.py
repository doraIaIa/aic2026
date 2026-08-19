from __future__ import annotations

import json
from pathlib import Path
import pytest

from aic2026.data_hub.models import VideoRecord, VideoSpace
from aic2026.data_hub.taxonomy_builder import TaxonomyBuilder
from aic2026.data_hub.taxonomy_models import (
    TaxonomyNodeRecord,
    TaxonomySpace,
    VideoMembershipRecord,
)
from aic2026.data_hub.video_registry import VideoRegistry


def _mock_video_registry(n_videos: int = 873) -> VideoRegistry:
    series_dist = {
        "L21": 29, "L22": 31, "L23": 25, "L24": 43, "L25": 88,
        "L26": 498, "L27": 16, "L28": 24, "L29": 23, "L30": 96,
    }
    records = []
    ordinal = 0
    for s_id, count in sorted(series_dist.items()):
        for idx in range(1, count + 1):
            vid = f"{s_id}_V{idx:03d}"
            records.append(
                VideoRecord(
                    video_id=vid,
                    ordinal=ordinal,
                    ordinal_space_id="v1_natural_series_video",
                    series=s_id,
                    source_relpath=f"videos/{s_id}/{vid}.mp4",
                    duration_ms=60000,
                    duration_sec=60.0,
                    fps=25.0,
                    width=1280,
                    height=720,
                )
            )
            ordinal += 1

    space = VideoSpace(
        video_space_id="canonical_universe_v1",
        schema_version="v1",
        video_count=len(records),
        ordering_rule="natural_sort_series_video_asc",
        catalog_checksum="test_checksum",
        created_at="2026-08-19T00:00:00Z",
        series_counts=series_dist,
    )
    return VideoRegistry(records=records, video_space=space)



def test_taxonomy_nodes_deterministic():
    reg = _mock_video_registry()
    builder = TaxonomyBuilder(video_registry=reg)
    nodes = builder.build_nodes()

    # 9 Program nodes + 9 Subject nodes = 18 nodes
    assert len(nodes) == 18

    node_dict = {n.branch_id: n for n in nodes}
    assert "program/news" in node_dict
    assert "program/sports/cycling" in node_dict
    assert "program/cultural-performance/lion-dragon-dance" in node_dict
    assert "program/education/exam-prep" in node_dict
    assert "program/cooking/demonstration" in node_dict
    assert "program/travel-experience" in node_dict
    assert "program/documentary/mekong-history-geography" in node_dict
    assert "program/documentary/mekong-people-culture-environment" in node_dict
    assert "program/positive-community-local-life-feature" in node_dict

    assert "subject/education/literature" in node_dict
    assert "subject/education/history" in node_dict
    assert "subject/education/biology" in node_dict
    assert "subject/education/chemistry" in node_dict
    assert "subject/education/physics" in node_dict
    assert "subject/education/english" in node_dict
    assert "subject/education/geography" in node_dict
    assert "subject/education/mathematics" in node_dict
    assert "subject/education/economics-law" in node_dict


def test_taxonomy_memberships_cardinality_and_status(tmp_path: Path):
    reg = _mock_video_registry()
    builder = TaxonomyBuilder(video_registry=reg)

    nodes, memberships, space = builder.materialize(tmp_path)

    # Validate node & membership files
    assert (tmp_path / "taxonomy_nodes.jsonl").exists()
    assert (tmp_path / "video_memberships.jsonl").exists()
    assert (tmp_path / "taxonomy_space.json").exists()

    program_m = [m for m in memberships if m.membership_type == "PRIMARY_PROGRAM"]
    subject_m = [m for m in memberships if m.membership_type == "SUBJECT"]

    assert len(program_m) == 873
    assert len(subject_m) == 88
    assert len(memberships) == 873 + 88

    # Status distribution
    status_counts = {"VERIFIED": 0, "INFERRED": 0, "OUTLIER": 0}
    for m in program_m:
        status_counts[m.status] += 1

    assert status_counts == {"VERIFIED": 833, "INFERRED": 39, "OUTLIER": 1}

    # Verify L30_V096 is OUTLIER
    l30_096 = [m for m in program_m if m.video_id == "L30_V096"][0]
    assert l30_096.status == "OUTLIER"
    assert l30_096.branch_id == "program/positive-community-local-life-feature"

    # Verify L30_V029 is INFERRED
    l30_029 = [m for m in program_m if m.video_id == "L30_V029"][0]
    assert l30_029.status == "INFERRED"

    # Program branch counts
    program_counts = space.program_counts
    assert program_counts == {
        "program/news": 60,
        "program/sports/cycling": 25,
        "program/cultural-performance/lion-dragon-dance": 43,
        "program/education/exam-prep": 88,
        "program/cooking/demonstration": 498,
        "program/travel-experience": 16,
        "program/documentary/mekong-history-geography": 24,
        "program/documentary/mekong-people-culture-environment": 23,
        "program/positive-community-local-life-feature": 96,
    }


def test_l25_subject_memberships(tmp_path: Path):
    reg = _mock_video_registry()
    builder = TaxonomyBuilder(video_registry=reg)
    _, memberships, _ = builder.materialize(tmp_path)

    subject_m = [m for m in memberships if m.membership_type == "SUBJECT"]
    assert len(subject_m) == 88

    subj_counts = {}
    for m in subject_m:
        assert m.video_id.startswith("L25_")
        assert m.status == "VERIFIED"
        subj_counts[m.branch_id] = subj_counts.get(m.branch_id, 0) + 1

    assert subj_counts["subject/education/literature"] == 10
    assert subj_counts["subject/education/history"] == 10
    assert subj_counts["subject/education/biology"] == 10
    assert subj_counts["subject/education/chemistry"] == 10
    assert subj_counts["subject/education/physics"] == 10
    assert subj_counts["subject/education/english"] == 10
    assert subj_counts["subject/education/geography"] == 10
    assert subj_counts["subject/education/mathematics"] == 10
    assert subj_counts["subject/education/economics-law"] == 8
