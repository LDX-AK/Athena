"""Shared path helpers for keeping Athena v2 and v3 artifacts separated."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_RESULTS_ROOT = ROOT / "data" / "results"
_MODELS_ROOT = ROOT / "athena" / "model"
_ALLOWED_TRACKS = {"v2", "v3"}
_ALLOWED_KINDS = {"results", "models"}


def normalize_track(track: str) -> str:
    name = str(track).strip().lower()
    if name not in _ALLOWED_TRACKS:
        raise ValueError(f"Unsupported track: {track!r}. Expected one of {sorted(_ALLOWED_TRACKS)}")
    return name


def track_dir(track: str, kind: str = "results") -> Path:
    track_name = normalize_track(track)
    kind_name = str(kind).strip().lower()
    if kind_name not in _ALLOWED_KINDS:
        raise ValueError(f"Unsupported path kind: {kind!r}. Expected one of {sorted(_ALLOWED_KINDS)}")
    if kind_name == "results":
        return _RESULTS_ROOT / track_name
    return _MODELS_ROOT / track_name


def default_result_path(track: str, timeframe: str, candidate: str, suffix: str) -> Path:
    track_name = normalize_track(track)
    safe_tf = str(timeframe).strip().lower()
    safe_candidate = str(candidate).strip().lower()
    safe_suffix = str(suffix).strip().lower().replace(" ", "_")
    return track_dir(track_name, "results") / f"walkforward_{safe_tf}_{safe_candidate}_{safe_suffix}.json"
