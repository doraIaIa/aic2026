from __future__ import annotations

import argparse
from pathlib import Path

from aic2026.retrieval.contract import CONTRACT_VERSION, POLICY_VERSION, contract_sha256


TEMPLATE = '''// GENERATED từ Python backend contract authority. Không sửa tay.
// contract_version: {version}
// policy_version: {policy}
// contract_sha256: {checksum}

export const RETRIEVAL_CONTRACT_VERSION = "{version}" as const;
export const RETRIEVAL_POLICY_VERSION = "{policy}" as const;
export const RETRIEVAL_CONTRACT_SHA256 = "{checksum}" as const;

export type RetrievalMode = "KIS" | "QA" | "TRAKE";
export type RetrievalLane = "visual" | "asr" | "ocr" | "object";
export type ProviderStatus = "AVAILABLE" | "UNAVAILABLE" | "ERROR" | "SKIPPED" | "MEDIA_UNAVAILABLE";
export interface SearchRequestV1 {{ contract_version: typeof RETRIEVAL_CONTRACT_VERSION; request_id: string; mode: RetrievalMode; query_text: string; mode_context?: Record<string, unknown>; routing: {{ strategy: "auto" | "manual"; enabled_lanes: RetrievalLane[]; object_match: "soft" | "exact_and" }}; filters: {{ video_ids?: string[]; start_sec?: number | null; end_sec?: number | null }}; result_limit: number; }}
export interface EvidenceV1 {{ modality: RetrievalLane; evidence_id: string; rank: number; raw_score: number | null; score_kind: string; anchor_sec: number; artifact_version: string; payload: Record<string, unknown>; }}
export interface EvidenceWindowV1 {{ evidence_window_id: string; video_id: string; start_sec: number; end_sec: number; representative: {{ kind: "visual_keyframe" | "dense_frame" | "temporal_anchor"; timestamp_sec: number; keyframe_id: string | null; frame_idx: number | null; submit_valid: boolean; operator_confirmation_required: true }}; evidence: EvidenceV1[]; fusion: Record<string, unknown>; sources: Record<string, string | null>; provenance: {{ contract_version: typeof RETRIEVAL_CONTRACT_VERSION; policy_version: typeof RETRIEVAL_POLICY_VERSION }}; }}
export interface SearchResponseV1 {{ contract_version: typeof RETRIEVAL_CONTRACT_VERSION; request_id: string; status: "OK" | "PARTIAL" | "ERROR" | "BLOCKED_BY_SCORING_CONTRACT"; route: Record<string, unknown>; providers: Record<string, Record<string, unknown>>; results: EvidenceWindowV1[]; latency_ms: Record<string, unknown>; warnings: string[]; }}
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Sinh TypeScript types từ retrieval contract authority.")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    content = TEMPLATE.format(version=CONTRACT_VERSION, policy=POLICY_VERSION, checksum=contract_sha256())
    output.write_text(content, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
