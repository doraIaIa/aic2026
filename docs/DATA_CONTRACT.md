# Data contract

## Canonical path rule

All persisted corpus paths are POSIX-style relative strings even when created on Windows.

Valid:

```text
Videos/L01_V001.mp4
Keyframes/L01_V001/000123.jpg
```

Invalid:

```text
G:\.shortcut-targets-by-id\...\L01_V001.mp4
F:\AIC_WORK\cache\...
/content/drive/MyDrive/...
/kaggle/input/...
```

The runtime resolver joins a relative path to the environment's configured root.

## Manifest item schema

Required fields:

```json
{
  "item_id": "stable-id",
  "source_relpath": "Keyframes/L01_V001/000123.jpg",
  "metadata": {}
}
```

`item_id` is immutable for the same logical source object.

## Shard schema

```json
{
  "schema_version": 1,
  "task": "ocr",
  "shard_id": "ocr-0007",
  "source_manifest_sha256": "...",
  "items": [ ... ]
}
```

## Completion marker schema

`DONE.json` is written last and includes:

- schema_version
- task
- shard_id
- started_at / finished_at
- input_manifest_sha256
- input_shard_sha256
- output_file
- output_sha256
- expected_items
- processed_items
- failed_items
- handler/model identifier
- config_hash
- optional git_commit

An importer must reject a mismatch between marker and actual files.
