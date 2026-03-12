"""Tests for testing.recorder — video compression, thumbnails, and trace timestamps."""

from __future__ import annotations

import json
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from testing.models import TestResult, TestStatus, TestSuite
from testing.recorder import (
    attach_recordings,
    compress_video,
    extract_thumbnail,
    extract_trace_timestamps,
    purge_old_recordings,
    recording_dir,
    store_video,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_fake_trace_zip(dest: Path, actions: list[dict]) -> None:
    """Write a minimal Playwright trace.json into a zip at dest."""
    trace_data = {"version": 1, "actions": actions}
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("trace.json", json.dumps(trace_data))


# ---------------------------------------------------------------------------
# store_video
# ---------------------------------------------------------------------------


class TestStoreVideo:
    def test_returns_none_when_source_is_none(self, tmp_path: Path) -> None:
        with patch("testing.recorder._RECORDINGS_ROOT", tmp_path / "recordings"):
            result = store_video("suite1", "test1", None)
        assert result is None

    def test_returns_none_when_source_missing(self, tmp_path: Path) -> None:
        with patch("testing.recorder._RECORDINGS_ROOT", tmp_path / "recordings"):
            result = store_video("suite1", "test1", str(tmp_path / "nonexistent.webm"))
        assert result is None

    def test_copies_video_to_recording_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "input.webm"
        src.write_bytes(b"fake video content")

        recordings_root = tmp_path / "recordings"
        with patch("testing.recorder._RECORDINGS_ROOT", recordings_root):
            with patch("testing.recorder._COMPRESS_VIDEOS", False):
                result = store_video("suite1", "test1", str(src))

        assert result is not None
        assert Path(result).exists()
        assert Path(result).read_bytes() == b"fake video content"

    def test_returns_stored_path_string(self, tmp_path: Path) -> None:
        src = tmp_path / "vid.webm"
        src.write_bytes(b"x")
        recordings_root = tmp_path / "recordings"
        with patch("testing.recorder._RECORDINGS_ROOT", recordings_root):
            with patch("testing.recorder._COMPRESS_VIDEOS", False):
                result = store_video("mysuite", "mytest", str(src))
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# compress_video
# ---------------------------------------------------------------------------


class TestCompressVideo:
    def test_copies_file_when_ffmpeg_not_available(self, tmp_path: Path) -> None:
        src = tmp_path / "src.webm"
        dest = tmp_path / "dest.webm"
        src.write_bytes(b"raw video")

        with patch("shutil.which", return_value=None):
            result = compress_video(src, dest)

        assert result == dest
        assert dest.read_bytes() == b"raw video"

    def test_calls_ffmpeg_when_available(self, tmp_path: Path) -> None:
        src = tmp_path / "src.webm"
        dest = tmp_path / "dest.webm"
        src.write_bytes(b"raw video")

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # Also ensure dest is written (simulate ffmpeg success via copy)
                shutil.copy2(src, dest)
                result = compress_video(src, dest)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert str(src) in cmd
        assert str(dest) in cmd

    def test_falls_back_to_copy_on_ffmpeg_failure(self, tmp_path: Path) -> None:
        src = tmp_path / "src.webm"
        dest = tmp_path / "dest.webm"
        src.write_bytes(b"content")

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", side_effect=Exception("ffmpeg crashed")):
                result = compress_video(src, dest)

        assert result == dest
        assert dest.read_bytes() == b"content"


# ---------------------------------------------------------------------------
# extract_thumbnail
# ---------------------------------------------------------------------------


class TestExtractThumbnail:
    def test_returns_none_when_ffmpeg_not_available(self, tmp_path: Path) -> None:
        video = tmp_path / "video.webm"
        video.write_bytes(b"x")

        with patch("shutil.which", return_value=None):
            result = extract_thumbnail(video, tmp_path)

        assert result is None

    def test_calls_ffmpeg_with_correct_args(self, tmp_path: Path) -> None:
        video = tmp_path / "video.webm"
        video.write_bytes(b"x")
        thumb = tmp_path / "video_thumb.jpg"

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                # Simulate ffmpeg creating the thumbnail
                thumb.write_bytes(b"jpg")
                result = extract_thumbnail(video, tmp_path, timestamp_s=2.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "2.0" in cmd

    def test_returns_none_on_ffmpeg_failure(self, tmp_path: Path) -> None:
        video = tmp_path / "video.webm"
        video.write_bytes(b"x")

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            with patch("subprocess.run", side_effect=Exception("error")):
                result = extract_thumbnail(video, tmp_path)

        assert result is None


# ---------------------------------------------------------------------------
# extract_trace_timestamps
# ---------------------------------------------------------------------------


class TestExtractTraceTimestamps:
    def test_parses_two_actions(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        actions = [
            {"title": "goto", "startTime": 1000.0},
            {"title": "click", "startTime": 1500.0},
        ]
        _write_fake_trace_zip(trace_zip, actions)

        timestamps = extract_trace_timestamps(str(trace_zip))
        assert len(timestamps) == 2

    def test_first_event_has_zero_offset(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        actions = [
            {"title": "start", "startTime": 5000.0},
            {"title": "end", "startTime": 5200.0},
        ]
        _write_fake_trace_zip(trace_zip, actions)

        timestamps = extract_trace_timestamps(str(trace_zip))
        assert timestamps[0].offset_ms == 0.0

    def test_subsequent_events_have_positive_offsets(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        actions = [
            {"title": "a", "startTime": 0.0},
            {"title": "b", "startTime": 300.0},
        ]
        _write_fake_trace_zip(trace_zip, actions)

        timestamps = extract_trace_timestamps(str(trace_zip))
        assert timestamps[1].offset_ms == 300.0
        assert timestamps[1].step_name == "b"

    def test_returns_empty_for_nonexistent_path(self) -> None:
        timestamps = extract_trace_timestamps("/does/not/exist.zip")
        assert timestamps == []

    def test_returns_empty_for_zip_without_trace_json(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        with zipfile.ZipFile(trace_zip, "w") as zf:
            zf.writestr("other.txt", "no trace here")

        timestamps = extract_trace_timestamps(str(trace_zip))
        assert timestamps == []

    def test_returns_empty_for_empty_string(self) -> None:
        timestamps = extract_trace_timestamps("")
        assert timestamps == []


# ---------------------------------------------------------------------------
# purge_old_recordings
# ---------------------------------------------------------------------------


class TestPurgeOldRecordings:
    def test_removes_old_suite_dirs(self, tmp_path: Path) -> None:
        recordings = tmp_path / "recordings"
        old_dir = recordings / "old_suite"
        old_dir.mkdir(parents=True)
        # Set mtime to 10 days ago
        old_time = (datetime.utcnow() - timedelta(days=10)).timestamp()
        import os
        os.utime(old_dir, (old_time, old_time))

        with patch("testing.recorder._RECORDINGS_ROOT", recordings):
            removed = purge_old_recordings(retention_days=7)

        assert removed == 1
        assert not old_dir.exists()

    def test_keeps_recent_suite_dirs(self, tmp_path: Path) -> None:
        recordings = tmp_path / "recordings"
        new_dir = recordings / "new_suite"
        new_dir.mkdir(parents=True)

        with patch("testing.recorder._RECORDINGS_ROOT", recordings):
            removed = purge_old_recordings(retention_days=7)

        assert removed == 0
        assert new_dir.exists()

    def test_returns_zero_when_root_missing(self, tmp_path: Path) -> None:
        with patch("testing.recorder._RECORDINGS_ROOT", tmp_path / "does_not_exist"):
            removed = purge_old_recordings()
        assert removed == 0


# ---------------------------------------------------------------------------
# attach_recordings
# ---------------------------------------------------------------------------


class TestAttachRecordings:
    def test_attaches_video_path(self, tmp_path: Path) -> None:
        # Create a fake video file in the tmp dir
        video_src = tmp_path / "e2e12345.webm"
        video_src.write_bytes(b"video data")

        suite = TestSuite(pr_ref="owner/repo#1")
        result = TestResult(
            test_id="e2e12345",
            test_name="test_e2e",
            status=TestStatus.FAIL,
            video_path=str(video_src),
        )
        suite.results.append(result)

        recordings_root = tmp_path / "recordings"
        with patch("testing.recorder._RECORDINGS_ROOT", recordings_root):
            with patch("testing.recorder._COMPRESS_VIDEOS", False):
                with patch("testing.replay.parse_trace", return_value=[]):
                    with patch("testing.replay.link_assertions", return_value=[]):
                        attach_recordings(suite, str(tmp_path))

        assert suite.results[0].video_path is not None
        assert Path(suite.results[0].video_path).exists()
