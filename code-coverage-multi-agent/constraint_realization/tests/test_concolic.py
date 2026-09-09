from __future__ import annotations

import unittest
from pathlib import Path

from constraint_realization.agent import AgentConfig, ConstraintAgent, run_agent
from constraint_realization.concolic import leftover_condition, realize, wrap_sql
from constraint_realization.extract import extract
from constraint_realization.split import split_constraint

ROOT = Path(__file__).resolve().parent / "fixtures" / "pg_mini"


class SliceVsCallers(unittest.TestCase):
    def test_timestr_branch_is_sat_over_a(self):
        t = extract(ROOT, "src/backend/utils/adt/datetime.c:6")
        self.assertEqual(split_constraint(t).kind, "PC_A")
        ir = realize(ROOT, t)
        self.assertEqual(ir.status, "SAT")
        self.assertTrue(ir.sat_on_slice)
        self.assertTrue(ir.realizable_under_callers)
        self.assertTrue(ir.model and ir.model[0] == ":")
        self.assertIn("TIME", wrap_sql(t, ir.model or ""))
        self.assertIn(ir.model, ir.sql or "")
        self.assertEqual(ir.verdict, "INPUT_REALIZED")

    def test_tzp_null_slice_sat_is_not_coverage(self):
        t = extract(ROOT, "src/backend/utils/adt/datetime.c:16")
        self.assertEqual(t.field, "tzp")
        self.assertEqual(split_constraint(t).kind, "UNREALIZABLE")
        ir = realize(ROOT, t)
        self.assertTrue(ir.sat_on_slice, ir.notes)
        self.assertFalse(ir.realizable_under_callers)
        self.assertEqual(ir.status, "UNREALIZABLE")
        self.assertIsNone(ir.sql)
        self.assertEqual(ir.verdict, "UNREALIZABLE UNDER A,E,B")
        self.assertIn("&tz", ir.evidence.get("callers_tzp", ""))

    def test_catalog_leftover_is_wrong_solver(self):
        t = extract(ROOT, "src/backend/catalog/pg_foo.c:8")
        ir = realize(ROOT, t)
        self.assertEqual(ir.status, "WRONG_SOLVER")
        self.assertFalse(ir.sat_on_slice)

    def test_leftover_condition_extract(self):
        self.assertEqual(leftover_condition("if (timestr[0] == ':')"), "timestr[0] == ':'")
        self.assertEqual(leftover_condition("if (tzp == NULL)"), "tzp == NULL")


class AgentConcolic(unittest.TestCase):
    def test_realize_input_rejects_pc_v_catalog(self):
        agent = ConstraintAgent(
            AgentConfig(
                pg_src=ROOT,
                use_llm_instantiate=False,
                use_llm_supervisor=False,
            )
        )
        agent.tools.scan_leftovers()
        out = agent.tools.realize_input("pg_foo.foopend")
        self.assertIn("Do not SMT-symbolize catalog memory", out["error"])
        rec = agent.tools.recover_family("pg_foo.foopend")
        self.assertTrue(rec["recoverable"])

    def test_scripted_agent_runs_concolic_on_pc_a(self):
        report = run_agent(
            AgentConfig(
                pg_src=ROOT,
                use_llm_instantiate=False,
                use_llm_supervisor=False,
            )
        )
        families = {f["family"]: f for f in report["families"]}
        pca = [f for f in report["families"] if f["kind"] == "PC_A"]
        self.assertTrue(pca, families.keys())
        self.assertEqual(pca[0]["verdict"], "INPUT_REALIZED")
        self.assertTrue(pca[0]["sql"].startswith("SELECT TIME"))
        tzp = [f for f in report["families"] if f["kind"] == "UNREALIZABLE"]
        self.assertTrue(tzp)
        self.assertEqual(tzp[0]["verdict"], "UNREALIZABLE UNDER A,E,B")
        self.assertTrue(tzp[0]["sat_on_slice"])
        actions = [t["action"] for t in report["trace"]]
        self.assertIn("realize_input", actions)
        rec_at = actions.index("recover_family")
        rel_at = actions.index("realize_input")
        self.assertNotEqual(rec_at, rel_at)


if __name__ == "__main__":
    unittest.main()
