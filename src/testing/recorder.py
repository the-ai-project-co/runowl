"""Video capture and session replay data management.

Video:  Playwright's built-in `video: 'on'` option records a .webm per test.
        We (optionally) compress it with ffmpeg, generate a thumbnail, and
        link it to the TestResult.

Replay: Playwright's `trace: 'on-first-retry'` produces a .zip trace archive.
        We parse the trace.json inside to extract step timestamps.

Both are stored under ~/.runowl/recordings/<suite_id>/ and retained for the
configured duration (default: 7 days).
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from testing.models import TestSuite, VideoTimestamp

logger = logging.getLogger(__name__)

_RECORDINGS_ROOT = Path.home() / ".runowl" / "recordings"
_DEFAULT_RETENTION_DAYS = int(os.environ.get("RUNOWL_RECORDING_RETENTION_DAYS", "7"))
_COMPRESS_VIDEOS = os.environ.get("RUNOWL_COMPRESS_VIDEOS", "1") != "0"

# Playwright trace format version we know how to parse (logged as a warning if mismatch)
_KNOWN_TRACE_VERSION = 1


def recording_dir(suite_id: str) -> Path:
    """Return (and create) the recording directory for a test suite."""
    d = _RECORDINGS_ROOT / suite_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Video compression
# ---------------------------------------------------------------------------


def compress_video(src: Path, dest: Path) -> Path:
    """
    Compress a video file using ffmpeg (VP9 codec).

    If ffmpeg is not available, copies the source as-is and returns dest.
    Returns the destination path in both cases.
    """
    if not _COMPRESS_VIDEOS or not shutil.which("ffmpeg"):
        shutil.copy2(src, dest)
        logger.debug("ffmpeg not available — copied video uncompressed: %s", dest)
        return dest

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(src),
                "-vcodec", "libvpx-vp9",
                "-crf", "41",
                "-b:v", "0",
                str(dest),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        logger.debug("Compressed video: %s → %s", src, dest)
    except Exception as exc:
        logger.warning("ffmpeg compression failed (%s) — falling back to copy", exc)
        shutil.copy2(src, dest)

    return dest


# ---------------------------------------------------------------------------
# Thumbnail extraction
# ---------------------------------------------------------------------------


def extract_thumbnail(
    video_path: Path,
    dest_dir: Path,
    timestamp_s: float = 1.0,
) -> Path | None:
    """
    Extract a single frame from a video file as a JPEG thumbnail.

    Returns the thumbnail path, or None if ffmpeg is not available.
    """
    if not shutil.which("ffmpeg"):
        logger.debug("ffmpeg not available — skipping thumbnail extraction")
        return None

    thumb_path = dest_dir / f"{video_path.stem}_thumb.jpg"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", str(timestamp_s),
                "-i", str(video_path),
                "-frames:v", "1",
                str(thumb_path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        logger.debug("Extracted thumbnail: %s", thumb_path)
        return thumb_path
    except Exception as exc:
        logger.debug("Thumbnail extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Trace timestamp extraction
# ---------------------------------------------------------------------------


def extract_trace_timestamps(trace_zip_path: str) -> list[VideoTimestamp]:
    """
    Parse a Playwright trace archive (.zip) and extract step timestamps.

    Returns a list of VideoTimestamp objects with offsets relative to the
    first action's start time. Returns [] on any error.
    """
    if not trace_zip_path:
        return []

    try:
        with zipfile.ZipFile(trace_zip_path, "r") as zf:
            names = zf.namelist()

            # Warn if trace format has changed
            if "trace.json" not in names:
                logger.debug("No trace.json in %s (names: %s)", trace_zip_path, names[:5])
                return []

            raw = zf.read("trace.json")
            data = json.loads(raw)

            # Check version if present
            version = data.get("version", _KNOWN_TRACE_VERSION)
            if version != _KNOWN_TRACE_VERSION:
                logger.warning(
                    "Playwright trace version %s differs from known version %s — "
                    "timestamp parsing may be inaccurate",
                    version,
                    _KNOWN_TRACE_VERSION,
                )

            actions = data.get("actions", [])
            if not actions:
                return []

            # Determine the start epoch from the first action
            first_start = actions[0].get("startTime", 0)

            timestamps: list[VideoTimestamp] = []
            for action in actions:
                start_time = action.get("startTime", first_start)
                offset_ms = max(0.0, start_time - first_start)
                step_name = action.get("title") or action.get("type") or "unknown"
                timestamps.append(
                    VideoTimestamp(step_name=str(step_name), offset_ms=offset_ms)
                )

            return timestamps

    except zipfile.BadZipFile:
        logger.debug("Bad zip file: %s", trace_zip_path)
        return []
    except Exception as exc:
        logger.debug("Failed to parse trace %s: %s", trace_zip_path, exc)
        return []


# ---------------------------------------------------------------------------
# Store helpers
# ---------------------------------------------------------------------------


def store_video(suite_id: str, test_id: str, source_path: str | None) -> str | None:
    """
    Copy (and optionally compress) a recorded video into the suite's recording directory.
    Also extracts a thumbnail if ffmpeg is available.
    Returns the stored path, or None if source_path is absent / invalid.
    """
    if not source_path:
        return None
    src = Path(source_path)
    if not src.exists():
        logger.debug("Video source not found: %s", source_path)
        return None

    dest_dir = recording_dir(suite_id)
    dest = dest_dir / f"{test_id}{src.suffix}"

    compress_video(src, dest)
    extract_thumbnail(dest, dest_dir)

    logger.debug("Stored video: %s → %s", src, dest)
    return str(dest)


def store_replay(suite_id: str, test_id: str, source_path: str | None) -> str | None:
    """
    Copy a Playwright trace (.zip) into the suite's recording directory.
    Returns the stored path, or None if not available.
    """
    if not source_path:
        return None
    src = Path(source_path)
    if not src.exists():
        return None

    dest_dir = recording_dir(suite_id)
    dest = dest_dir / f"{test_id}_trace.zip"
    shutil.copy2(src, dest)
    logger.debug("Stored replay trace: %s → %s", src, dest)
    return str(dest)


def attach_recordings(suite: TestSuite, tmp_dir: str) -> None:
    """
    After a Docker E2E run, scan the tmp_dir for video / trace files and
    attach them to the corresponding TestResult objects in the suite.
    Also extracts video timestamps and replay events.
    """
    from testing.replay import link_assertions, parse_trace

    tmp = Path(tmp_dir)

    for result in suite.results:
        # Store and compress video
        if result.video_path:
            stored = store_video(suite.id, result.test_id, result.video_path)
            result.video_path = stored

            # Thumbnail path (same dir, _thumb.jpg suffix)
            if stored:
                thumb = Path(stored).parent / f"{Path(stored).stem}_thumb.jpg"
                if thumb.exists():
                    result.thumbnail_path = str(thumb)

        # Store Playwright trace archive
        trace_candidates = list(tmp.rglob(f"*{result.test_id}*trace*.zip"))
        if not trace_candidates:
            trace_candidates = list(tmp.rglob("*.zip"))
        if trace_candidates:
            stored_replay = store_replay(suite.id, result.test_id, str(trace_candidates[0]))
            result.replay_path = stored_replay

            # Extract step timestamps from trace
            if stored_replay:
                result.video_timestamps = extract_trace_timestamps(stored_replay)

            # Parse replay events and link to assertion failures
            if stored_replay:
                events = parse_trace(stored_replay)
                result.replay_events = link_assertions(events, result)

        # Screenshots (on failure)
        screenshots = (
            list((tmp / "screenshots").rglob(f"*{result.test_id}*"))
            if (tmp / "screenshots").exists()
            else []
        )
        if screenshots:
            dest_dir = recording_dir(suite.id)
            stored_shots: list[str] = []
            for shot in screenshots[:5]:  # cap at 5
                dest = dest_dir / f"{result.test_id}_{shot.name}"
                shutil.copy2(shot, dest)
                stored_shots.append(str(dest))
            result.screenshots = stored_shots


def purge_old_recordings(retention_days: int = _DEFAULT_RETENTION_DAYS) -> int:
    """
    Remove recording directories older than retention_days.
    Returns the number of directories removed.
    """
    if not _RECORDINGS_ROOT.exists():
        return 0

    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    removed = 0

    for suite_dir in _RECORDINGS_ROOT.iterdir():
        if not suite_dir.is_dir():
            continue
        mtime = datetime.utcfromtimestamp(suite_dir.stat().st_mtime)
        if mtime < cutoff:
            shutil.rmtree(suite_dir, ignore_errors=True)
            removed += 1
            logger.debug("Purged old recording dir: %s", suite_dir)

    return removed
