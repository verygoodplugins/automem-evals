"""Seed old server records or query an isolated AutoMem endpoint.

Executed inside a disposable API container with no external egress. Inputs
contain only synthetic records and the public, pinned LoCoMo fixture.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'http://127.0.0.1:8001'
HEADERS = {'X-Api-Key': 'buried-fact-test-token', 'Content-Type': 'application/json'}
FIXTURE = Path('/tmp/original-index-fixture.json')
IDS = Path('/tmp/original-index-ids.json')


def request(path, data=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(),
                                 headers=HEADERS, method=method)
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def wait_vectors(expected):
    deadline = time.monotonic() + 180
    while True:
        health = request('/health')
        emb = health.get('embedding', {})
        if (health.get('sync_status') == 'synced' and health.get('memory_count') == expected
            and health.get('vector_count') == expected
            and all(emb.get(k, 0) == 0 for k in ('queue_depth', 'pending', 'inflight'))):
            return health
        if time.monotonic() > deadline:
            raise TimeoutError(f'vectors did not synchronize: {health}')
        time.sleep(.25)


def payload(doc):
    result = {'content': doc['summary'], 'tags': [doc['scope']], 'type':'Decision', 'importance':doc.get('importance',.5),
              'timestamp':'2022-01-01T00:00:00Z',
              'metadata': {'was_summarized': True, 'original_content':doc['original_content'],
                           'original_length':len(doc['original_content']), 'fixture_key':doc['id']}}
    if doc['kind'] == 'expired':
        result.update(t_valid='2020-01-01T00:00:00Z', t_invalid='2021-01-01T00:00:00Z')
    elif doc['kind'] == 'future':
        result['t_valid'] = '2099-01-01T00:00:00Z'
    return result


def seed():
    fixture = json.loads(FIXTURE.read_text())
    docs = fixture['documents']
    ids = {}
    start = time.perf_counter()
    active = [doc for doc in docs if doc.get('active', True)]
    inactive = [doc for doc in docs if not doc.get('active', True)]
    for i in range(0, len(active), 24):
        group = active[i:i + 24]
        response = request('/memory/batch', {'memories':[payload(d) for d in group]})
        returned = response.get('memory_ids') or []
        if len(returned) != len(group):
            raise RuntimeError('batch did not acknowledge every fixture')
        ids.update({doc['id']: mid for doc, mid in zip(group, returned)})
    for doc in inactive:
        response = request('/memory', payload(doc))
        ids[doc['id']] = response['memory_id']
    health = wait_vectors(len(docs))
    sample = request('/memory/' + ids[docs[0]['id']])['memory']
    if sample.get('metadata', {}).get('original_content') != docs[0]['original_content']:
        raise RuntimeError('legacy original text was not stored')
    IDS.write_text(json.dumps(ids, sort_keys=True))
    print(json.dumps({'records':len(docs), 'seed_ms':round((time.perf_counter() - start) * 1000, 1),
                      'health':health, 'legacy_original_verified':True}, sort_keys=True))


def evaluate(mode="all"):
    fixture = json.loads(FIXTURE.read_text())
    ids = json.loads(IDS.read_text())
    inverse = {mid:key for key, mid in ids.items()}
    docs = {doc['id']:doc for doc in fixture['documents']}
    output = []
    for query in fixture['queries']:
        if mode == 'pre' and query['kind'] not in ('identifier', 'history_expired', 'literal', 'stress'):
            continue
        # The fixed floor rerun is intentionally restricted to non-temporal
        # synthetic questions; thresholds are not tuned on the evaluation set.
        floors = (0, .4) if mode == 'all' and query['kind'] in ('identifier', 'paraphrase', 'negative', 'wrong_scope') else (0,)
        for floor in floors:
            params = urllib.parse.urlencode({'query':query['text'], 'tags':query['scope'],
                'tag_match':'exact', 'limit':10, 'adaptive_floor':'false',
                'current_only':str(query.get('current_only', True)).lower(),
                'expand_relations':'false', 'auto_decompose':'false', 'min_score':str(floor),
                'recency_bias':'off'})
            start = time.perf_counter()
            response = request('/recall?' + params)
            elapsed = (time.perf_counter() - start)*1000
            results = response.get('results', [])
            ranked = [inverse.get(r.get('id') or r.get('memory', {}).get('id'), 'unknown') for r in results]
            expected = set(query.get('expected', []))
            ranks = [ranked.index(key)+1 for key in expected if key in ranked]
            all_rank = max(ranks) if len(ranks) == len(expected) and expected else None
            scope_leaks = [key for key in ranked if key == 'unknown' or docs[key]['scope'] != query['scope']]
            inactive_leaks = [key for key in ranked if key != 'unknown' and not docs[key].get('active', True)] if query.get('current_only',True) else []
            forbidden = [key for key in query.get('forbidden',[]) if key in ranked]
            output.append({'query_id':query['id'], 'kind':query['kind'], 'floor':floor,
                'expected': sorted(expected), 'ranked':ranked, 'all_rank':all_rank,
                'any_rank':min(ranks) if ranks else None, 'count':len(results),
                'top_score':results[0].get('final_score') if results else None,
                'scope_leaks':scope_leaks, 'inactive_leaks':inactive_leaks, 'forbidden_returned':forbidden,
                'latency_ms':round(elapsed,3)})
    print(json.dumps({'rows':output, 'record_count':len(ids), 'fixture_sha256':fixture['fixture_sha256']}, sort_keys=True))


def mutation():
    """Verify index maintenance directly and through HTTP after content update/delete."""
    from falkordb import FalkorDB
    graph = FalkorDB(host='falkordb', port=6379).select_graph('memories')
    memory_id = json.loads(IDS.read_text())['mutable-probe']
    def indexed(term):
        result = graph.query("CALL db.idx.fulltext.queryNodes('MemoryOriginalText', $q) YIELD node AS m, score RETURN m.id", {'q':term})
        return memory_id in {row[0] for row in result.result_set}
    def recall(term):
        params=urllib.parse.urlencode({'query':term,'tags':'mutable-index','tag_match':'exact','limit':10,
              'adaptive_floor':'false','current_only':'true','min_score':'0','recency_bias':'off'})
        results=request('/recall?'+params).get('results',[])
        result=next((r for r in results if (r.get('id') or r.get('memory',{}).get('id'))==memory_id),None)
        return {'returned':result is not None, 'components':result.get('score_components',{}) if result else {}}
    out={'old_before':{'indexed':indexed('retiredalpha734'),'recall':recall('retiredalpha734')}}
    request('/memory/'+memory_id, {'content':'Current migration marker is freshbeta735.'}, method='PATCH')
    out['old_after_patch']={'indexed':indexed('retiredalpha734'),'recall':recall('retiredalpha734')}
    out['new_after_patch']={'indexed':indexed('freshbeta735'),'recall':recall('freshbeta735')}
    request('/memory/'+memory_id, method='DELETE')
    out['new_after_delete']={'indexed':indexed('freshbeta735'),'recall':recall('freshbeta735')}
    if not out['old_before']['indexed'] or out['old_after_patch']['indexed'] or not out['new_after_patch']['indexed'] or out['new_after_delete']['indexed']:
        raise AssertionError(f'index mutation maintenance failed: {out}')
    print(json.dumps(out,sort_keys=True))


if __name__ == '__main__':
    if sys.argv[1] == 'seed': seed()
    elif sys.argv[1] == 'evaluate': evaluate(sys.argv[2] if len(sys.argv) > 2 else 'all')
    elif sys.argv[1] == 'mutation': mutation()
    else: raise ValueError('expected seed or evaluate')
