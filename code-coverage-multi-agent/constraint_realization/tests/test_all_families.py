from __future__ import annotations

import json
import unittest
from pathlib import Path

from constraint_realization.extract import extract
from constraint_realization.instantiate import instantiate
from constraint_realization.leftover import scan_guard_gaps
from constraint_realization.pipeline import run_all
from constraint_realization.recover import recover
from constraint_realization.split import split_constraint

ROOT = Path(__file__).resolve().parent / "fixtures" / "pg_mini"


class SplitAndRecover(unittest.TestCase):
    def test_two_pc_v_families_from_same_catalog(self):
        foo = extract(ROOT, "src/backend/catalog/pg_foo.c:8")
        bar = extract(ROOT, "src/backend/catalog/pg_foo.c:18")
        self.assertEqual(split_constraint(foo).kind, "PC_V")
        self.assertEqual(split_constraint(bar).kind, "PC_V")
        self.assertEqual(foo.field, "foopend")
        self.assertEqual(bar.field, "barflag")

        rel_foo = recover(ROOT, foo)
        rel_bar = recover(ROOT, bar)
        self.assertTrue(rel_foo.recoverable, rel_foo.notes)
        self.assertIn("DETACH PARTITION", rel_foo.sql_template)
        self.assertIn("CONCURRENTLY", rel_foo.sql_template)
        self.assertTrue(rel_foo.wait_for_lockers)
        self.assertTrue(rel_foo.prevent_in_xact)

        self.assertTrue(rel_bar.recoverable, rel_bar.notes)
        self.assertIn("ENABLE ALWAYS", rel_bar.sql_template)
        self.assertFalse(rel_bar.wait_for_lockers)

    def test_instantiate_follows_recovered_template_not_hardcoded_detach(self):
        bar = extract(ROOT, "src/backend/catalog/pg_foo.c:18")
        rel = recover(ROOT, bar)
        plan = instantiate(rel, prefix="t")
        self.assertIn("ENABLE ALWAYS", plan.writer.statements[0])
        self.assertNotIn("DETACH", plan.writer.statements[0])


class ScanAll(unittest.TestCase):
    def test_all_groups_by_family_and_kind(self):
        report = run_all(ROOT, do_execute=False)
        kinds = report["kind_counts"]
        self.assertGreaterEqual(kinds.get("PC_V", 0), 2)
        self.assertGreaterEqual(kinds.get("NAMED_SQL", 0), 1)
        self.assertGreaterEqual(kinds.get("ENV", 0), 1)
        families = {f["family"]: f for f in report["families"]}
        self.assertIn("pg_foo.foopend", families)
        self.assertIn("pg_foo.barflag", families)
        self.assertEqual(families["pg_foo.foopend"]["verdict"], "RECOVERED")
        self.assertEqual(families["pg_foo.barflag"]["verdict"], "RECOVERED")
        self.assertIn("DETACH PARTITION", families["pg_foo.foopend"]["sql_template"])
        self.assertIn("ENABLE ALWAYS", families["pg_foo.barflag"]["sql_template"])
        env = [f for f in report["families"] if f["kind"] == "ENV"]
        self.assertTrue(env)
        self.assertEqual(env[0]["verdict"], "CONDITIONALLY")
        named = [f for f in report["families"] if f["kind"] == "NAMED_SQL"]
        self.assertTrue(named)


if __name__ == "__main__":
    unittest.main()
