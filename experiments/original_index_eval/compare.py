"""Summarize matched server or explicitly marked chunk-reference results."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics


def key(row):
    return row['query_id'], row['floor']


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['kind'], row['floor'])].append(row)
    summary = {}
    for (kind, floor), group in sorted(groups.items()):
        item={'n':len(group), 'p50_ms':round(statistics.median(r['latency_ms'] for r in group), 3),
              'scope_leaks':sum(bool(r['scope_leaks']) for r in group),
              'inactive_leaks':sum(bool(r['inactive_leaks']) for r in group),
              'forbidden_returned':sum(bool(r['forbidden_returned']) for r in group)}
        ordered = sorted(r['latency_ms'] for r in group)
        item['p95_ms'] = ordered[max(0,(95*len(ordered)+99)//100-1)]
        if group[0]['expected']:
            for k in (1,5,10):
                item[f'any_at_{k}']=sum(r['any_rank'] is not None and r['any_rank'] <= k for r in group)
                item[f'all_at_{k}']=sum(r['all_rank'] is not None and r['all_rank'] <= k for r in group)
            item['mrr_at_10']=sum(1/r['any_rank'] if r['any_rank'] and r['any_rank'] <= 10 else 0 for r in group)/len(group)
        else:
            item['nonempty']=sum(r['count']>0 for r in group)
        summary[f'{kind}@{floor}']=item
    return summary


def compare(baseline, candidate, chunk):
    if not (baseline['fixture_sha256'] == candidate['fixture_sha256'] == chunk['fixture_sha256']):
        raise ValueError('fixture hashes differ')
    def rows(result):
        values = result['result']['evaluation']['rows'] if 'result' in result else result['rows']
        result_map = {key(row):row for row in values}
        if len(result_map) != len(values):
            raise ValueError('duplicate query/floor')
        return result_map
    old,new,vec=rows(baseline),rows(candidate),rows(chunk)
    if old.keys() != new.keys():
        raise ValueError('server query cohorts differ')
    if {q for q in old if q[1] == 0} != vec.keys():
        raise ValueError('chunk query cohort differs')
    paired = []
    for q in sorted(old):
        a,b=old[q],new[q]
        if a['kind'] != b['kind'] or a['expected'] != b['expected']:
            raise ValueError('question labels differ')
        paired.append({'query_id':q[0], 'floor':q[1], 'kind':a['kind'],
                       'baseline_all_rank':a['all_rank'], 'candidate_all_rank':b['all_rank'],
                       'baseline_nonempty':bool(a['count']), 'candidate_nonempty':bool(b['count'])})
    return {'baseline':summarize(list(old.values())),'candidate':summarize(list(new.values())),
            'chunk_prototype':summarize(list(vec.values())),'paired':paired,
            'limitations':['LoCoMo evidence labels are incomplete relevance labels; all@k is evidence coverage',
                           'chunk arm uses exhaustive local ranking and a different scoring function from the server',
                           'score thresholds are fixed controls, not tuned or comparable across ranking systems',
                           'latencies include different operations and host contention; not production latency']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path)
    p.add_argument('chunk',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    old,new,chunk=[json.loads(path.read_text()) for path in (a.baseline,a.candidate,a.chunk)]
    result=compare(old,new,chunk)
    result['input_sha256']={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.baseline,a.candidate,a.chunk)}
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps({name:result[name] for name in ('baseline','candidate','chunk_prototype')},indent=2))


if __name__=='__main__':
    main()
