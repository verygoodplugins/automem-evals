"""Frozen client-side chunk-vector reference, not AutoMem /recall.

Scores every permitted source record exhaustively. The protocol reuses the
preceding predeclared summary-BM25 and max-chunk cosine blend, with no tuning.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time

import numpy as np
from fastembed import TextEmbedding
from fixtures import combined_corpus, fixture_hash

from lexical import build_lexical, bm25, chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    docs, queries, excluded = combined_corpus(args.dataset)
    cache = args.cache_dir.resolve(strict=True)
    model_dir = cache / 'models--qdrant--bge-base-en-v1.5-onnx-q'
    revision = (model_dir / 'refs/main').read_text().strip()
    digest = hashlib.sha256()
    with (model_dir/'snapshots'/revision/'model_optimized.onnx').open('rb') as model_file:
        for block in iter(lambda:model_file.read(1024*1024), b''):
            digest.update(block)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['NO_PROXY']='*'
    model = TextEmbedding(model_name='BAAI/bge-base-en-v1.5',cache_dir=str(cache),threads=2)
    parts, owners = [], []
    for i, doc in enumerate(docs):
        for part in chunks(doc['original_content']):
            owners.append(i)
            parts.append(part)
    start = time.perf_counter()
    part_vectors = np.asarray(list(model.embed(parts, batch_size=32)), dtype=np.float32)
    chunk_index_ms = (time.perf_counter()-start)*1000
    print(f'Embedded {len(parts)} chunks', flush=True)
    start = time.perf_counter()
    query_vectors = np.asarray(list(model.embed([q['text'] for q in queries],batch_size=32)), dtype=np.float32)
    query_embedding_ms = (time.perf_counter()-start)*1000
    lexical = build_lexical(docs, 'summary')
    owner_array = np.asarray(owners)
    indexes = {i:np.flatnonzero(owner_array==i) for i in range(len(docs))}
    scopes = defaultdict(list)
    for i, doc in enumerate(docs):
        scopes[doc['scope']].append(i)
    rows = []
    for query, vector in zip(queries, query_vectors):
        start = time.perf_counter()
        scores=[]
        for i in scopes[query['scope']]:
            doc = docs[i]
            if query.get('current_only',True) and not doc.get('active',True):
                continue
            semantic = float(np.max(part_vectors[indexes[i]] @ vector))
            counts,df,lengths,avg=lexical
            wordscore=bm25(query['text'],counts[i],df,lengths,avg,i,len(docs))
            score=.6*max(0,semantic)+.4*wordscore/(wordscore+4)
            scores.append((score,doc['id']))
        scores.sort(key=lambda item:(-item[0],item[1]))
        ranked=[mid for _,mid in scores[:10]]
        expected=set(query.get('expected', []))
        ranks=[ranked.index(mid)+1 for mid in expected if mid in ranked]
        rows.append({'query_id':query['id'],'kind':query['kind'],'floor':0,
                     'expected':sorted(expected),'ranked':ranked,
                     'all_rank':max(ranks) if expected and len(ranks)==len(expected) else None,
                     'any_rank':min(ranks) if ranks else None,'count':min(10,len(scores)),
                     'top_score':scores[0][0] if scores else None,
                     'scope_leaks':[], 'inactive_leaks':[],
                     'forbidden_returned':[x for x in query.get('forbidden',[]) if x in ranked],
                     'latency_ms':round((time.perf_counter()-start)*1000,3)})
    output={'status':'client_exhaustive_chunk_prototype_not_server','fixture_sha256':fixture_hash(docs,queries),
            'model':'BAAI/bge-base-en-v1.5','model_revision':revision,'model_sha256':digest.hexdigest(),
            'documents':len(docs),'queries':len(queries),'source_exclusions':excluded,
            'scoring':'0.6 * max(0, max_chunk_cosine) + 0.4 * summary_BM25/(summary_BM25+4)',
            'part_vectors':len(parts),'part_vectors_bytes_float32':len(parts)*768*4,
            'original_text_bytes':sum(len(d['original_content'].encode()) for d in docs),
            'summary_text_bytes':sum(len(d['summary'].encode()) for d in docs),
            'index_ms':round(chunk_index_ms,1),'query_embedding_batch_ms':round(query_embedding_ms,1),
            'limitations':['exhaustive in-memory scope filtering, not server ANN or final-score parity',
                           'latency excludes query embedding/network/database; concurrent host load',
                           'the same literal corpus includes stress controls; BM25 DF is global',
                           'fixed score blend; cutoff is not a calibrated abstention policy'],
            'rows':rows,'paid_usd':0}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(args.output)


if __name__=='__main__':
    main()
