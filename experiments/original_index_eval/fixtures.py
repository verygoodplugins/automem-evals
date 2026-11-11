"""Frozen, independent original-text retrieval controls.

All records are synthetic. Documents and queries are designed separately from
last session's full-text fixture; no production or user memories are included.
"""
import hashlib
import json

# scope, topic, fact, reworded query, plausible but unsupported question
CASES = [
    ('atlas-ops', 'writer restart', 'The writer resumes only after removing an expired lease.', 'What must happen before the writer can resume?', 'Which pager escalation rota applies to the writer?'),
    ('atlas-ops', 'incident response', 'The first response to a backup checksum mismatch is to quarantine the archive.', 'What should the operator do when the backup checksum is wrong?', 'What is the incident response phone number?'),
    ('atlas-ops', 'deployment service', 'Roll back the deployment after three failed health checks.', 'How many failed readiness checks trigger a rollback?', 'What time zone is the deployment calendar in?'),
    ('atlas-ops', 'queue incident', 'Rebuild the dead-letter queue before turning the consumers back on.', 'What must be rebuilt before the consumers restart?', 'Which cloud region hosts the dead-letter queue?'),
    ('studio-web', 'keyboard access', 'The focus ring should remain visible on a charcoal background.', 'How should keyboard focus appear in dark mode?', 'What brand typeface is used in the focus indicator?'),
    ('studio-web', 'mobile navigation', 'Place the primary action bar along the bottom edge on small screens.', 'Where should the main actions sit on a phone?', 'Which translation provider handles the mobile menu?'),
    ('studio-web', 'notification color', 'Use a muted coral accent for the warning badge.', 'What colour was selected for alert badges?', 'What hex code was chosen for the neutral background?'),
    ('studio-web', 'motion setting', 'Shorten the bounce animation to 120 milliseconds.', 'How long should the bounce animation last?', 'Which sound plays when the bounce finishes?'),
    ('field-team', 'transport preference', 'Prefer overnight rail journeys to short-haul flights where feasible.', 'Which travel mode should replace short flights when practical?', 'Which loyalty account should receive train points?'),
    ('field-team', 'conference gathering', 'Meet at the west entrance at 08:30 on the first morning.', 'Where and when should the group gather on day one?', 'What is the conference registration barcode?'),
    ('field-team', 'hotel rooms', 'Avoid rooms facing the tram line to reduce noise.', 'Which rooms should the group avoid because they are noisy?', 'What is the hotel door access code?'),
    ('field-team', 'event catering', 'One attendee is allergic to peanuts; request nut-free food.', 'What dietary allergy must the venue accommodate?', 'What wine did the attendee select?'),
    ('shop-platform', 'browser testing', 'Run browser tests serially to avoid port collisions.', 'How should browser checks be scheduled to prevent port conflicts?', 'What is the annual browser testing budget?'),
    ('shop-platform', 'authentication migration', 'Rotate the signing key before switching identity providers.', 'What security credential changes before the login provider migration?', 'What support number does the new identity provider use?'),
    ('shop-platform', 'package recovery', 'Remove the corrupt package cache before rebuilding.', 'What should be cleared after a damaged dependency download?', 'Where was the team offsite held?'),
    ('shop-platform', 'alert escalation', 'Notify the on-call operator after two failed retry attempts.', 'Who is alerted after two failed automatic recoveries?', 'What colour is the operator dashboard?'),
]

FILLER = (
    'Discussion notes document operational context, accepted alternatives, '
    'delivery dependencies, accountability, previous status, and scheduling. '
)


def corpus():
    docs, queries = [], []
    for i, (scope, topic, fact, paraphrase, missing) in enumerate(CASES):
        key = f'hx{i:03d}r'
        summary = f'The {scope} project recorded a decision about {topic}.'
        original = f'{summary} {(FILLER * 4)} Record identifier {key}. {fact}'
        docs.append({'id':f'fact-{i:02d}', 'scope':scope, 'summary':summary,
                     'original_content':original, 'active':True, 'kind':'answer'})
        queries.extend([
            {'id':f'id-{i:02d}', 'kind':'identifier', 'scope':scope, 'text':key, 'expected':[f'fact-{i:02d}']},
            {'id':f'paraphrase-{i:02d}', 'kind':'paraphrase', 'scope':scope, 'text':paraphrase, 'expected':[f'fact-{i:02d}']},
            {'id':f'negative-{i:02d}', 'kind':'negative', 'scope':scope, 'text':missing, 'expected':[]},
        ])
    scopes = sorted({case[0] for case in CASES})
    for si, scope in enumerate(scopes):
        for i in range(16):
            text = f'Team {scope} project meeting {i}: notes track routine scheduling, design, deployments, and operational coordination.'
            docs.append({'id':f'noise-{si}-{i}', 'scope':scope, 'summary':text,
                         'original_content':text+' '+FILLER*3, 'active':True, 'kind':'distractor'})
        foreign = (si + 1) % len(scopes)
        foreign_id = next(i for i, row in enumerate(CASES) if row[0] == scopes[foreign])
        queries.append({'id':f'wrong-scope-{si}', 'kind':'wrong_scope', 'scope':scope,
                        'text':f'hx{foreign_id:03d}r', 'expected':[],
                        'forbidden':[f'fact-{foreign_id:02d}']})
        expired = f'historic{si}x'
        future = f'notyet{si}x'
        for suffix, token, state in [('expired', expired, 'expired'), ('future', future, 'future')]:
            docs.append({'id':f'{suffix}-{si}', 'scope':scope, 'summary':f'Archived decision for {scope}.',
                         'original_content':f'The {scope} project confidential historical marker {token}.',
                         'active':False, 'kind':state})
        queries.extend([
            {'id':f'current-expired-{si}', 'kind':'current_expired','scope':scope,'text':expired,'expected':[], 'forbidden':[f'expired-{si}'], 'current_only':True},
            {'id':f'history-expired-{si}', 'kind':'history_expired','scope':scope,'text':expired,'expected':[f'expired-{si}'], 'current_only':False},
            {'id':f'current-future-{si}', 'kind':'current_future','scope':scope,'text':future,'expected':[], 'forbidden':[f'future-{si}'], 'current_only':True},
        ])
    # A separate higher-cardinality scope tests whether a low-importance exact
    # marker is lost behind common-term distractors before ranking.
    for i in range(300):
        summary = f'Stress scope billing decision note {i}.'
        docs.append({'id':f'stress-noise-{i:03d}', 'scope':'stress-index', 'summary':summary,
                     'original_content':summary+' The checkout policy and provider code require routine audit review.',
                     'active':True, 'kind':'distractor', 'importance':.9})
    docs.append({'id':'stress-target', 'scope':'stress-index', 'summary':'Stress scope billing decision.',
                 'original_content':'The checkout policy provider code is markerstress734 for production routing.',
                 'active':True, 'kind':'answer', 'importance':.1})
    queries.append({'id':'stress-target-query','kind':'stress','scope':'stress-index',
                    'text':'checkout policy provider code markerstress734', 'expected':['stress-target']})
    # These realistic literals exercise query-language escaping and Unicode.
    for i, (raw, query) in enumerate([
        ('Contact service+queue@example.net for the customer escalation.', 'service+queue@example.net'),
        ('The restoration directory is /var/lib/cache-v2/locked.', '/var/lib/cache-v2/locked'),
        ('The incident owner is located in München.', 'München'),
        ('The event appears under the name Café Soleil.', 'Café Soleil'),
    ]):
        scope = 'literal-index'
        docs.append({'id':f'literal-{i}', 'scope':scope, 'summary':f'Operational incident note {i}.',
                     'original_content':f'Operational incident note {i}. {FILLER * 3} {raw}',
                     'active':True, 'kind':'answer'})
        queries.append({'id':f'literal-query-{i}','kind':'literal','scope':scope,
                        'text':query,'expected':[f'literal-{i}']})
    # After backfill this record is changed and deleted to test index maintenance.
    docs.append({'id':'mutable-probe','scope':'mutable-index','summary':'A historical change note.',
                 'original_content':'The obsolete migration marker is retiredalpha734.',
                 'active':True,'kind':'mutable'})
    return docs, queries


def fixture_hash(docs, queries):
    value = json.dumps({'documents':docs,'queries':queries},sort_keys=True,separators=(',', ':'),ensure_ascii=False).encode()
    return hashlib.sha256(value).hexdigest()


def combined_corpus(dataset_path):
    """Combine independent controls with a frozen public LoCoMo evidence slice."""
    from pathlib import Path
    from locomo_adapter import build
    source = Path(dataset_path).read_bytes()
    expected = '79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4'
    if hashlib.sha256(source).hexdigest() != expected:
        raise ValueError('LoCoMo dataset revision does not match the pinned input')
    heldout_docs, heldout_queries, excluded = build(json.loads(source))
    docs, queries = corpus()
    for doc in heldout_docs:
        docs.append({**doc, 'active': True, 'kind': 'locomo'})
    for q in heldout_queries:
        queries.append({**q, 'kind': 'locomo_evidence'})
    return docs, queries, excluded
