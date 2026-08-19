from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

from aic2026.data_hub.taxonomy_models import (
    TaxonomyNodeRecord,
    TaxonomySpace,
    VideoMembershipRecord,
)
from aic2026.data_hub.video_registry import VideoRegistry


# Explicit verified mappings for L24
_L24_DIRECT_VERIFIED: Set[str] = {
    "L24_V002",
    "L24_V003",
    "L24_V004",
    "L24_V012",
    "L24_V017",
}

# Explicit verified mappings for L25 Subjects
_L25_SUBJECT_MAPPINGS: Dict[str, List[str]] = {
    "subject/education/literature": [
        "L25_V001", "L25_V010", "L25_V018", "L25_V027", "L25_V036",
        "L25_V045", "L25_V054", "L25_V063", "L25_V080", "L25_V081",
    ],
    "subject/education/history": [
        "L25_V002", "L25_V011", "L25_V019", "L25_V028", "L25_V037",
        "L25_V046", "L25_V055", "L25_V064", "L25_V072", "L25_V082",
    ],
    "subject/education/biology": [
        "L25_V003", "L25_V012", "L25_V020", "L25_V029", "L25_V038",
        "L25_V047", "L25_V056", "L25_V065", "L25_V073", "L25_V083",
    ],
    "subject/education/chemistry": [
        "L25_V004", "L25_V013", "L25_V021", "L25_V030", "L25_V039",
        "L25_V048", "L25_V057", "L25_V066", "L25_V074", "L25_V084",
    ],
    "subject/education/physics": [
        "L25_V005", "L25_V014", "L25_V022", "L25_V031", "L25_V040",
        "L25_V049", "L25_V058", "L25_V067", "L25_V077", "L25_V085",
    ],
    "subject/education/english": [
        "L25_V006", "L25_V015", "L25_V023", "L25_V032", "L25_V041",
        "L25_V050", "L25_V059", "L25_V068", "L25_V075", "L25_V086",
    ],
    "subject/education/geography": [
        "L25_V007", "L25_V016", "L25_V024", "L25_V033", "L25_V042",
        "L25_V051", "L25_V060", "L25_V069", "L25_V076", "L25_V087",
    ],
    "subject/education/mathematics": [
        "L25_V008", "L25_V017", "L25_V025", "L25_V034", "L25_V043",
        "L25_V052", "L25_V061", "L25_V070", "L25_V078", "L25_V088",
    ],
    "subject/education/economics-law": [
        "L25_V009", "L25_V026", "L25_V035", "L25_V044", "L25_V053",
        "L25_V062", "L25_V071", "L25_V079",
    ],
}


class TaxonomyBuilder:
    """Deterministic materializer for Program V1 and L25 Subject taxonomy."""

    def __init__(self, video_registry: VideoRegistry) -> None:
        self.video_registry = video_registry

    def build_nodes(self) -> List[TaxonomyNodeRecord]:
        """Build Program V1 and L25 Subject flat taxonomy graph nodes."""
        nodes = [
            # Program Nodes
            TaxonomyNodeRecord(
                branch_id="program/news",
                branch_type="PROGRAM",
                label_vi="Bản tin / Thời sự",
                label_en="News Broadcast",
                aliases=["60 giây", "thời sự", "bản tin"],
                requires_region_index=True,
            ),
            TaxonomyNodeRecord(
                branch_id="program/sports/cycling",
                branch_type="PROGRAM",
                label_vi="Thể thao / Đua xe đạp",
                label_en="Sports / Cycling Broadcast",
                parent_ids=["program/sports"],
                aliases=["đua xe đạp", "áo vàng", "chặng đua"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/cultural-performance/lion-dragon-dance",
                branch_type="PROGRAM",
                label_vi="Biểu diễn văn hóa / Lân Sư Rồng",
                label_en="Cultural Performance / Lion & Dragon Dance",
                parent_ids=["program/cultural-performance"],
                aliases=["lân sư rồng", "múa lân", "mai hoa thung"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/education/exam-prep",
                branch_type="PROGRAM",
                label_vi="Giáo dục / Ôn thi THPT",
                label_en="Education / Exam Preparation",
                parent_ids=["program/education"],
                aliases=["ôn thi", "bài giảng", "thpt", "bí quyết ôn thi"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/cooking/demonstration",
                branch_type="PROGRAM",
                label_vi="Ẩm thực / Hướng dẫn nấu ăn",
                label_en="Cooking / Culinary Demonstration",
                parent_ids=["program/cooking"],
                aliases=["món ngon mỗi ngày", "nấu ăn", "ẩm thực"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/travel-experience",
                branch_type="PROGRAM",
                label_vi="Du lịch / Trải nghiệm địa phương",
                label_en="Travel / Local Experience",
                aliases=["du lịch", "trải nghiệm", "văn hóa địa phương"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/documentary/mekong-history-geography",
                branch_type="PROGRAM",
                label_vi="Ký sự / Mê Kông Lịch sử & Địa lý",
                label_en="Documentary / Mekong History & Geography",
                parent_ids=["program/documentary"],
                aliases=["ký sự mê kông", "sông mê kông", "lịch sử địa lý"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/documentary/mekong-people-culture-environment",
                branch_type="PROGRAM",
                label_vi="Ký sự / Mê Kông Con người & Môi trường",
                label_en="Documentary / Mekong People, Culture & Environment",
                parent_ids=["program/documentary"],
                aliases=["ký sự mê kông", "con người", "môi trường", "sinh thái"],
            ),
            TaxonomyNodeRecord(
                branch_id="program/positive-community-local-life-feature",
                branch_type="PROGRAM",
                label_vi="Đời sống / Gương nhân ái & Đời sống địa phương",
                label_en="Life / Positive Community & Local Life Feature",
                aliases=["người tốt việc tốt", "gương nhân ái", "đời sống", "lan tỏa năng lượng tích cực"],
            ),
            # L25 Subject Nodes
            TaxonomyNodeRecord(
                branch_id="subject/education/literature",
                branch_type="SUBJECT",
                label_vi="Môn Ngữ văn",
                label_en="Subject / Literature",
                parent_ids=["program/education/exam-prep"],
                aliases=["ngữ văn", "văn học"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/history",
                branch_type="SUBJECT",
                label_vi="Môn Lịch sử",
                label_en="Subject / History",
                parent_ids=["program/education/exam-prep"],
                aliases=["lịch sử", "sử"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/biology",
                branch_type="SUBJECT",
                label_vi="Môn Sinh học",
                label_en="Subject / Biology",
                parent_ids=["program/education/exam-prep"],
                aliases=["sinh học", "sinh"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/chemistry",
                branch_type="SUBJECT",
                label_vi="Môn Hóa học",
                label_en="Subject / Chemistry",
                parent_ids=["program/education/exam-prep"],
                aliases=["hóa học", "hóa"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/physics",
                branch_type="SUBJECT",
                label_vi="Môn Vật lý",
                label_en="Subject / Physics",
                parent_ids=["program/education/exam-prep"],
                aliases=["vật lý", "lý"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/english",
                branch_type="SUBJECT",
                label_vi="Môn Tiếng Anh",
                label_en="Subject / English",
                parent_ids=["program/education/exam-prep"],
                aliases=["tiếng anh", "ngoại ngữ"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/geography",
                branch_type="SUBJECT",
                label_vi="Môn Địa lý",
                label_en="Subject / Geography",
                parent_ids=["program/education/exam-prep"],
                aliases=["địa lý", "địa"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/mathematics",
                branch_type="SUBJECT",
                label_vi="Môn Toán học",
                label_en="Subject / Mathematics",
                parent_ids=["program/education/exam-prep"],
                aliases=["toán học", "toán"],
            ),
            TaxonomyNodeRecord(
                branch_id="subject/education/economics-law",
                branch_type="SUBJECT",
                label_vi="Môn Giáo dục Kinh tế & Pháp luật",
                label_en="Subject / Economics & Law",
                parent_ids=["program/education/exam-prep"],
                aliases=["kinh tế pháp luật", "ktpl", "kinh tế và pháp luật"],
            ),
        ]
        return nodes

    def build_memberships(self) -> List[VideoMembershipRecord]:
        """Build audited video memberships across all 873 canonical videos."""
        memberships: List[VideoMembershipRecord] = []
        all_videos = sorted(self.video_registry.iter_videos(), key=lambda v: v.ordinal)

        for v in all_videos:
            vid = v.video_id
            series = v.series

            # Program V1 primary leaf mapping
            if series in ("L21", "L22"):
                branch_id = "program/news"
                status = "VERIFIED"
                conf = 0.99
                evidence = "60 Giây / multi-topic news format confirmed by whole-video ASR aggregate"
            elif series == "L23":
                branch_id = "program/sports/cycling"
                status = "VERIFIED"
                conf = 0.99
                evidence = "HTV Sports cycling broadcast confirmed by ASR racing terminology"
            elif series == "L24":
                branch_id = "program/cultural-performance/lion-dragon-dance"
                if vid in _L24_DIRECT_VERIFIED:
                    status = "VERIFIED"
                    conf = 0.95
                    evidence = "Lion/dragon dance competition confirmed by explicit transcript"
                else:
                    status = "INFERRED"
                    conf = 0.62
                    evidence = "Series L24 prior; individual ASR weak/generic/zero"
            elif series == "L25":
                branch_id = "program/education/exam-prep"
                status = "VERIFIED"
                conf = 0.99
                evidence = "Bí Quyết Ôn Thi THPT confirmed by lecture ASR"
            elif series == "L26":
                branch_id = "program/cooking/demonstration"
                status = "VERIFIED"
                conf = 0.995
                evidence = "Món Ngon Mỗi Ngày cooking demonstration confirmed by culinary ASR"
            elif series == "L27":
                branch_id = "program/travel-experience"
                status = "VERIFIED"
                conf = 0.98
                evidence = "Travel and local food experience confirmed by ASR"
            elif series == "L28":
                branch_id = "program/documentary/mekong-history-geography"
                status = "VERIFIED"
                conf = 0.97
                evidence = "Ký sự Mê Kông History & Geography confirmed by narration ASR"
            elif series == "L29":
                branch_id = "program/documentary/mekong-people-culture-environment"
                status = "VERIFIED"
                conf = 0.95
                evidence = "Ký sự Mê Kông People, Culture & Environment confirmed by narration ASR"
            elif series == "L30":
                branch_id = "program/positive-community-local-life-feature"
                if vid == "L30_V096":
                    status = "OUTLIER"
                    conf = 0.50
                    evidence = "Promotional/meta-content clip for contest; non-standard format"
                elif vid == "L30_V029":
                    status = "INFERRED"
                    conf = 0.58
                    evidence = "Series L30 prior; zero-ASR clip"
                else:
                    status = "VERIFIED"
                    conf = 0.95
                    evidence = "Positive community feature confirmed by human-interest ASR"
            else:
                raise ValueError(f"Unknown series '{series}' for video {vid}")

            m_rec = VideoMembershipRecord(
                membership_id=f"{vid}#{branch_id}",
                video_id=vid,
                branch_id=branch_id,
                membership_type="PRIMARY_PROGRAM",
                status=status,
                confidence=conf,
                score_type="heuristic",
                evidence=evidence,
            )
            memberships.append(m_rec)

        # L25 Subject Memberships (88 videos)
        for branch_id, vids in _L25_SUBJECT_MAPPINGS.items():
            for vid in vids:
                m_rec = VideoMembershipRecord(
                    membership_id=f"{vid}#{branch_id}",
                    video_id=vid,
                    branch_id=branch_id,
                    membership_type="SUBJECT",
                    status="VERIFIED",
                    confidence=0.98,
                    score_type="heuristic",
                    evidence="Subject explicit lecture title and ASR domain terms",
                )
                memberships.append(m_rec)

        return memberships

    def compute_checksum(
        self,
        nodes: List[TaxonomyNodeRecord],
        memberships: List[VideoMembershipRecord],
    ) -> str:
        """Compute deterministic SHA-256 over all taxonomy nodes and memberships."""
        hasher = hashlib.sha256()
        sorted_nodes = sorted(nodes, key=lambda n: n.branch_id)
        for n in sorted_nodes:
            line = f"NODE|{n.branch_id}|{n.branch_type}|{n.label_en}|{n.active}\n"
            hasher.update(line.encode("utf-8"))

        sorted_memberships = sorted(memberships, key=lambda m: (m.video_id, m.branch_id))
        for m in sorted_memberships:
            conf_str = f"{m.confidence:.4f}" if m.confidence is not None else ""
            line = f"MEM|{m.membership_id}|{m.video_id}|{m.branch_id}|{m.membership_type}|{m.status}|{conf_str}\n"
            hasher.update(line.encode("utf-8"))

        return hasher.hexdigest()

    def materialize(
        self, output_canonical_dir: Path
    ) -> Tuple[List[TaxonomyNodeRecord], List[VideoMembershipRecord], TaxonomySpace]:
        """Materialize taxonomy_nodes.jsonl, video_memberships.jsonl, and taxonomy_space.json."""
        output_canonical_dir.mkdir(parents=True, exist_ok=True)
        nodes = self.build_nodes()
        memberships = self.build_memberships()

        # Validate cardinalities
        program_memberships = [m for m in memberships if m.membership_type == "PRIMARY_PROGRAM"]
        subject_memberships = [m for m in memberships if m.membership_type == "SUBJECT"]

        if len(program_memberships) != self.video_registry.video_count():
            raise ValueError(
                f"Program memberships count mismatch: expected {self.video_registry.video_count()}, got {len(program_memberships)}"
            )

        status_counts = {"VERIFIED": 0, "INFERRED": 0, "OUTLIER": 0}
        program_counts: Dict[str, int] = {}
        for m in program_memberships:
            status_counts[m.status] = status_counts.get(m.status, 0) + 1
            program_counts[m.branch_id] = program_counts.get(m.branch_id, 0) + 1

        if status_counts != {"VERIFIED": 833, "INFERRED": 39, "OUTLIER": 1}:
            raise ValueError(f"Audited status counts mismatch: expected 833/39/1, got {status_counts}")

        expected_program_counts = {
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
        if program_counts != expected_program_counts:
            raise ValueError(f"Program counts mismatch: expected {expected_program_counts}, got {program_counts}")

        if len(subject_memberships) != 88:
            raise ValueError(f"L25 Subject memberships mismatch: expected 88, got {len(subject_memberships)}")

        checksum = self.compute_checksum(nodes, memberships)

        # Write taxonomy_nodes.jsonl
        nodes_out = output_canonical_dir / "taxonomy_nodes.jsonl"
        with open(nodes_out, "w", encoding="utf-8") as f:
            for n in nodes:
                f.write(json.dumps(n.to_dict(), ensure_ascii=False) + "\n")

        # Write video_memberships.jsonl
        mem_out = output_canonical_dir / "video_memberships.jsonl"
        with open(mem_out, "w", encoding="utf-8") as f:
            for m in memberships:
                f.write(json.dumps(m.to_dict(), ensure_ascii=False) + "\n")

        # Write taxonomy_space.json
        tax_space = TaxonomySpace(
            taxonomy_id="taxonomy_authority_v1",
            schema_version="v1",
            node_count=len(nodes),
            membership_count=len(memberships),
            program_counts=program_counts,
            status_counts=status_counts,
            checksum=checksum,
        )
        with open(output_canonical_dir / "taxonomy_space.json", "w", encoding="utf-8") as f:
            json.dump(tax_space.to_dict(), f, indent=2)

        return nodes, memberships, tax_space
