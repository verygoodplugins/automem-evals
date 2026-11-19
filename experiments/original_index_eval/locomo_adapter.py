"""Pinned LoCoMo evidence adapter; no QA answers are indexed."""
from collections import Counter
import re

SAMPLES=('conv-26','conv-30')
DOC_CHARS=850
SUMMARY_CHARS=220


def build(dataset):
    docs=[];queries=[];excluded=Counter(); selected={s['sample_id']:s for s in dataset if s.get('sample_id') in SAMPLES}
    if set(selected)!=set(SAMPLES): raise ValueError('expected frozen conversations missing')
    for scope in SAMPLES:
        sample=selected[scope]; conversation=sample['conversation']; turns={}; mapping={}
        sessions=sorted((k for k in conversation if re.fullmatch(r'session_\d+',k)),key=lambda k:int(k.split('_')[1]))
        for name in sessions:
            session=conversation[name]; session_time=conversation.get(name+'_date_time','')
            group=[]; chars=0
            def flush():
                nonlocal group,chars
                if not group:return
                mid=f'{scope}/{name}/{len(docs):04d}'
                content=f'Session date: {session_time}\n'+'\n'.join(f"{t.get('speaker','Unknown')}: {t['text']}" for t in group)
                docs.append({'id':mid,'scope':scope,'original_content':content,'summary':content[:SUMMARY_CHARS]})
                for turn in group:
                    if turn['dia_id'] in mapping: raise ValueError('duplicate dialog identifier')
                    mapping[turn['dia_id']]=mid
                group=[];chars=0
            for turn in session:
                if not isinstance(turn,dict) or not isinstance(turn.get('text'),str) or not turn.get('dia_id'):
                    raise ValueError('invalid dialogue record')
                turns[turn['dia_id']]=turn
                n=len(turn['text'])+len(turn.get('speaker',''))+3
                if group and chars+n>DOC_CHARS:flush()
                group.append(turn);chars+=n
            flush()
        for i,qa in enumerate(sample['qa']):
            if qa.get('category')==5:
                excluded['adversarial_category_5']+=1;continue
            evidence=qa.get('evidence') or []
            if not isinstance(evidence,list) or not evidence or any(x not in mapping for x in evidence):
                excluded['missing_or_unresolvable_evidence']+=1;continue
            if any(turns[x].get('img_url') or turns[x].get('blip_caption') for x in evidence):
                excluded['visual_evidence_ambiguous']+=1;continue
            if not isinstance(qa.get('question'),str) or not qa['question'].strip():
                excluded['empty_question']+=1;continue
            queries.append({'id':f'{scope}/q{i:03d}','scope':scope,'text':qa['question'],
                            'expected':sorted({mapping[x] for x in evidence}),
                            'category':qa.get('category'),'evidence_turns':len(set(evidence))})
    return docs,queries,dict(excluded)
