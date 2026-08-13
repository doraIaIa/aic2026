"""AIC 2026 - Frame Identity Mapper.

Provides the explicit conversion logic between the physical decoded frame
ordinal and the competition submission convention (BTC frame ID).
"""
from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class PhysicalFrame:
    """Identity of the physical frame on the video timeline."""
    video_id: str
    decoded_frame_ordinal: int
    decoded_pts_sec: float


@dataclasses.dataclass
class CompetitionFrameIdentity:
    """Identity for BTC-compatible submission."""
    video_id: str
    decoded_frame_ordinal: int
    decoded_pts_sec: float
    competition_frame_id: int
    mapping_method: str


class FrameIdentityMapper:
    """Adapter to resolve and convert frame identities."""

    @staticmethod
    def resolve_physical_frame(video_id: str, time_sec: float, fps: float) -> PhysicalFrame:
        """Resolves an anchor time into a mathematical true physical frame.
        
        The physical ordinal is round(time_sec * fps).
        """
        effective_fps = fps if fps > 0 else 25.0
        # Time is strictly the continuous domain
        decoded_frame_ordinal = round(time_sec * effective_fps)
        # PTS is the discrete time
        decoded_pts_sec = round(decoded_frame_ordinal / effective_fps, 6)
        
        return PhysicalFrame(
            video_id=video_id,
            decoded_frame_ordinal=decoded_frame_ordinal,
            decoded_pts_sec=decoded_pts_sec
        )

    @staticmethod
    def map_physical_to_btc(physical: PhysicalFrame, fps: float) -> CompetitionFrameIdentity:
        """Converts a physical frame to the competition submission ID.
        
        Audit over 21,595 canonical keyframes proved the BTC map-keyframes
        were generated via integer truncation (int(pts_time * fps)) instead
        of rounding. Crucially, BTC also rounded the fps to 2 decimals first
        (e.g., 29.97 instead of 30000/1001), which causes further drift.
        """
        effective_fps = fps if fps > 0 else 25.0
        btc_fps = round(effective_fps, 2)
        
        # Apply the discovered deterministic mapping
        competition_frame_id = int(physical.decoded_pts_sec * btc_fps)
        
        return CompetitionFrameIdentity(
            video_id=physical.video_id,
            decoded_frame_ordinal=physical.decoded_frame_ordinal,
            decoded_pts_sec=physical.decoded_pts_sec,
            competition_frame_id=competition_frame_id,
            mapping_method="deterministic_int_truncation"
        )

    @staticmethod
    def resolve_and_map(video_id: str, time_sec: float, fps: float) -> CompetitionFrameIdentity:
        """Helper to resolve a time to a full dual-identity frame."""
        physical = FrameIdentityMapper.resolve_physical_frame(video_id, time_sec, fps)
        return FrameIdentityMapper.map_physical_to_btc(physical, fps)
