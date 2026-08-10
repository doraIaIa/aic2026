from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ManifestItem:
    item_id: str
    source_relpath: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ManifestItem":
        item_id = str(value["item_id"]).strip()
        source_relpath = str(value["source_relpath"]).strip()
        if not item_id:
            raise ValueError("item_id cannot be empty")
        if not source_relpath:
            raise ValueError("source_relpath cannot be empty")
        metadata = value.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        return cls(item_id=item_id, source_relpath=source_relpath, metadata=metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "source_relpath": self.source_relpath,
            "metadata": self.metadata,
        }
