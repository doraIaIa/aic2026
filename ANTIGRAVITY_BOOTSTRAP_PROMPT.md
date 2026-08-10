# Prompt for Antigravity — Phase 0 repository bootstrap

You are acting as a senior Python/Data/ML systems engineer. Your task is to continue this repository **without broadening scope**.

Read these files first, in order:

1. `AGENTS.md`
2. `docs/IMPLEMENTATION_SPEC.md`
3. `docs/DATA_CONTRACT.md`
4. `docs/CLOUD_EXECUTION.md`
5. `README.md`

Then inspect the repository and run the complete test suite before changing anything.

## Current objective

Prepare the project for the first real AIC dataset audit and M0 implementation. Do NOT implement Whisper/OCR/SigLIP full-dataset runs yet.

## Required work

1. Add a read-only dataset discovery command that accepts `AIC_DATA_ROOT`/config root and produces a corpus audit report without downloading/copying the whole dataset.
2. Discover actual folder/file names instead of assuming them.
3. Produce counts/sizes/extensions and sample metadata only.
4. Detect Google Drive streamed/unavailable files gracefully; never force a 100 GB mirror.
5. Build a canonical `corpus_manifest.jsonl` containing only stable IDs and relative paths.
6. Add explicit checks for:
   - keyframe ordering
   - CLIP feature count/dimension against keyframe count
   - metadata/frame mapping fields
   - missing objects/metadata
   - duplicate video/keyframe IDs
7. Do not create the production FAISS index until the mapping checks pass.
8. Add tests using synthetic fixtures; never rely on the actual 100 GB corpus for unit tests.
9. All output goes under the configured work root; source data is never mutated.
10. Finish with a report: PASS/PARTIAL/FAIL/BLOCKED for every validation gate and exact commands to run next.

## Hard stop conditions

Stop and ask for review if:

- frame indexing cannot be proven;
- CLIP vectors cannot be mapped one-to-one to keyframes;
- a step requires modifying raw data;
- a dependency choice would materially change the architecture;
- the dataset root resolves only through an unstable opaque shortcut path and no stable root can be established.
