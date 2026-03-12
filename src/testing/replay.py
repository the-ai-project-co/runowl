"""Session replay: parse Playwright trace archives into structured event timelines.

Playwright's `trace: 'on-first-retry'` option produces a .zip file containing:
  - trace.json  — actions, network requests, console messages
  - Various snapshot and resource files

This module:
1. Parses trace.json into typed ReplayEvent objects  (parse_trace)
2. Builds a sorted, clustered event timeline          (build_timeline)
3. Links events to failing test assertions            (link_assertions)

The resulting event lists are stored on TestResult.replay_events and consumed
by the Phase 2B UI (session replay player).
"""

from __future__ import annotations

import json
import logging
import zipfile

from testing.models import ReplayEvent, ReplayEventType, TestResult

logger = logging.getLogger(__name__)

# Events within this window (ms) are assigned the same cluster_id
_CLUSTER_WINDOW_MS = 100.0

# Events within this window before a failing assertion are linked to it
_ASSERTION_PRE_WINDOW_MS = 500.0


# ---------------------------------------------------------------------------
# Parse Playwright trace → ReplayEvent list
# ---------------------------------------------------------------------------


def parse_trace(trace_zip_path: str) -> list[ReplayEvent]:
    """
    Open a Playwright trace .zip and return a flat list of ReplayEvent objects.

    Handles three event categories:
    - DOM actions   (from "actions" array — clicks, fills, navigations, etc.)
    - Network       (from "resources" / "network" arrays)
    - Console logs  (from "console" array)

    Returns [] on any parse error without raising.
    """
    if not trace_zip_path:
        return []

    try:
        with zipfile.ZipFile(trace_zip_path, "r") as zf:
            if "trace.json" not in zf.namelist():
                return []
            data = json.loads(zf.read("trace.json"))
    except (zipfile.BadZipFile, json.JSONDecodeError, OSError) as exc:
        logger.debug("Could not read trace %s: %s", trace_zip_path, exc)
        return []

    events: list[ReplayEvent] = []

    # Determine epoch offset from first action (so all offsets start near 0)
    actions = data.get("actions", [])
    first_ts = actions[0].get("startTime", 0) if actions else 0

    # --- DOM actions ---
    for action in actions:
        start_time = action.get("startTime", first_ts)
        offset_ms = max(0.0, start_time - first_ts)

        action_type = action.get("type", "")
        # Playwright uses "type" for low-level events and "title" for human-readable step names
        is_assertion = action_type in ("expect", "assert") or action.get("method") in (
            "expect",
            "assert",
        )
        evt_type = ReplayEventType.ASSERTION if is_assertion else ReplayEventType.DOM_ACTION

        events.append(
            ReplayEvent(
                type=evt_type,
                offset_ms=offset_ms,
                detail={
                    "title": action.get("title") or action_type,
                    "type": action_type,
                    "method": action.get("method"),
                    "selector": action.get("selector"),
                    "error": action.get("error"),
                },
            )
        )

    # --- Network requests ---
    for resource in data.get("resources", []) + data.get("network", []):
        ts = resource.get("timestamp", first_ts)
        offset_ms = max(0.0, ts - first_ts)
        events.append(
            ReplayEvent(
                type=ReplayEventType.NETWORK_REQUEST,
                offset_ms=offset_ms,
                detail={
                    "url": resource.get("url", ""),
                    "method": resource.get("method", "GET"),
                    "status": resource.get("status"),
                    "duration_ms": resource.get("time"),
                },
            )
        )

    # --- Console messages ---
    for msg in data.get("console", []):
        ts = msg.get("timestamp", first_ts)
        offset_ms = max(0.0, ts - first_ts)
        events.append(
            ReplayEvent(
                type=ReplayEventType.CONSOLE_LOG,
                offset_ms=offset_ms,
                detail={
                    "text": msg.get("text", ""),
                    "level": msg.get("type", "log"),
                },
            )
        )

    return events


# ---------------------------------------------------------------------------
# Build timeline (sort + cluster)
# ---------------------------------------------------------------------------


def build_timeline(events: list[ReplayEvent]) -> list[ReplayEvent]:
    """
    Sort events by offset_ms and assign cluster_id to events within
    a 100 ms window of each other.

    Returns a new sorted list with cluster_id set in-place on each event.
    """
    sorted_events = sorted(events, key=lambda e: e.offset_ms)

    cluster_id = 0
    cluster_start = 0.0

    for i, event in enumerate(sorted_events):
        if i == 0:
            cluster_start = event.offset_ms
            event.cluster_id = cluster_id
        elif event.offset_ms - cluster_start <= _CLUSTER_WINDOW_MS:
            event.cluster_id = cluster_id
        else:
            cluster_id += 1
            cluster_start = event.offset_ms
            event.cluster_id = cluster_id

    return sorted_events


# ---------------------------------------------------------------------------
# Link replay events to assertion failures
# ---------------------------------------------------------------------------


def link_assertions(events: list[ReplayEvent], test_result: TestResult) -> list[ReplayEvent]:
    """
    When a test has failed, find ASSERTION events with an error in the trace
    and mark them (and DOM/network events in the 500 ms before the failure)
    with linked_assertion_id = test_result.test_id.

    Returns the modified event list (same objects, mutated in-place).
    """
    if not test_result.failed:
        return events

    # Find failing assertion events
    failing_assertion_offsets: list[float] = []
    for event in events:
        if event.type == ReplayEventType.ASSERTION and event.detail.get("error"):
            event.linked_assertion_id = test_result.test_id
            failing_assertion_offsets.append(event.offset_ms)

    if not failing_assertion_offsets:
        return events

    # Link events that occurred just before each failing assertion
    for event in events:
        if event.linked_assertion_id:
            continue  # already linked
        for assertion_offset in failing_assertion_offsets:
            pre_window_start = assertion_offset - _ASSERTION_PRE_WINDOW_MS
            if pre_window_start <= event.offset_ms < assertion_offset:
                event.linked_assertion_id = test_result.test_id
                break

    return events
