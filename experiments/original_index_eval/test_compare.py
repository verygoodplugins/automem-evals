import unittest
from compare import compare, summarize


def row(q,kind,rank,expected=None):
    return {'query_id':q,'kind':kind,'floor':0,'expected':expected or [],
            'ranked':[], 'all_rank':rank,'any_rank':rank,'count':1,
            'latency_ms':1,'scope_leaks':[],'inactive_leaks':[],'forbidden_returned':[]}


class CompareTests(unittest.TestCase):
    def test_retrieval_negative_and_scope_metrics(self):
        a=row('1','identifier',1,['gold']); b=row('2','identifier',7,['gold'])
        negative=row('3','negative',None); negative['scope_leaks']=['foreign']
        result=summarize([a,b,negative])
        self.assertEqual(result['identifier@0']['all_at_5'],1)
        self.assertEqual(result['identifier@0']['all_at_10'],2)
        self.assertEqual(result['negative@0']['nonempty'],1)
        self.assertEqual(result['negative@0']['scope_leaks'],1)

    def test_compare_rejects_mismatched_or_duplicate_inputs(self):
        good={'fixture_sha256':'same','rows':[row('1','identifier',1,['gold'])]}
        other={'fixture_sha256':'different','rows':good['rows']}
        with self.assertRaises(ValueError):compare(good,other,good)
        other={'fixture_sha256':'same','rows':good['rows']*2}
        with self.assertRaises(ValueError):compare(good,other,good)

    def test_compare_accepts_actual_server_result_envelope(self):
        entry = row('1','identifier',1,['gold'])
        server = {'fixture_sha256':'same','result':{'evaluation':{'rows':[entry]}}}
        chunk = {'fixture_sha256':'same','rows':[entry]}
        self.assertEqual(compare(server, server, chunk)['candidate']['identifier@0']['all_at_5'], 1)

    def test_mrr_at_10_excludes_deeper_hits(self):
        rows = [row('1','identifier',2,['gold']), row('2','identifier',11,['gold'])]
        self.assertEqual(summarize(rows)['identifier@0']['mrr_at_10'], 0.25)


if __name__=='__main__':unittest.main()
