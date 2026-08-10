from __future__ import annotations

from typing import Any, Protocol
import time

from aic2026.jobs.models import ManifestItem


class ItemHandler(Protocol):
    name: str

    def process(self, item: ManifestItem) -> dict[str, Any]: ...


class EchoHandler:
    name = "echo"

    def process(self, item: ManifestItem) -> dict[str, Any]:
        return {
            "item_id": item.item_id,
            "source_relpath": item.source_relpath,
            "metadata": item.metadata,
            "handler": self.name,
        }


class SlowEchoHandler:
    name = "slow_echo"

    def __init__(self, sleep_sec: float = 0.5):
        self.sleep_sec = sleep_sec

    def process(self, item: ManifestItem) -> dict[str, Any]:
        time.sleep(self.sleep_sec)
        return {
            "item_id": item.item_id,
            "source_relpath": item.source_relpath,
            "metadata": item.metadata,
            "handler": self.name,
        }


def get_handler(name: str) -> ItemHandler:
    if name == "echo":
        return EchoHandler()
    if name == "slow_echo":
        return SlowEchoHandler()
    raise ValueError(
        f"Unknown handler {name!r}. Only 'echo' and 'slow_echo' are implemented in the reliability scaffold; "
        "ML handlers must be added after dataset audit."
    )
