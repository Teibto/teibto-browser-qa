from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import bsk_coop  # noqa: E402


class FakeCli:
    """`bsk` as seen by bsk_coop: a sync reply, a help text and scripted action replies."""

    def __init__(self, *, help_text="--context <CONTEXT>\n--observation <OBSERVATION>", observation=True,
                 replies=None):
        self.help_text, self.observation = help_text, observation
        self.replies = list(replies or [(0, "{}", "")])
        self.calls: list[list[str]] = []
        self.syncs = 0

    def __call__(self, argv: list[str]):
        self.calls.append(argv)
        if argv[:2] == ["cooperate", "sync"]:
            self.syncs += 1
            reply = {"context_id": f"ctx-{self.syncs}"}
            if self.observation:
                reply["observation_id"] = f"obs-{self.syncs}"
            return 0, json.dumps(reply), ""
        if argv[:2] == ["cooperate", "wait"]:
            return 0, "{}", ""
        if argv == ["click", "--help"]:
            return 0, self.help_text, ""
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]

    def actions(self):
        return [c for c in self.calls if c[0] not in ("cooperate",) and c != ["click", "--help"]]


def refusal(reason: str, effect: str) -> tuple[int, str, str]:
    return 1, "", json.dumps({"code": "permission_denied", "data": {"effect_state": effect, "reason": reason}})


class CoopTests(unittest.TestCase):
    def setUp(self) -> None:
        bsk_coop._OBSERVATION_FLAG = None          # the capability probe is cached per process

    def test_protocol_18_sends_context_and_observation_from_the_same_sync(self):
        cli = FakeCli()
        self.assertEqual(0, bsk_coop.dispatch(cli, ["fill", "--selector", "#email", "--value", "x"])[0])
        self.assertEqual(["fill", "--selector", "#email", "--value", "x",
                          "--context", "ctx-1", "--observation", "obs-1"], cli.actions()[0])

    def test_cli_without_the_flag_gets_context_only(self):
        cli = FakeCli(help_text="--context <CONTEXT>")              # bsk 0.4.0
        bsk_coop.dispatch(cli, ["click", "--selector", "#go"])
        self.assertEqual(["click", "--selector", "#go", "--context", "ctx-1"], cli.actions()[0])

    def test_sync_without_observation_gets_context_only(self):
        cli = FakeCli(observation=False)
        bsk_coop.dispatch(cli, ["click", "--selector", "#go"])
        self.assertNotIn("--observation", cli.actions()[0])

    def test_control_context_invalid_before_dispatch_is_sent_again_with_a_new_sync(self):
        cli = FakeCli(replies=[refusal("control_context_invalid", "none"), (0, "{}", "")])
        self.assertEqual(0, bsk_coop.dispatch(cli, ["click", "--selector", "#login-submit"])[0])
        sent = cli.actions()
        self.assertEqual(2, len(sent))
        self.assertIn("obs-1", sent[0])
        self.assertIn("obs-2", sent[1])                             # never reuse an observation

    def test_unknown_effect_is_never_sent_again(self):
        cli = FakeCli(replies=[refusal("control_context_invalid", "unknown"), (0, "{}", "")])
        self.assertEqual(1, bsk_coop.dispatch(cli, ["click", "--selector", "#login-submit"])[0])
        self.assertEqual(1, len(cli.actions()))

    def test_passive_commands_need_no_sync(self):
        cli = FakeCli()
        bsk_coop.dispatch(cli, ["snapshot"])
        self.assertEqual([["snapshot"]], cli.calls)


if __name__ == "__main__":
    unittest.main()
