from __future__ import annotations

from aic2026.workspace import WorkspaceError, WorkspaceStore


def _item(kind: str = "KIS"):
    return {"btc_stt": "1", "original_query": "xe", "search_query": "xe", "query_type": kind, "video_id": "L21_V001", "timestamp_sec": 3.0, "frame_id": 75, "answer_text": "đáp án" if kind == "QA" else None, "match_lanes": ["visual", "object"], "note": "", "status": "draft", "events": [] if kind != "TRAKE" else [{"event_order": 1, "video_id": "L21_V001", "timestamp_sec": 3.0, "frame_id": 75}, {"event_order": 2, "video_id": "L21_V001", "timestamp_sec": 6.0, "frame_id": 150}]}


def test_workspace_persists_crud_and_export(tmp_path):
    store = WorkspaceStore(tmp_path / "workspace.sqlite")
    created = store.save(_item("TRAKE"))
    assert created["events"][1]["frame_id"] == 150
    assert store.list()[0]["id"] == created["id"]
    updated = store.save({**_item("TRAKE"), "status": "confirmed"}, entry_id=created["id"])
    assert updated["status"] == "confirmed"
    assert '"query_type": "TRAKE"' in store.export("json")
    assert "frame_id" in store.export("csv")
    store.delete(created["id"])
    assert store.list() == []


def test_workspace_rejects_cross_video_trake():
    item = _item("TRAKE")
    item["events"][1]["video_id"] = "L21_V002"
    try:
        WorkspaceStore(":memory:").save(item)
    except WorkspaceError as exc:
        assert "cùng video" in str(exc)
    else:
        raise AssertionError("TRAKE cross-video phải fail closed")
