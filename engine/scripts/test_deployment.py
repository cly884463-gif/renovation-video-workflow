"""Fault injection and real process concurrency; fixtures only under --out."""
import argparse,copy,json,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from production import save,read,load_config,output_dir
from ledger import commit,digest,check_job,seed


def worker(root,task):
    out=Path(root);spec=read(out/(task+'.json'));b=out/('backup_'+task);b.mkdir()
    commit(out/'history.json',spec['job'],spec['entry'],b)


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--worker');a=p.parse_args()
    if a.worker:worker(a.out,a.worker);return
    out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False);cases=[]
    def ok(name,value):assert value,name;cases.append(name)
    def reject(name,fn):
        try:fn()
        except (ValueError,FileNotFoundError):cases.append(name)
        else:raise AssertionError(name)
    cfg=dict(workspace='work',history='history.json',approvals='work/approvals.json',source_roots={'shared':['missing'],'optional':['also_missing']},material_roots=['@library/optional/拍摄'],copy_root='@shared/文案',tts={'reference_audio':'private/reference.wav','python':'runtime/python.exe'},asr={'model_path':'models/model'})
    save(out/'machine.json',cfg);loaded=load_config(out/'machine.json')
    ok('offline_unused_library_loads',loaded['material_roots']==cfg['material_roots'])
    ok('asr_relative_to_config',loaded['asr']['model_path']==str(out/'models/model'))
    ok('voice_relative_to_config',loaded['tts']['reference_audio']==str(out/'private/reference.wav'))
    from workflow import initialize,configure,new_job
    initialize(['--config',str(out/'machine.json')]);history=Path(loaded['workspace'])/'history.json';old=read(history);save(history,[{'id':'keep-me'}])
    initialize(['--config',str(out/'machine.json')]);ok('repeated_init_preserves_history',read(history)==[{'id':'keep-me'}])
    # Seed existing and missing files independently without an overwrite.
    ok('partial_init_seed_missing',seed(out/'new_approvals.json',{'approved':[]})=='created')
    ok('seed_preserves_existing',seed(out/'new_approvals.json',{'bad':True})=='preserved' and read(out/'new_approvals.json')=={'approved':[]})
    save(history,old)
    configure(['--out',str(out/'generated/machine.json')]);ok('configuration_generated_outside_skill',read(out/'generated/machine.json')['workspace']=='./work')
    save(out/'draft.json',{'id':'NEW01'})
    for n in ('job1','job2'):new_job(['--config',str(out/'machine.json'),'--draft',str(out/'draft.json'),'--out',n])
    ok('unique_new_task_ids',read(out/'work/job1/draft.json')['id']!=read(out/'work/job2/draft.json')['id'])
    from preflight import inspect
    with patch('preflight.doctor',return_value=True),patch('preflight.subprocess.run',side_effect=FileNotFoundError('missing runtime')):
        r=inspect(loaded,'all')
    missing={x['item'] for x in r['checks'] if x['status']=='missing'}
    ok('all_missing_requirements_reported',not r['passed'] and {'base_python','voice_python','voice_reference','asr_python','asr_model'}.issubset(missing))
    from source_paths import key
    for name,contents in [('alias_a',b'a'),('alias_b',b'b')]:
        root=out/name;root.mkdir();(root/'file.mp4').write_bytes(contents)
    reject('alias_content_conflict',lambda:key(out/'alias_a/file.mp4',{'source_roots':{'shared':[str(out/'alias_a'),str(out/'alias_b')]}}))
    existing={'id':'old','music_identity':'m','music_sha256':'s','revision_token':'before'}
    reject('new_id_collision',lambda:check_job({'id':'old'},[existing]))
    reject('stale_revision',lambda:check_job({'id':'old','mode':'revision','revision_base_sha256':'stale'},[existing]))
    ok('explicit_revision_allowed',check_job({'id':'old','mode':'revision','revision_base_sha256':digest(existing)},[existing])==existing)
    output_dir(loaded,'failed')
    try:output_dir(loaded,'failed')
    except ValueError as e:ok('retry_message_preserves_evidence','failed_retry2' in str(e) and (out/'work/failed').is_dir())
    # Multiple OS processes, not threads or mocked locks.
    save(out/'history.json',[])
    def launch(task):return subprocess.Popen([sys.executable,'-X','utf8','-B',__file__,'--out',str(out),'--worker',task],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    jobs=[]
    for i in range(4):
        task='concurrent'+str(i);save(out/(task+'.json'),dict(job={'id':task,'mode':'new'},entry={'id':task,'music_identity':task,'music_sha256':task}));jobs.append(launch(task))
    for proc in jobs:
        _,err=proc.communicate(timeout=30);assert proc.returncode==0,err
    ok('concurrent_appends_no_loss',len(read(out/'history.json'))==4)
    save(out/'history.json',[existing]);rev={'id':'old','mode':'revision','revision_base_sha256':digest(existing)}
    jobs=[]
    for i in range(2):
        task='revision'+str(i);entry=dict(existing,revision_token=task);save(out/(task+'.json'),dict(job=rev,entry=entry));jobs.append(launch(task))
    codes=[]
    for proc in jobs:proc.communicate(timeout=30);codes.append(proc.returncode)
    ok('concurrent_revision_conflict',sum(c==0 for c in codes)==1 and len(read(out/'history.json'))==1)
    current=read(out/'history.json')
    b=out/'music_conflict';b.mkdir()
    reject('music_rechecked_under_lock',lambda:commit(out/'history.json',{'id':'new'},dict(id='new',music_identity='m',music_sha256='s'),b))
    ok('failed_commit_preserves_history',read(out/'history.json')==current)
    save(out/'result.json',dict(passed=True,cases=cases));print('PASS',len(cases),'deployment regressions')


if __name__=='__main__':main()
