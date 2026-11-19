import unittest
from fixtures import CASES, corpus, fixture_hash


class FixtureTests(unittest.TestCase):
    def test_distinct_facts_and_markers_absent_from_summary(self):
        docs, queries = corpus()
        facts = [d for d in docs if d['id'].startswith('fact-')]
        self.assertEqual(len(facts), 16)
        self.assertEqual(len({d['id'] for d in docs}), len(docs))
        self.assertEqual(len({q['id'] for q in queries}), len(queries))
        for i, doc in enumerate(facts):
            self.assertIn(CASES[i][2], doc['original_content'])
            self.assertNotIn(CASES[i][2], doc['summary'])
            self.assertIn(f'hx{i:03d}r', doc['original_content'])
            self.assertNotIn(f'hx{i:03d}r', doc['summary'])
        self.assertEqual(fixture_hash(docs, queries), fixture_hash(*corpus()))

    def test_scope_controls_reference_foreign_records(self):
        docs, queries = corpus()
        lookup = {d['id']: d for d in docs}
        wrong = [q for q in queries if q['kind'] == 'wrong_scope']
        self.assertEqual(len(wrong), 4)
        for q in wrong:
            self.assertNotEqual(lookup[q['forbidden'][0]]['scope'], q['scope'])
            self.assertIn(q['text'], lookup[q['forbidden'][0]]['original_content'])

    def test_history_controls_have_positive_and_negative_paths(self):
        docs, queries = corpus()
        by_id = {d['id']: d for d in docs}
        for q in queries:
            if q['kind'] in {'current_expired', 'current_future'}:
                self.assertTrue(q['current_only'])
                self.assertFalse(by_id[q['forbidden'][0]]['active'])
            elif q['kind'] == 'history_expired':
                self.assertFalse(q['current_only'])
                self.assertFalse(by_id[q['expected'][0]]['active'])

    def test_positive_and_negative_controls_are_disjoint(self):
        docs, queries = corpus()
        by_id = {d['id']: d for d in docs}
        for q in queries:
            for mid in q.get('expected', []):
                self.assertEqual(by_id[mid]['scope'], q['scope'])
            for mid in q.get('forbidden', []):
                if q['kind'] == 'wrong_scope':
                    self.assertNotEqual(by_id[mid]['scope'], q['scope'])



if __name__ == '__main__':
    unittest.main()
