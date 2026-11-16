import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from memleak_admissibility import adapter as ml  # noqa: E402

TERMS = {d: v[0] + v[1] for d, v in ml.DOMAINS.items()}


class FixtureTests(unittest.TestCase):
    def test_deterministic_and_variants_differ(self):
        a = ml.build_fixture("cold")
        digest = ml.fixture_digest
        self.assertEqual(digest(a), digest(ml.build_fixture("cold")))
        for other in (ml.build_fixture("matured"),
                      ml.build_fixture("cold", "verbatim_copy")):
            self.assertNotEqual(digest(a), digest(other))
        with self.assertRaises(ValueError):
            ml.build_fixture("warm")

    def test_shape_and_entity_collisions_appear_only_when_matured(self):
        cold, matured = ml.build_fixture("cold"), ml.build_fixture("matured")
        self.assertEqual((len(cold["memories"]), len(cold["queries"])), (80, 32))
        self.assertEqual((len(cold["edges"]), len(matured["edges"])), (0, 48))
        ids = [m["id"] for m in cold["memories"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ml.owner_map(cold)), 80)
        self.assertEqual(len(ml.crafted_ids(cold)), 16)
        for q in cold["queries"]:
            own = [m for m in cold["memories"] if m["owner"] == q["querier"]]
            self.assertTrue(own and all(q["user_tag"] in m["tags"] for m in own))

        def entity_owners(fx, tier):
            out = {}
            for m in fx["memories"]:
                for t in m["tags"] if m["tier"] == tier else []:
                    if t.startswith("entity:"):
                        out.setdefault(t, set()).add(m["owner"])
            return out
        self.assertEqual(entity_owners(cold, "T0"), {})
        shared = entity_owners(matured, "T0").values()
        self.assertTrue(any(len(o) == 2 for o in shared))
        self.assertTrue(all(len(o) == 1 for o in entity_owners(matured, "T3").values()))

    def test_adjacency_gradient_and_control(self):
        fx, by_tier = ml.build_fixture("cold"), {}
        for q in fx["queries"]:
            theirs = " ".join(m["content"] for m in fx["memories"]
                              if m["kind"] == "organic" and m["tier"] == q["tier"]
                              and m["owner"] != q["querier"])
            hit = sum(t in theirs for t in TERMS[q["domain"]] if t in q["text"])
            by_tier.setdefault(q["tier"], []).append(hit)
        m = [sum(by_tier[t]) / len(by_tier[t]) for t in ("T0", "T1", "T2", "T3")]
        self.assertEqual(m[3], 0)
        self.assertTrue(m[0] >= m[1] >= m[2] > m[3])


class PlanTests(unittest.TestCase):
    def test_plan_size_params_and_no_label_leakage(self):
        fx = ml.build_fixture("matured")
        plan, ids = ml.build_plan(fx), {m["id"] for m in fx["memories"]}
        self.assertEqual(len(plan), len(ml.ARMS) * 32)
        for e in plan:
            blob = json.dumps(e["request"])
            self.assertLessEqual(set(e["request"]["params"]), ml.RECALL_PARAMS)
            self.assertFalse(any(i in blob for i in ids) or "crafted" in blob)

    def test_arm_shapes_and_prefix_scope(self):
        fx = ml.build_fixture("cold")
        q = fx["queries"][0]
        req = {a: ml.arm_request(a, q) for a in ml.ARMS}
        self.assertEqual(req["pooled_user_exact"][1]["tag_match"], "exact")
        self.assertEqual(req["pooled_org_prefix"][1]["tag_match"], "prefix")
        self.assertNotIn("tags", req["partitioned"][1])
        self.assertEqual(req["partitioned"][0], f"user:{q['querier']}")
        respect = req["pooled_user_exact_expand_respect"][1]
        self.assertTrue(respect["expand_respect_tags"])
        self.assertNotIn("expand_respect_tags", req["pooled_user_exact_expand"][1])
        for arm in ("pooled_overfetch_owner_gate", "pooled_user_exact_scope_fallback"):
            self.assertEqual(req[arm][1]["limit"], ml.OVER_FETCH)
        self.assertEqual(req["pooled_overfetch_owner_gate"][2]["keep"], ml.K)
        with self.assertRaises(ValueError):
            ml.arm_request("pooled_everything", q)
        for q in fx["queries"]:  # company prefix reaches the other user, except T3
            other = next(m for m in fx["memories"] if m["kind"] == "organic"
                         and m["tier"] == q["tier"] and m["owner"] != q["querier"])
            self.assertEqual(other["tags"][0].startswith(q["company_tag"] + ":"),
                             q["tier"] != "T3")


class GateAndClassifierTests(unittest.TestCase):
    Q = {"query_id": "q", "tier": "T0", "querier": "mira"}
    OWN = {"a": "mira", "b": "mira", "c": "noel", "d": "noel", "m": "mallory-t0"}

    def res(self, mid, score=0.5, **extra):
        return {"id": mid, "final_score": score, "relations": [], **extra}

    def classify(self, results, owners=None, crafted=(), k=3):
        return ml.classify_response(self.Q, {"results": results},
                                    owners or self.OWN, set(crafted), k)

    def test_gate_fails_closed_and_scrubs_inline_content(self):
        own = {"id": "a", "tags": ["tenant:acme-t0:platform:mira"], "content": "x"}
        other = {"id": "c", "tags": ["tenant:acme-t0:platform:noel"], "content": "y"}
        results = [
            {"id": "a", "memory": own, "relations": [
                {"type": "RELATES_TO", "memory": other}]},
            {"id": "c", "memory": other}, {"id": "z", "memory": {"id": "z"}}]
        gated = ml.apply_owner_gate(results, "mira", keep=3)
        self.assertEqual([r["id"] for r in gated], ["a"])
        self.assertEqual(gated[0]["relations"][0]["memory"], {"id": "c"})

    def test_direct_leak_rank_gap_and_crafted(self):
        row = self.classify([self.res("a", 0.9), self.res("m", 0.6), self.res("c")],
                            crafted={"m"})
        self.assertTrue(row["leaked"])
        self.assertEqual((row["first_cross_rank"], row["crafted_in_topk"]), (2, 1))
        self.assertEqual(row["channels"], {"direct": 2})
        self.assertAlmostEqual(row["score_gap"], 0.6 - 0.9)

    def test_clean_underfilled_and_leak_beyond_topk(self):
        clean = self.classify([self.res("a")])
        self.assertEqual((clean["leaked_any_channel"], clean["underfill"]),
                         (False, True))
        late = self.classify([self.res("a"), self.res("b"), self.res("a2"),
                              self.res("c", outside_tag_scope=True)],
                             owners=dict(self.OWN, a2="mira"))
        self.assertEqual((late["leaked"], late["leaked_any_channel"]), (False, True))
        self.assertEqual(late["channels"], {"scope_fallback": 1})

    def test_expansion_channels_and_inline_payloads(self):
        rels = [{"type": "RELATES_TO", "memory": {"id": "c", "content": "secret"}},
                {"type": "RELATES_TO", "memory": {"id": "d"}},
                {"type": "RELATES_TO", "memory": {"id": "b", "content": "own"}}]
        row = self.classify([self.res("a", relations=rels),
                             self.res("c", match_type="relation"),
                             self.res("d", match_type="entity_expansion")], k=1)
        self.assertEqual(row["channels"],
                         {"relation_expansion": 1, "entity_expansion": 1})
        self.assertEqual((row["inline_content_leaks"], row["inline_id_only"]), (1, 1))
        self.assertFalse(row["leaked"])

    def test_enriched_inline_summary_counts_as_leaked_text(self):
        # _summarize_relation_node returns `summary` and drops `content` once a
        # memory is enriched, so a foreign summary must not read as id-only.
        rels = [{"type": "RELATES_TO", "strength": 0.5,
                 "memory": {"id": "c", "summary": "Noel's salary band"}},
                {"type": "RELATES_TO", "strength": 0.5,
                 "memory": {"id": "d", "summary": "  "}}]
        row = self.classify([self.res("a", relations=rels)])
        self.assertEqual((row["inline_content_leaks"], row["inline_id_only"]), (1, 1))
        self.assertTrue(row["leaked_any_channel"])
        self.assertFalse(row["leaked"])

    def test_expansion_provenance_edges_are_not_unknown_owners(self):
        # Relation-expanded results carry edges with no `id` and no `memory`.
        edge = {"type": "RELATES_TO", "strength": 0.7, "from": "a",
                "seed_rank": 1, "seed_score": 0.9}
        row = self.classify([self.res("a"),
                             self.res("c", match_type="relation", relations=[edge])],
                            k=1)
        self.assertEqual(row["unknown_owner"], 0)
        self.assertEqual(row["channels"], {"relation_expansion": 1})
        self.assertEqual((row["inline_content_leaks"], row["inline_id_only"]), (0, 0))
        self.assertEqual(ml.aggregate([row], ["q"])["status"], "scored")
        unknown_seed = self.classify(
            [self.res("c", match_type="relation",
                      relations=[dict(edge, **{"from": "ghost"})])])
        self.assertEqual(unknown_seed["unknown_owner"], 1)

    def test_gate_keeps_provenance_edges_free_of_phantom_targets(self):
        own = {"id": "a", "tags": ["tenant:acme-t0:platform:mira"]}
        edge = {"type": "RELATES_TO", "strength": 0.7, "from": "z", "seed_rank": 1}
        gated = ml.apply_owner_gate(
            [{"id": "a", "memory": own, "relations": [edge]}], "mira", keep=3)
        self.assertEqual(gated[0]["relations"], [{"type": "RELATES_TO"}])
        self.assertEqual(self.classify(gated)["unknown_owner"], 0)

    def test_unknown_owner_is_counted_and_invalidates_aggregate(self):
        row = self.classify([self.res("ghost")])
        self.assertEqual(row["unknown_owner"], 1)
        self.assertEqual(ml.aggregate([row], ["q"])["status"], "invalid")

    def test_wilson_matches_paper_interval(self):
        self.assertEqual(ml.wilson(7, 10), [0.3968, 0.8922])
        self.assertEqual(ml.wilson(0, 10)[0], 0.0)
        self.assertIsNone(ml.wilson(0, 0))

    def test_aggregate_requires_exact_plan_coverage(self):
        r1 = self.classify([self.res("a")])
        r2 = dict(r1, query_id="q2", tier="T3")
        full = ml.aggregate([r1, r2], ["q", "q2"])
        self.assertEqual((full["status"], full["overall"]["lr"]), ("scored", 0.0))
        self.assertEqual(sorted(full["by_tier"]), ["T0", "T3"])
        for rows in ([], [r1], [r1, r1], [r1, r2, dict(r1, query_id="q3")]):
            self.assertEqual(ml.aggregate(rows, ["q", "q2"])["status"], "not_scored")


class ReportAndCliTests(unittest.TestCase):
    def test_report_is_not_scored_and_labels_cold_matured(self):
        rep = ml.build_report("t")
        self.assertEqual((rep["status"], rep["scores"]), ("not_scored", None))
        self.assertFalse(rep["paper_comparable"])
        self.assertIsNone(rep["source"]["official_code"])
        mat = rep["maturation"]
        self.assertEqual((mat["cold"]["edges"], mat["cold"]["graph"]), (0, "none"))
        self.assertEqual((mat["matured"]["status"], mat["matured"]["graph"]),
                         ("planned_not_run", "injected_oracle"))
        self.assertIsNone(mat["delta"])
        self.assertEqual(rep["automem_contract"]["tag_match_default"], "prefix")

    def test_offline_and_stdlib_only(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            ml.build_report("t")
            ml.build_plan(ml.build_fixture("matured"))
        tree = ast.parse(Path(ml.__file__).read_text(encoding="utf-8"))
        names = {a.name.split(".")[0] for n in ast.walk(tree)
                 if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree)
                  if isinstance(n, ast.ImportFrom)}
        self.assertTrue(names <= set(sys.stdlib_module_names), names)

    def test_cli_is_reproducible_and_validates_over_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for n in (1, 2):
                out, plan = Path(tmp) / f"r{n}.json", Path(tmp) / f"p{n}.jsonl"
                self.assertEqual(ml.main(["--run-id", "t", "--out", str(out),
                                          "--plan-out", str(plan)]), 0)
                outs.append((out.read_bytes(), plan.read_bytes()))
            self.assertEqual(outs[0], outs[1])
            self.assertEqual(len(outs[0][1].splitlines()), 2 * len(ml.ARMS) * 32)
            with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
                ml.main(["--run-id", "t", "--k", "5", "--over-fetch", "3"])


if __name__ == "__main__":
    unittest.main()
