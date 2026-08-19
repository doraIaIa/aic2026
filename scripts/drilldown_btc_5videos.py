import json
import zipfile
from pathlib import Path
import numpy as np

from aic2026.core.data_registry import DATA_REGISTRY
from aic2026.data_hub.btc_registry import BtcRegistry
from aic2026.data_hub.video_registry import VideoRegistry
from aic2026.media.resolver import MediaResolver


def main():
    print("=== 5-VIDEO BTC DRILLDOWN & MEDIA RESOLVER VALIDATION ===")
    video_cat_dir = Path(r"F:\AIC_WORK\artifacts\canonical_universe_v1")
    btc_cat_dir = Path(r"F:\AIC_WORK\artifacts\canonical_btc_v1")
    drive_root = DATA_REGISTRY.btc_drive_root
    obj_zip_path = Path(r"F:\AIC_WORK\tmp\objects-aic25-b1.zip")

    video_reg = VideoRegistry.load_from_directory(video_cat_dir)
    btc_reg = BtcRegistry.load_from_directory(btc_cat_dir, load_clip=True, load_objects=False, load_media=True)
    media_resolver = MediaResolver(media_root=drive_root)

    sample_videos = ["L21_V001", "L24_V008", "L25_V002", "L26_V361", "L30_V041"]

    results = []

    with zipfile.ZipFile(obj_zip_path, "r") as zf:
        for vid in sample_videos:
            v_rec = video_reg.get_video(vid)
            btc_kfs = btc_reg.get_btc_keyframes_by_video(vid)
            media_info = btc_reg.get_media_info(vid)
            clip_ref = btc_reg.get_btc_clip_ref(vid)

            # Check raw video file on drive via MediaResolver
            raw_video_path = drive_root / v_rec.source_relpath
            resolver_meta = None
            frame_resolve_test = None
            if raw_video_path.exists():
                try:
                    meta = media_resolver.video_info(vid)
                    resolver_meta = meta.to_dict()
                except Exception as e:
                    resolver_meta = {"error": str(e)}

            # Pick sample keyframe n=10 (or last if fewer)
            sample_n = min(10, len(btc_kfs))
            sample_kf = btc_reg.get_btc_keyframe_by_video_n(vid, sample_n)

            # Resolve frame by time on source video
            if raw_video_path.exists() and sample_kf:
                try:
                    resolve_res = media_resolver.resolve_frame_by_time(vid, sample_kf.raw_pts_time)
                    frame_resolve_test = resolve_res.to_dict()
                except Exception as e:
                    frame_resolve_test = {"error": str(e)}

            # Read object detections for this keyframe from zip
            obj_member = f"objects/{vid}/{sample_n:03d}.json"
            top_objs = []
            obj_count = 0
            try:
                raw_bytes = zf.read(obj_member)
                data = json.loads(raw_bytes.decode("utf-8"))
                scores = data.get("detection_scores", [])
                class_names = data.get("detection_class_names", [])
                boxes = data.get("detection_boxes", [])
                obj_count = len(scores)
                for d_i in range(min(3, obj_count)):
                    box = boxes[d_i] if d_i < len(boxes) else [0, 0, 0, 0]
                    top_objs.append({
                        "class_name": class_names[d_i] if d_i < len(class_names) else "",
                        "confidence": float(scores[d_i]),
                        "bbox": [float(x) for x in box],
                    })
            except KeyError:
                pass

            top_obj_str = "; ".join(
                f"{o['class_name']} ({o['confidence']:.2f}, bbox=[{o['bbox'][0]:.2f},{o['bbox'][1]:.2f},{o['bbox'][2]:.2f},{o['bbox'][3]:.2f}])"
                for o in top_objs
            ) if top_objs else "None"

            # Check raw clip row mapping
            clip_row_idx = sample_n - 1

            # Read raw CLIP row to verify unit norm and dtype
            clip_npy_path = drive_root / "data_extracted" / "clip-features-32" / f"{vid}.npy"
            clip_arr = np.load(clip_npy_path)
            row_vec = clip_arr[clip_row_idx]
            vec_norm = float(np.linalg.norm(row_vec.astype(np.float32)))

            res = {
                "video_id": vid,
                "video_ordinal": v_rec.ordinal,
                "series": v_rec.series,
                "duration_sec": v_rec.duration_sec,
                "fps": v_rec.fps,
                "width": v_rec.width,
                "height": v_rec.height,
                "source_relpath": v_rec.source_relpath,
                "raw_video_exists": raw_video_path.exists(),
                "resolver_fps": resolver_meta.get("fps") if resolver_meta else None,
                "resolver_duration_sec": resolver_meta.get("duration_sec") if resolver_meta else None,
                "resolver_frame_count": resolver_meta.get("frame_count") if resolver_meta else None,
                "btc_keyframe_count": len(btc_kfs),
                "clip_source_relpath": clip_ref.feature_relpath if clip_ref else None,
                "clip_rows": clip_ref.total_rows if clip_ref else None,
                "clip_dimension": int(clip_arr.shape[1]),
                "clip_dtype": str(clip_arr.dtype),
                "clip_row_unit_norm": round(vec_norm, 6),
                "media_title": media_info.title if media_info else None,
                "media_channel": media_info.author if media_info else None,
                "media_duration_sec": media_info.duration_sec if media_info else None,
                "sample_n": sample_n,
                "sample_uid": sample_kf.keyframe_uid if sample_kf else None,
                "sample_pts_time": sample_kf.raw_pts_time if sample_kf else None,
                "sample_timestamp_ms": sample_kf.timestamp_ms if sample_kf else None,
                "sample_frame_idx": sample_kf.frame_idx if sample_kf else None,
                "sample_image_relpath": sample_kf.image_relpath if sample_kf else None,
                "clip_row_idx": clip_row_idx,
                "top_objects": top_obj_str,
                "object_count_in_frame": obj_count,
                "frame_resolve_test": frame_resolve_test,
            }
            results.append(res)

            print(f"\n--- {vid} (Ordinal {v_rec.ordinal}) ---")
            print(f"  Series:            {v_rec.series}")
            print(f"  Video Metadata:    {v_rec.duration_sec}s @ {v_rec.fps}fps ({v_rec.width}x{v_rec.height})")
            print(f"  BTC Keyframes:     {len(btc_kfs):,}")
            print(f"  Raw CLIP:          {clip_arr.shape} ({clip_arr.dtype}), row {clip_row_idx} L2-norm={vec_norm:.6f}")
            print(f"  Media Info:        '{media_info.title[:50] if media_info and media_info.title else 'N/A'}' by {media_info.author if media_info else 'N/A'} ({media_info.duration_sec if media_info else 'N/A'}s)")
            print(f"  Sample Keyframe:   {sample_kf.keyframe_uid}")
            print(f"    n:               {sample_n}")
            print(f"    pts_time:        {sample_kf.raw_pts_time}s ({sample_kf.timestamp_ms}ms)")
            print(f"    frame_idx:       {sample_kf.frame_idx}")
            print(f"    JPEG path:       {sample_kf.image_relpath}")
            print(f"    Top Objects:     {top_obj_str}")
            print(f"  Media Resolver:    duration={res.get('resolver_duration_sec')}s, fps={res.get('resolver_fps')}, frames={res.get('resolver_frame_count')}")
            if frame_resolve_test:
                print(f"  Source Video Frame Resolve: req={sample_kf.raw_pts_time}s -> frame={frame_resolve_test.get('competition_frame_id')}, pts={frame_resolve_test.get('decoded_pts_sec')}s")

    out_json = btc_cat_dir / "drilldown_5videos.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved drilldown data to {out_json}")


if __name__ == "__main__":
    main()
