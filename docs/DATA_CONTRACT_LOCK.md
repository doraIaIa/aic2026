# Canonical Data Contract Lock

This contract defines the absolute truth regarding mapping alignments for the AIC 2026 Batch-1 dataset.

## Core Invariants

1. **Keyframe Ordinal:** `keyframe ordinal == CSV.n`
2. **CLIP Row Mapping:** `clip_row == CSV.n - 1`
3. **Frame Index:** `frame_idx` is an independent original-video coordinate. **NEVER** derive the keyframe filename from `frame_idx`.

## Examples of Valid Mappings

- `001.jpg` + `n=1` + `frame_idx=0` = **VALID**
- `002.jpg` + `n=2` + `frame_idx=75` = **VALID**
- `154.jpg` + `n=154` + `clip_row=153` = **VALID**

Any logic attempting to load `000000.jpg` based on `frame_idx=0` is inherently flawed and violates this contract.
