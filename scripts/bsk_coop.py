"""BrowserSkill 0.4 shared control: one `cooperate sync` context per page action.

From protocol 1.7 the daemon rejects every page action (navigate after the first, evaluate,
click, fill, select, press, tab close, ...) unless it carries `--context <id>` from the latest
`bsk cooperate sync` of that tab. Each context is single-use. A rejection is reported before
dispatch as `reason: cooperation_sync_required` with `effect_state: none`, so the action did not
run; callers wait, sync again and re-send at most COOP_RETRIES times. Any other outcome is the
caller's ordinary error handling, and an unknown effect is never re-sent.

Pages the extension cannot observe (about:blank, chrome://) fail the sync; the action is then
sent without a context and the daemon decides. Older CLIs without `cooperate` behave the same.
"""
from __future__ import annotations

import json
from typing import Callable

# (returncode, stdout, stderr) for `bsk <args>` bound to the caller's session and tab.
Runner = Callable[[list[str]], "tuple[int, str, str]"]

# Reads and session/tab bookkeeping that the daemon accepts without a context.
PASSIVE = {"status", "browsers", "daemon", "doctor", "logs", "session", "window", "cooperate",
           "snapshot", "screenshot", "console", "network", "get-html", "view", "observe",
           "install-skill", "update", "dialog", "operation"}
COOP_RETRIES = 3
WAIT_MS = "5000"
SYNC_TOKENS = "200"   # the runner never reads the observation; keep the reply small


def needs_context(args: list[str]) -> bool:
    if not args:
        return False
    if args[0] == "tab":                 # create/list/select are bookkeeping; close acts on the page
        return len(args) > 1 and args[1] == "close"
    return args[0] not in PASSIVE


def sync_required(text: str) -> bool:
    return "cooperation_sync_required" in text


def context_args(run: Runner) -> list[str]:
    """`--context <id>` from a fresh sync, or [] when this page/CLI has no shared control."""
    # --settle lets bsk absorb a transient read-only refusal ("A page frame is not responding" on a
    # background tab) with its own bounded wait+sync; it never repeats a browser action.
    code, out, _ = run(["cooperate", "sync", "--settle", "--max-tokens", SYNC_TOKENS, "--json"])
    if code != 0:
        return []
    try:
        context = json.loads(out).get("context_id")
    except (ValueError, AttributeError):
        return []
    return ["--context", str(context)] if context else []


SELF_REVOKED = "User activity revoked this action"
# bsk 0.4.0 sometimes stamps the agent's own trusted input a fraction of a millisecond before the
# window it expects for that input (measured 0.4 ms early, #167) and then revokes the action as
# human activity. The input was delivered exactly once (30-click probe: every revoked click
# produced one pointerdown/up/click). Only an event of the expected type whose timestamp lies
# within this tolerance of bsk's own expected window counts as the agent's input.
SELF_EVENT_TOLERANCE_MS = 5.0


def self_revocation(run: Runner) -> list[dict] | None:
    """The activity records if every one is the agent's own mis-attributed input, else None.

    Reads `cooperate status` (it does not consume activity, unlike sync). Any record without
    bsk's own attribution, of another type, or outside the tolerance is treated as a real person.
    """
    code, out, _ = run(["cooperate", "status", "--json"])
    if code != 0:
        return None
    try:
        activity = json.loads(out).get("activity") or []
    except (ValueError, AttributeError):
        return None
    if not activity:
        return None
    for item in activity:
        attribution = item.get("attribution") if isinstance(item, dict) else None
        window = (attribution or {}).get("expected_event_time") or {}
        stamp = (attribution or {}).get("event_timestamp")
        if (not attribution or item.get("type") != attribution.get("expected_type")
                or not isinstance(stamp, (int, float))
                or not isinstance(window.get("earliest"), (int, float))
                or not isinstance(window.get("latest"), (int, float))
                or not (window["earliest"] - SELF_EVENT_TOLERANCE_MS <= stamp
                        <= window["latest"] + SELF_EVENT_TOLERANCE_MS)):
            return None
    return activity


def wait(run: Runner) -> None:
    """Let a person's hold or a settling page finish before the next sync (bounded by bsk)."""
    run(["cooperate", "wait", "--timeout-ms", WAIT_MS, "--json"])


def _compact(text: str) -> str:
    return text.replace(" ", "").replace("\n", "")


def dispatch(run: Runner, args: list[str]) -> "tuple[int, str, str]":
    """Send one bsk command with the shared-control rules; used by the login gate and examples.

    `run` executes `bsk <argv>` bound to the caller's session (and tab) under the caller's lease.
    Passive commands go straight through. A page action gets a fresh context; a refusal before
    dispatch is waited out and re-sent at most COOP_RETRIES times; the 0.4.0 self-attribution
    revocation becomes success with `{"self_revoked": true, "activity": [...]}` as its output.
    Everything else (including an unknown effect) is returned unchanged for the caller to raise.
    """
    if not needs_context(args):
        return run(args)
    for attempt in range(COOP_RETRIES + 1):
        code, out, err = run(args + context_args(run))
        text = _compact(err or out)
        if code == 0:
            return code, out, err
        if sync_required(text) and '"effect_state":"none"' in text and attempt < COOP_RETRIES:
            wait(run)
            continue
        if SELF_REVOKED.replace(" ", "") in text and '"effect_state":"unknown"' in text:
            own = self_revocation(run)
            if own is not None:
                return 0, json.dumps({"self_revoked": True, "activity": own}), ""
        return code, out, err
    return code, out, err


def dismiss_pending(run_session: Runner, text: str) -> dict | None:
    """Dismiss the native dialog that suspended an action (bsk >= protocol 1.5); return it.

    The action already ran, so the caller must treat its effect as unknown and never re-send it.
    Dismissing frees the session at once instead of leaving it blocked for bsk's 60 s deadline.
    """
    if '"reason":"dialog_pending"' not in _compact(text):
        return None
    try:
        dialog = (json.loads(text).get("data") or {}).get("dialog") or {}
    except ValueError:
        return None
    if dialog.get("id"):
        run_session(["dialog", "dismiss", str(dialog["id"]), "--json"])
    return dialog
