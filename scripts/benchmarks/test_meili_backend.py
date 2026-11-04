import json
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import meili_backend as mb
import meili_bench as bench


class FakeMeili:
    """In-memory stand-in for MeiliClient (documents by id; records the last search body)."""

    def __init__(self):
        self.docs, self.last_search, self.settings = {}, None, {}

    def ensure_index(self, uid, dimensions=None):
        self.settings[uid] = dimensions

    def write_docs(self, uid, docs, partial=False):
        for d in docs:
            cur = self.docs.setdefault(d["id"], {}) if partial else {}
            cur.update(d)
            self.docs[d["id"]] = cur

    def delete_docs(self, uid, ids=None, filt=None):
        for i in ids or []:
            self.docs.pop(i, None)

    def search(self, uid, body):
        self.last_search = body
        hits = [dict(d, _vectors={mb.EMBEDDER: {"embeddings": [d["_vectors"][mb.EMBEDDER]]}}) for d in self.docs.values()]
        return {"hits": hits[: body["limit"]]}

    def fetch(self, uid, **body):
        rows = list(self.docs.values())
        return {"results": rows[body.get("offset", 0): body.get("offset", 0) + body["limit"]]}

    def request(self, method, path, body=None):
        return {"numberOfDocuments": len(self.docs), "embedders": {mb.EMBEDDER: {"dimensions": 3}}}


def point(pid, vec, **payload):
    return NS(id=pid, vector=vec, payload={"content": pid, "tags": ["a:b"], "timestamp": "2026-01-02T03:04:05Z", **payload})


class MeiliBackendTests(unittest.TestCase):
    def test_document_roundtrip_keeps_payload_and_derives_search_fields(self):
        doc = mb.to_document("m1", {"content": "hi", "tags": ["x", "y"], "timestamp": "2026-01-02T03:04:05Z", "metadata": {"k": 1}}, [0.1])
        self.assertEqual(doc["tag_text"], "x y")
        self.assertEqual(doc["ts_epoch"], 1767323045.0)
        self.assertEqual((doc["_vectors"], json.loads(doc["metadata_json"])), ({mb.EMBEDDER: [0.1]}, {"k": 1}))

    def test_build_filter_mirrors_baseline_where_clause(self):
        flt = mb.build_filter(tags=["a:b"], mode="any", match="prefix", excluded_types=["Artifact"], start_time="2026-01-01T00:00:00Z")
        self.assertIn("NOT archived = true", flt)
        self.assertIn('tag_prefixes IN ["a:b"]', flt)
        self.assertIn('NOT type IN ["Artifact"]', flt)
        self.assertIn("ts_epoch >= 1767225600.0", flt)
        self.assertIn('tags = "a" AND tags = "b"', mb.build_filter(tags=["a", "b"], mode="all", match="exact"))

    def test_qdrant_filter_translation_and_unsupported_condition(self):
        match_any, match_val = NS(any=["t1", "t2"]), NS(value="Artifact", any=None)
        flt = NS(must=[NS(key="tags", match=match_any)], must_not=[NS(key="type", match=match_val)], should=None)
        self.assertEqual(mb.qdrant_filter_to_meili(flt), 'tags IN ["t1", "t2"] AND NOT (type = "Artifact")')
        self.assertIsNone(mb.qdrant_filter_to_meili(None))
        with self.assertRaises(NotImplementedError):
            mb.qdrant_filter_to_meili(NS(must=[NS(key="x", match=None)], must_not=None, should=None))

    def test_apply_set_payload_handles_filter_points_nested_key_and_keeps_metadata(self):
        fake = FakeMeili()
        fake.write_docs("idx", [mb.to_document("p1", point("p1", [1.0], metadata={"keep": 1}).payload)])
        mb.apply_set_payload(fake, "idx", {"tags": ["z"]}, NS(must=[NS(has_id=["p1"])], must_not=None))  # enrichment's guarded form
        self.assertEqual(fake.docs["p1"]["tag_text"], "z")
        mb.apply_set_payload(fake, "idx", {"people": ["Ann"]}, ["p1"], key="metadata.entities")
        self.assertEqual(json.loads(fake.docs["p1"]["metadata_json"]), {"keep": 1, "entities": {"people": ["Ann"]}})
        with self.assertRaises(NotImplementedError):
            mb.apply_set_payload(fake, "idx", {}, ["p1"], key="tags.x")

    def test_mirror_writes_through_to_real_qdrant_and_keyword_index(self):
        calls, fake = [], FakeMeili()
        real = NS(upsert=lambda **kw: calls.append(("upsert", len(kw["points"]))), delete=lambda **kw: calls.append(("delete",)),
                  scroll=lambda **kw: "real-scroll")
        mirror = mb.MirrorQdrant(real, fake, "kw")
        mirror.upsert("c", [point("p1", [1.0])])
        self.assertEqual((calls, "p1" in fake.docs), ([("upsert", 1)], True))
        self.assertEqual(mirror.scroll(), "real-scroll")  # everything else is plain Qdrant
        mirror.delete("c", NS(points=["p1"]))
        self.assertNotIn("p1", fake.docs)


    def test_keyword_search_sends_configured_matching_strategy(self):
        h = NS(_extract_keywords=str.split, _prepare_tag_filters=list, _canonicalize_prefix_filters=list, RECALL_EXCLUDED_TYPES=(),
               _serialize_node=lambda n: {"id": n}, _format_graph_result=lambda g, n, s, k, seen: {"id": n, "score": s})
        fake, graph = FakeMeili(), NS(query=lambda q, p: NS(result_set=[["p1"]]))
        fake.search = lambda uid, body: (setattr(fake, "last_search", body), {"hits": [{"id": "p1", "_rankingScore": 0.5}]})[1]
        pkg, sub = types.ModuleType("automem"), types.ModuleType("automem.search")
        pkg.search, sub.runtime_recall_helpers = sub, h
        with mock.patch.dict(sys.modules, {"automem": pkg, "automem.search": sub, "automem.search.runtime_recall_helpers": h}):
            for strategy in ("last", "frequency"):
                out = mb.make_keyword_search(fake, "kw", None, strategy)(graph, "did caroline", 5, set())
                self.assertEqual(fake.last_search["matchingStrategy"], strategy)
        self.assertEqual(out, [{"id": "p1", "score": 0.5}])
        self.assertEqual(mb.MeiliClient.provenance(fake, "kw", "frequency")["matching_strategy"], "frequency")


class BenchHelperTests(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        values = list(range(1, 101))
        self.assertEqual([bench.percentile(values, p) for p in (50, 95, 99)], [50, 95, 99])
        self.assertEqual(bench.percentile([7], 99), 7)

    def test_budget_gate_stops_when_projection_exceeds_cap(self):
        ok = bench.check_budget("2.50", "1.25", 10)  # 2.50 + 12.50 = 15.00
        self.assertEqual(ok["projected_usd"], "15.00")
        with self.assertRaises(bench.BudgetExceeded):
            bench.check_budget("2.50", "1.80", 10)  # 20.50 > 20
        bench.check_budget("0", "2", 10)  # exactly at the cap is allowed


if __name__ == "__main__":
    unittest.main()
