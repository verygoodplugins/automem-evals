"""Compare isolated baseline with candidate pre/post legacy backfill.

Every stack starts from the pinned old server, so all records predate the new
index. Candidate API alone is recreated against its own preserved graph/vector
stores, then its dry-run and explicit legacy-enabled backfill are invoked.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from fixtures import combined_corpus, fixture_hash

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPOSE = HERE / 'compose.yaml'
ARM = HERE / 'server_arm.py'


def command(args, **kw):
    return subprocess.run(args, check=True, text=True, **kw)


def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_info(repo):
    repo = repo.resolve(strict=True)
    dirty = command(['git','-C',str(repo),'status','--porcelain','--untracked-files=no'],capture_output=True).stdout.strip()
    if dirty:
        raise ValueError(f'tracked changes in {repo}; commit the implementation before evaluation')
    return repo, command(['git','-C',str(repo),'rev-parse','HEAD'],capture_output=True).stdout.strip()


def wait(container, require_index=False):
    for _ in range(150):
        script = ('import urllib.request,json; d=json.load(urllib.request.urlopen("http://127.0.0.1:8001/health",timeout=2)); '
                  + ('assert d.get("original_text_index")=="ready"' if require_index else 'assert d.get("status") in ("healthy","degraded")'))
        check = subprocess.run(['docker','exec',container,'python','-c', script],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if check.returncode == 0:
            return
        time.sleep(1)
    raise TimeoutError(f'{container} did not become healthy')


def exec_arm(container, mode, subset=None):
    command_args = ['docker','exec','-i',container,'python','-',mode]
    if subset:
        command_args.append(subset)
    try:
        result = command(command_args, input=ARM.read_text(),capture_output=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'{mode} failed in {container}: {exc.stderr}') from exc
    return json.loads(result.stdout)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('baseline','candidate'),required=True)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--cache-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--legacy-flag',default='--assume-legacy-original-current',
                   help='exact candidate CLI opt-in flag for existing unverifiable originals')
    args=p.parse_args()
    baseline,base_sha=source_info(args.baseline)
    if args.mode=='candidate':
        if args.candidate is None:p.error('--candidate is required')
        candidate,candidate_sha=source_info(args.candidate)
    else:
        candidate,candidate_sha=None,None
    cache=args.cache_dir.resolve(strict=True)
    model_dir=cache/'models--qdrant--bge-base-en-v1.5-onnx-q'
    model_revision=(model_dir/'refs/main').read_text().strip()
    model_sha=sha_file(model_dir/'snapshots'/model_revision/'model_optimized.onnx')
    images={name:command(['docker','image','inspect',name,'--format','{{.Id}}'],capture_output=True).stdout.strip()
            for name in ('automem-flask-api:latest','falkordb/falkordb:latest','qdrant/qdrant:v1.11.3')}
    docs,queries,excluded=combined_corpus(args.dataset)
    fixture={'documents':docs,'queries':queries,'fixture_sha256':fixture_hash(docs,queries)}
    project='originalidx'+uuid.uuid4().hex[:12]
    compose=['docker','compose','-p',project,'-f',str(COMPOSE)]
    env=dict(os.environ,AUTOMEM_DIR=str(baseline),EVAL_MODELS_DIR=str(cache),
             EVAL_EMBEDDING_PROVIDER='local',EVAL_VECTOR_SIZE='768',EVAL_AUTO_SUMMARIZE='false')
    container=f'{project}-api-1'
    results={}
    with tempfile.TemporaryDirectory(prefix='original-index-eval-') as temp:
        temp=Path(temp); fixture_path=temp/'fixture.json'; ids_path=temp/'ids.json'
        fixture_path.write_text(json.dumps(fixture,ensure_ascii=False))
        try:
            command(compose+['up','-d','--pull','never'],env=env,stdout=subprocess.DEVNULL)
            wait(container)
            command(['docker','cp',str(fixture_path),f'{container}:/tmp/original-index-fixture.json'],capture_output=True)
            results['seed']=exec_arm(container,'seed')
            if args.mode=='baseline':
                results['evaluation']=exec_arm(container,'evaluate')
            else:
                command(['docker','cp',f'{container}:/tmp/original-index-ids.json',str(ids_path)],capture_output=True)
                env['AUTOMEM_DIR']=str(candidate)
                command(compose+['up','-d','--no-deps','--force-recreate','api'],env=env,stdout=subprocess.DEVNULL)
                wait(container, require_index=True)
                command(['docker','cp',str(fixture_path),f'{container}:/tmp/original-index-fixture.json'],capture_output=True)
                command(['docker','cp',str(ids_path),f'{container}:/tmp/original-index-ids.json'],capture_output=True)
                results['pre_backfill']=exec_arm(container,'evaluate','pre')
                backfill=['docker','exec',container,'python','/app/scripts/backfill_original_search.py',
                          '--host','falkordb','--allow-remote']
                def run_backfill(flags):
                    start=time.perf_counter()
                    response=command(backfill+flags,capture_output=True)
                    return {'summary':json.loads(response.stdout), 'stderr':response.stderr,
                            'elapsed_ms':round((time.perf_counter()-start)*1000,1)}
                results['backfill']={}
                results['backfill']['dry_conservative']=run_backfill([])
                results['backfill']['apply_conservative']=run_backfill(['--apply'])
                results['conservative_sample']=exec_arm(container,'evaluate','pre')
                results['backfill']['dry_legacy_opt_in']=run_backfill([args.legacy_flag])
                results['backfill']['apply_legacy_opt_in']=run_backfill(['--apply',args.legacy_flag])
                results['backfill']['verify']=run_backfill(['--verify'])
                results['backfill']['repeat_legacy_opt_in']=run_backfill(['--apply',args.legacy_flag])
                if results['backfill']['repeat_legacy_opt_in']['summary'].get('applied') != 0:
                    raise RuntimeError('legacy backfill is not idempotent')
                results['evaluation']=exec_arm(container,'evaluate')
                results['mutation']=exec_arm(container,'mutation')
        finally:
            cleanup=subprocess.run(compose+['down','-v','--remove-orphans'],env=env,stdout=subprocess.DEVNULL)
            if cleanup.returncode:
                raise RuntimeError(f'failed to remove isolated project {project}')
    output={'mode':args.mode,'baseline_sha':base_sha,'candidate_sha':candidate_sha,
            'fixture_sha256':fixture['fixture_sha256'],'dataset_sha256':sha_file(args.dataset),
            'source_exclusions':excluded,'model':'BAAI/bge-base-en-v1.5','model_revision':model_revision,
            'model_sha256':model_sha,'image_ids':images,'server_arm_sha256':sha_file(ARM),
            'network':'internal','enrichment':False,'provider_cost_usd':0,'result':results}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
    print(args.output)


if __name__=='__main__':main()
