from __future__ import annotations

from aic2026.data_hub.asr_ocr_builder import (
    AsrOcrCatalogBuilder,
    normalize_canonical_text,
)
from aic2026.data_hub.asr_ocr_models import (
    AsrOcrValidationResult,
    AsrSegmentRecord,
    AsrVideoCoverageRecord,
    OcrBgeRowmapRecord,
    OcrItemRecord,
    OcrKeyframeCoverageRecord,
)
from aic2026.data_hub.asr_ocr_registry import AsrOcrRegistry
from aic2026.data_hub.asr_ocr_validator import AsrOcrValidator
from aic2026.data_hub.btc_builder import BtcCatalogBuilder
from aic2026.data_hub.btc_models import (
    BtcClipRowRecord,
    BtcKeyframeRecord,
    BtcMediaInfoRecord,
    BtcObjectCoverageRecord,
    BtcObjectDetectionRecord,
    BtcSpace,
    BtcValidationResult,
)
from aic2026.data_hub.btc_registry import BtcRegistry
from aic2026.data_hub.btc_validator import BtcValidator
from aic2026.data_hub.builder import (
    build_canonical_video_records,
    materialize_video_catalog,
    natural_video_sort_key,
)
from aic2026.data_hub.custom_builder import (
    build_custom_and_qwen_records,
    materialize_custom_qwen_catalog,
    normalize_custom_image_relpath,
)
from aic2026.data_hub.custom_models import (
    CustomKeyframeRecord,
    CustomSpace,
    CustomValidationResult,
    QwenMissingRecord,
    QwenSemanticRecord,
)
from aic2026.data_hub.custom_registry import CustomKeyframeRegistry
from aic2026.data_hub.custom_validator import CustomKeyframeValidator
from aic2026.data_hub.models import (
    SourceRecord,
    ValidationResult,
    VideoRecord,
    VideoSpace,
)
from aic2026.data_hub.validator import (
    EXPECTED_SERIES_COUNTS_873,
    VideoRegistryValidator,
)
from aic2026.data_hub.video_registry import VideoRegistry

__all__ = [
    # Video Catalog
    "VideoRecord",
    "VideoSpace",
    "SourceRecord",
    "ValidationResult",
    "VideoRegistryValidator",
    "VideoRegistry",
    "EXPECTED_SERIES_COUNTS_873",
    "natural_video_sort_key",
    "build_canonical_video_records",
    "materialize_video_catalog",
    # Custom & Qwen
    "CustomKeyframeRecord",
    "QwenSemanticRecord",
    "QwenMissingRecord",
    "CustomSpace",
    "CustomValidationResult",
    "CustomKeyframeValidator",
    "CustomKeyframeRegistry",
    "normalize_custom_image_relpath",
    "build_custom_and_qwen_records",
    "materialize_custom_qwen_catalog",
    # ASR & OCR
    "AsrSegmentRecord",
    "AsrVideoCoverageRecord",
    "OcrItemRecord",
    "OcrKeyframeCoverageRecord",
    "OcrBgeRowmapRecord",
    "AsrOcrValidationResult",
    "AsrOcrValidator",
    "AsrOcrCatalogBuilder",
    "AsrOcrRegistry",
    "normalize_canonical_text",
    # BTC Space
    "BtcKeyframeRecord",
    "BtcClipRowRecord",
    "BtcObjectDetectionRecord",
    "BtcObjectCoverageRecord",
    "BtcMediaInfoRecord",
    "BtcSpace",
    "BtcValidationResult",
    "BtcValidator",
    "BtcCatalogBuilder",
    "BtcRegistry",
]
