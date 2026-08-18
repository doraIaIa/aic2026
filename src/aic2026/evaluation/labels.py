from typing import Literal, Optional, List, Union
from dataclasses import dataclass, field, asdict
import json
from pathlib import Path

@dataclass(kw_only=True)
class FrameRange:
    start_frame_id: int
    end_frame_id: int

@dataclass(kw_only=True)
class TrakeEvent:
    event_order: int
    start_frame_id: int
    end_frame_id: int
    representative_frame_id: int

@dataclass(kw_only=True)
class BaseLabel:
    query_id: str
    query_type: str
    query_text: str
    split: str
    dataset_version: str = "internal_verified_v1"
    verification_status: Literal["UNVERIFIED", "IN_REVIEW", "VERIFIED", "NEEDS_MORE_REVIEW", "UNRESOLVED", "NEEDS_RANGE_REVIEW"] = "UNVERIFIED"
    label_provenance: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None

@dataclass(kw_only=True)
class KisLabel(BaseLabel):
    query_type: Literal["KIS"] = "KIS"
    video_id: Optional[str] = None
    frame_ranges: List[FrameRange] = field(default_factory=list)
    representative_frame_id: Optional[int] = None

@dataclass(kw_only=True)
class QaLabel(BaseLabel):
    query_type: Literal["QA"] = "QA"
    video_id: Optional[str] = None
    frame_ranges: List[FrameRange] = field(default_factory=list)
    representative_frame_id: Optional[int] = None
    answer_text: Optional[str] = None
    answer_variants: List[str] = field(default_factory=list)
    answer_verification: str = "MANUAL"

@dataclass(kw_only=True)
class TrakeLabel(BaseLabel):
    query_type: Literal["TRAKE"] = "TRAKE"
    video_id: Optional[str] = None
    events: List[TrakeEvent] = field(default_factory=list)

LabelType = Union[KisLabel, QaLabel, TrakeLabel]

def create_empty_labels(manifest_path: Path, output_path: Path):
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = [json.loads(line) for line in f]
        
    labels = []
    for m in manifest:
        base = {
            "query_id": m["query_id"],
            "query_text": m["query_text"],
            "split": m["split"]
        }
        if m["query_type"] == "KIS":
            labels.append(asdict(KisLabel(**base)))
        elif m["query_type"] == "QA":
            labels.append(asdict(QaLabel(**base)))
        elif m["query_type"] == "TRAKE":
            labels.append(asdict(TrakeLabel(**base)))
            
    with open(output_path, 'w', encoding='utf-8') as f:
        for lbl in labels:
            f.write(json.dumps(lbl, ensure_ascii=False) + '\n')
            
    print(f"Created {output_path} with {len(labels)} empty labels")

if __name__ == '__main__':
    manifest_path = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1\query_manifest.jsonl")
    output_path = Path(r"F:\AIC_WORK\artifacts\evaluation\internal-verified-v1\labels.jsonl")
    create_empty_labels(manifest_path, output_path)
