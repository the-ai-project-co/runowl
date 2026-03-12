"""Tests for testing.replay — DOM/network/console capture, timeline, assertion linking."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from testing.models import ReplayEventType, TestResult, TestStatus
from testing.replay import build_timeline, link_assertions, parse_trace


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_trace_zip(
    dest: Path,
    actions: list[dict] | None = None,
    resources: list[dict] | None = None,
    console: list[dict] | None = None,
) -> None:
    """Write a minimal Playwright trace.json into a zip at dest."""
    trace = {"version": 1}
    if actions is not None:
        trace["actions"] = actions
    if resources is not None:
        trace["resources"] = resources
    if console is not None:
        trace["console"] = console
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr("trace.json", json.dumps(trace))


def _failing_result(test_id: str = "t001") -> TestResult:
    return TestResult(test_id=test_id, test_name=f"test_{test_id}", status=TestStatus.FAIL)


def _passing_result(test_id: str = "t001") -> TestResult:
    return TestResult(test_id=test_id, test_name=f"test_{test_id}", status=TestStatus.PASS)


# ---------------------------------------------------------------------------
# parse_trace
# ---------------------------------------------------------------------------


class TestParseTrace:
    def test_returns_dom_events_for_actions(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[
                {"title": "goto", "type": "navigate", "startTime": 0.0},
                {"title": "click", "type": "click", "startTime": 100.0},
            ],
        )
        events = parse_trace(str(trace_zip))
        dom_events = [e for e in events if e.type == ReplayEventType.DOM_ACTION]
        assert len(dom_events) == 2

    def test_returns_assertion_event_for_expect_type(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[
                {"title": "expect", "type": "expect", "startTime": 0.0, "error": "Expected true"},
            ],
        )
        events = parse_trace(str(trace_zip))
        assertion_events = [e for e in events if e.type == ReplayEventType.ASSERTION]
        assert len(assertion_events) == 1

    def test_returns_network_events(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[{"title": "a", "startTime": 0.0}],
            resources=[{"url": "https://api.example.com/data", "method": "GET", "status": 200, "timestamp": 50.0}],
        )
        events = parse_trace(str(trace_zip))
        network_events = [e for e in events if e.type == ReplayEventType.NETWORK_REQUEST]
        assert len(network_events) == 1
        assert network_events[0].detail["url"] == "https://api.example.com/data"

    def test_returns_console_events(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[{"title": "a", "startTime": 0.0}],
            console=[{"text": "Error: something failed", "type": "error", "timestamp": 200.0}],
        )
        events = parse_trace(str(trace_zip))
        console_events = [e for e in events if e.type == ReplayEventType.CONSOLE_LOG]
        assert len(console_events) == 1
        assert "something failed" in console_events[0].detail["text"]

    def test_first_event_offset_is_zero(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[
                {"title": "start", "startTime": 9000.0},
                {"title": "end", "startTime": 9500.0},
            ],
        )
        events = parse_trace(str(trace_zip))
        assert events[0].offset_ms == 0.0

    def test_subsequent_events_have_increasing_offsets(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[
                {"title": "a", "startTime": 100.0},
                {"title": "b", "startTime": 400.0},
            ],
        )
        events = parse_trace(str(trace_zip))
        assert events[1].offset_ms == pytest.approx(300.0)

    def test_returns_empty_for_nonexistent_path(self) -> None:
        events = parse_trace("/no/such/file.zip")
        assert events == []

    def test_returns_empty_for_missing_trace_json(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        with zipfile.ZipFile(trace_zip, "w") as zf:
            zf.writestr("other.json", "{}")
        events = parse_trace(str(trace_zip))
        assert events == []

    def test_total_event_count_matches_input(self, tmp_path: Path) -> None:
        trace_zip = tmp_path / "trace.zip"
        _write_trace_zip(
            trace_zip,
            actions=[
                {"title": "goto", "type": "navigate", "startTime": 0.0},
                {"title": "expect", "type": "expect", "startTime": 100.0, "error": "fail"},
            ],
            resources=[{"url": "http://x.com", "timestamp": 50.0}],
            console=[{"text": "log msg", "type": "log", "timestamp": 80.0}],
        )
        events = parse_trace(str(trace_zip))
        # 2 actions + 1 network + 1 console = 4
        assert len(events) == 4


# ---------------------------------------------------------------------------
# build_timeline
# ---------------------------------------------------------------------------


class TestBuildTimeline:
    def _make_events(self, offsets: list[float]) -> list:
        from testing.models import ReplayEvent, ReplayEventType

        return [
            ReplayEvent(type=ReplayEventType.DOM_ACTION, offset_ms=offset)
            for offset in offsets
        ]

    def test_sorts_events_by_offset(self) -> None:
        events = self._make_events([300.0, 100.0, 200.0])
        timeline = build_timeline(events)
        offsets = [e.offset_ms for e in timeline]
        assert offsets == sorted(offsets)

    def test_assigns_cluster_id_to_all_events(self) -> None:
        events = self._make_events([0.0, 50.0, 200.0])
        timeline = build_timeline(events)
        assert all(e.cluster_id is not None for e in timeline)

    def test_events_within_100ms_get_same_cluster(self) -> None:
        events = self._make_events([0.0, 50.0, 100.0])
        timeline = build_timeline(events)
        assert timeline[0].cluster_id == timeline[1].cluster_id == timeline[2].cluster_id

    def test_events_beyond_100ms_get_different_cluster(self) -> None:
        events = self._make_events([0.0, 200.0])
        timeline = build_timeline(events)
        assert timeline[0].cluster_id != timeline[1].cluster_id

    def test_empty_input_returns_empty(self) -> None:
        assert build_timeline([]) == []


# ---------------------------------------------------------------------------
# link_assertions
# ---------------------------------------------------------------------------


class TestLinkAssertions:
    def _make_events(self, specs: list[tuple[ReplayEventType, float, dict]]) -> list:
        from testing.models import ReplayEvent

        return [
            ReplayEvent(type=t, offset_ms=offset, detail=detail)
            for t, offset, detail in specs
        ]

    def test_links_failing_assertion_to_test(self) -> None:
        events = self._make_events([
            (ReplayEventType.ASSERTION, 500.0, {"type": "expect", "error": "Failed"}),
        ])
        result = _failing_result("t001")
        linked = link_assertions(events, result)
        assert linked[0].linked_assertion_id == "t001"

    def test_links_dom_event_within_500ms_before_failure(self) -> None:
        events = self._make_events([
            (ReplayEventType.DOM_ACTION, 100.0, {}),    # 400ms before → within window
            (ReplayEventType.ASSERTION, 500.0, {"type": "expect", "error": "fail"}),
        ])
        result = _failing_result("t001")
        linked = link_assertions(events, result)
        assert linked[0].linked_assertion_id == "t001"

    def test_does_not_link_dom_event_600ms_before_failure(self) -> None:
        events = self._make_events([
            (ReplayEventType.DOM_ACTION, 0.0, {}),     # 600ms before → outside window
            (ReplayEventType.ASSERTION, 600.0, {"type": "expect", "error": "fail"}),
        ])
        result = _failing_result("t001")
        linked = link_assertions(events, result)
        # DOM event at 0ms, assertion at 600ms → window is 100–600ms → 0ms is outside
        assert linked[0].linked_assertion_id is None

    def test_does_not_link_events_for_passing_test(self) -> None:
        events = self._make_events([
            (ReplayEventType.ASSERTION, 0.0, {"type": "expect", "error": "fail"}),
        ])
        result = _passing_result("t001")
        linked = link_assertions(events, result)
        assert linked[0].linked_assertion_id is None

    def test_does_not_link_assertion_without_error(self) -> None:
        events = self._make_events([
            (ReplayEventType.ASSERTION, 0.0, {"type": "expect"}),  # no "error" key
        ])
        result = _failing_result("t001")
        linked = link_assertions(events, result)
        assert linked[0].linked_assertion_id is None

    def test_returns_events_unchanged_when_no_failing_assertions(self) -> None:
        events = self._make_events([
            (ReplayEventType.DOM_ACTION, 0.0, {}),
        ])
        result = _failing_result("t001")
        linked = link_assertions(events, result)
        # No ASSERTION events with errors — nothing should be linked
        assert linked[0].linked_assertion_id is None
