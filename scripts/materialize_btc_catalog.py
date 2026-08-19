import time
from pathlib import Path

from aic2026.core.data_registry import DATA_REGISTRY
from aic2026.data_hub.btc_builder import BtcCatalogBuilder
from aic2026.data_hub.video_registry import VideoRegistry


def main():
    t0 = time.time()
    print("=== MATERIALIZING CANONICAL BTC CATALOG (M1D) ===")

    video_cat_dir = Path(r"F:\AIC_WORK\artifacts\canonical_universe_v1")
    video_registry = VideoRegistry.load_from_directory(video_cat_dir, validate=True)
    print(f"Loaded VideoRegistry: {video_registry.video_count()} canonical videos")

    drive_root = DATA_REGISTRY.btc_drive_root
    map_dir = drive_root / "data_extracted" / "map-keyframes"
    clip_dir = drive_root / "data_extracted" / "clip-features-32"
    obj_zip = Path(r"F:\AIC_WORK\tmp\objects-aic25-b1.zip")
    media_zip = Path(r"F:\AIC_WORK\tmp\media-info-aic25-b1.zip")
    faiss_dir = Path(r"F:\AIC_WORK\artifacts\m1\clip-faiss-btc-v1")
    out_dir = Path(r"F:\AIC_WORK\artifacts\canonical_btc_v1")

    builder = BtcCatalogBuilder(video_registry=video_registry)
    validation = builder.materialize(
        output_dir=out_dir,
        map_keyframes_dir=map_dir,
        clip_features_dir=clip_dir,
        objects_zip_path=obj_zip,
        media_info_zip_path=media_zip,
        faiss_dir=faiss_dir,
    )

    print("\n=== MATERIALIZATION SUMMARY ===")
    print(f"Status:                      {'PASS' if validation.is_valid else 'FAIL'}")
    print(f"Total BTC Keyframes:         {validation.btc_keyframe_count:,}")
    print(f"Total BTC Videos:            {validation.btc_video_count:,}")
    print(f"BTC Catalog Checksum:        {validation.btc_catalog_checksum}")
    print(f"Raw CLIP Row Count:          {validation.raw_clip_row_count:,}")
    print(f"Raw CLIP Mapped Rows:        {validation.raw_clip_mapped_rows:,}")
    print(f"Raw CLIP Rowmap Checksum:    {validation.raw_clip_rowmap_checksum}")
    print(f"Object Detections:           {validation.object_detection_count:,}")
    print(f"Object Empty Frames:         {validation.object_empty_keyframe_count:,}")
    print(f"Object Unavailable Frames:   {validation.object_unavailable_keyframe_count:,}")
    print(f"Object Canonical Checksum:   {validation.object_canonical_checksum}")
    print(f"Media-Info Records:          {validation.media_info_count:,}")
    print(f"Media-Info Checksum:         {validation.media_info_checksum}")
    print(f"Existing FAISS Vectors:      {validation.faiss_vector_rows:,}")
    print(f"Existing FAISS Mapped:       {validation.faiss_mapped_rows:,}")
    print(f"Total Elapsed Time:          {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
