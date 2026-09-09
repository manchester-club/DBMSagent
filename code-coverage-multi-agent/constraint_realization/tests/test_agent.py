from __future__ import annotations

import unittest
from pathlib import Path

from constraint_realization.agent import (
    AgentConfig,
    ConstraintAgent,
    parse_react_action,
    run_agent,
    run_scripted,
)
from constraint_realization.execute import ExecResult
from constraint_realization.extract import extract
from constraint_realization.instantiate import instantiate
from constraint_realization.recover import recover

ROOT = Path(__file__).resolve().parent / "fixtures" / "pg_mini"


def _cfg(**kwargs) -> AgentConfig:
    base = dict(
        pg_src=ROOT,
        use_llm_instantiate=False,
        use_llm_supervisor=False,
        do_execute=False,
        max_steps=40,
        max_retries=3,
    )
    base.update(kwargs)
    return AgentConfig(**base)


class ParseReAct(unittest.TestCase):
    def test_action_and_json_input(self):
        thought, action, args = parse_react_action(
            "Thought: scan first\nAction: scan_leftovers\nAction Input: {}"
        )
        self.assertEqual(action, "scan_leftovers")
        self.assertEqual(args, {})
        self.assertIn("scan", thought)

    def test_bare_family_id(self):
        _, action, args = parse_react_action(
            "Action: recover_family\nAction Input: pg_foo.foopend"
        )
        self.assertEqual(action, "recover_family")
        self.assertEqual(args["family_id"], "pg_foo.foopend")


class ToolContract(unittest.TestCase):
    def test_instantiate_requires_recover(self):
        agent = ConstraintAgent(_cfg())
        agent.tools.scan_leftovers()
        out = agent.tools.instantiate_plan("pg_foo.foopend")
        self.assertIn("recover_family first", out["error"])
        rec = agent.tools.recover_family("pg_foo.foopend")
        self.assertTrue(rec["recoverable"])
        self.assertIn("DETACH PARTITION", rec["sql_template"])
        plan = agent.tools.instantiate_plan("pg_foo.foopend")
        self.assertNotIn("error", plan)
        self.assertIn("DETACH", plan["plan"]["writer"][0])

    def test_instantiate_prompt_carries_feedback_not_c_names(self):
        bar = extract(ROOT, "src/backend/catalog/pg_foo.c:18")
        rel = recover(ROOT, bar)
        seen = {}

        def fake_llm(prompt: str) -> str:
            seen["prompt"] = prompt
            return """{
              "setup": ["CREATE TABLE t_p (a int)"],
              "holder": ["SELECT 1"],
              "writer": ["ALTER TABLE t_p ENABLE ALWAYS"],
              "observer": ["SELECT * FROM t_p"],
              "teardown": ["DROP TABLE t_p CASCADE"]
            }"""

        plan = instantiate(
            rel, prefix="t", completer=fake_llm, feedback="holder died early"
        )
        self.assertEqual(plan.via, "llm")
        self.assertIn("previous_attempt_failed=holder died early", seen["prompt"])
        self.assertNotIn("MarkFooPending", seen["prompt"])
        self.assertIn("sql_template=", seen["prompt"])


class ScriptedAgent(unittest.TestCase):
    def test_scripted_covers_both_pc_v_families(self):
        report = run_agent(_cfg())
        self.assertTrue(report["finished"])
        families = {f["family"]: f for f in report["families"]}
        self.assertEqual(families["pg_foo.foopend"]["verdict"], "RECOVERED")
        self.assertEqual(families["pg_foo.barflag"]["verdict"], "RECOVERED")
        self.assertIn("DETACH PARTITION", families["pg_foo.foopend"]["sql_template"])
        self.assertIn("ENABLE ALWAYS", families["pg_foo.barflag"]["sql_template"])
        env = [f for f in report["families"] if f["kind"] == "ENV"]
        self.assertTrue(env)
        self.assertEqual(env[0]["verdict"], "CONDITIONALLY")
        actions = [t["action"] for t in report["trace"]]
        self.assertIn("scan_leftovers", actions)
        self.assertIn("recover_family", actions)
        self.assertIn("instantiate_plan", actions)
        inst_at = actions.index("instantiate_plan")
        rec_at = actions.index("recover_family")
        self.assertLess(rec_at, inst_at)

    def test_retry_on_execute_failure(self):
        hits = {"n": 0}

        def flaky(plan):
            hits["n"] += 1
            if hits["n"] == 1:
                return ExecResult(False, False, "", "", "", ["syntax error"])
            return ExecResult(True, True, "t", "", "", ["ok"])

        def always_ok(_target):
            return type("V", (), {"ok": True, "then_gained": [9]})()

        report = run_scripted(
            ConstraintAgent(
                _cfg(do_execute=True, execute_fn=flaky, verify_fn=always_ok, target="src/backend/catalog/pg_foo.c:8")
            )
        )
        fam = report["families"][0]
        self.assertEqual(fam["family"], "pg_foo.foopend")
        self.assertEqual(fam["verdict"], "REALIZABLE")
        self.assertGreaterEqual(fam["attempts"], 2)
        self.assertEqual(hits["n"], 2)


class ReActSupervisor(unittest.TestCase):
    def test_scripted_replies_must_recover_before_instantiate(self):
        replies = [
            "Thought: scan\nAction: scan_leftovers\nAction Input: {}",
            "Thought: skip recover illegally\nAction: instantiate_plan\nAction Input: {\"family_id\": \"pg_foo.foopend\"}",
            "Thought: recover now\nAction: recover_family\nAction Input: pg_foo.foopend",
            "Thought: instantiate\nAction: instantiate_plan\nAction Input: {\"family_id\": \"pg_foo.foopend\"}",
            "Thought: done this family\nAction: record_verdict\nAction Input: {\"family_id\": \"pg_foo.foopend\", \"verdict\": \"RECOVERED\"}",
            "Thought: recover bar\nAction: recover_family\nAction Input: pg_foo.barflag",
            "Thought: instantiate bar\nAction: instantiate_plan\nAction Input: {\"family_id\": \"pg_foo.barflag\"}",
            "Thought: done bar\nAction: record_verdict\nAction Input: {\"family_id\": \"pg_foo.barflag\", \"verdict\": \"RECOVERED\"}",
            "Thought: env\nAction: record_verdict\nAction Input: {\"family_id\": \"ENV:src/backend/catalog/objectaccess.c:4\", \"verdict\": \"CONDITIONALLY\"}",
            "Thought: named sql\nAction: record_verdict\nAction Input: {\"family_id\": \"NAMED_SQL:src/backend/utils/adt/acl.c:4\", \"verdict\": \"NAMED_SQL\"}",
            "Thought: stop\nAction: finish\nAction Input: {}",
        ]
        i = {"n": 0}

        def supervisor(*, messages, system):
            self.assertIn("recover_family BEFORE instantiate_plan", system)
            text = replies[min(i["n"], len(replies) - 1)]
            i["n"] += 1
            return text

        report = run_agent(
            _cfg(use_llm_supervisor=True, supervisor_complete=supervisor)
        )
        actions = [t["action"] for t in report["trace"]]
        self.assertEqual(actions[0], "scan_leftovers")
        self.assertEqual(actions[1], "instantiate_plan")
        self.assertIn("recover_family first", report["trace"][1]["observation"]["error"])
        self.assertEqual(actions[2], "recover_family")
        self.assertEqual(actions[3], "instantiate_plan")
        families = {f["family"]: f for f in report["families"]}
        self.assertEqual(families["pg_foo.foopend"]["verdict"], "RECOVERED")
        self.assertEqual(families["pg_foo.barflag"]["verdict"], "RECOVERED")
        self.assertTrue(report["finished"])


if __name__ == "__main__":
    unittest.main()
