"""Video capture and session replay data management.

Video:  Playwright's built-in `video: 'on'` option records a .webm per test.
        We compress and store it, generate a thumbnail path, and link it to
        the TestResult.

Replay: Playwright's `trace: 'on-first-retry'` produces a .zip trace archive
        that can be opened in trace.playwright.dev. We store the path so the
        UI can offer a download link.

Both are stored under ~/.runowl/recordings/<suite_id>/ and retained for the
configured duration (default: 7 days).
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from testing.models import TestSuite

logger = logging.getLogger(__name__)

_RECORDINGS_ROOT = Path.home() / ".runowl" / "recordings"
_DEFAULT_RETENTION_DAYS = int(os.environ.get("RUNOWL_RECORDING_RETENTION_DAYS", "7"))


def recording_dir(suite_id: str) -> Path:
    """Return (and create) the recording directory for a test suite."""
    d = _RECORDINGS_ROOT / suite_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def store_video(suite_id: str, test_id: str, source_path: str | None) -> str | None:
    """
    Copy a recorded video file into the suite's recording directory.
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
    shutil.copy2(src, dest)
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
    """
    tmp = Path(tmp_dir)

    for result in suite.results:
        if result.video_path:
            stored = store_video(suite.id, result.test_id, result.video_path)
            result.video_path = stored

        # Look for a Playwright trace archive matching this test
        trace_candidates = list(tmp.rglob(f"*{result.test_id}*trace*.zip"))
        if not trace_candidates:
            trace_candidates = list(tmp.rglob("*.zip"))
        if trace_candidates:
            stored_replay = store_replay(suite.id, result.test_id, str(trace_candidates[0]))
            result.replay_path = stored_replay

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
