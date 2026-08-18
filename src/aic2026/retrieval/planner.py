from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlannerDecision:
    version: str
    reason_codes: tuple[str, ...]
    requested_lanes: tuple[str, ...]


class RulePlanner:
    """Planner product deterministic; không thay equal-RRF authority của evaluation."""

    version = "rule_planner_v1"
    _OCR = ("bảng hiệu", "biển ghi", "dòng chữ", "chữ", "logo", "số hiệu", "biển báo", "màn hình", "nhãn")
    _ASR = ("nói", "phát biểu", "nhắc đến", "cho biết", "hỏi", "tên là gì", "địa điểm", "người dẫn chương trình")
    _OBJECT = ("xe", "ô tô", "xe hơi", "xe máy", "người", "chó", "mèo", "bóng", "đèn giao thông", "bao nhiêu")

    def plan(self, query_text: str, available_lanes: tuple[str, ...]) -> PlannerDecision:
        value = query_text.casefold()
        reasons: list[str] = ["BASELINE_ALL_AVAILABLE"]
        if any(term in value for term in self._OCR):
            reasons.append("TEXT_SIGNAGE")
        if any(term in value for term in self._ASR):
            reasons.append("SPEECH_CUE")
        if any(term in value for term in self._OBJECT):
            reasons.append("OBJECT_CUE")
        if not {"TEXT_SIGNAGE", "SPEECH_CUE", "OBJECT_CUE"} & set(reasons):
            reasons.append("VISUAL_DESCRIPTION")
        return PlannerDecision(self.version, tuple(reasons), tuple(sorted(available_lanes)))
