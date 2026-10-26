"""Run against an explicitly supplied, valid v3 regression job; outputs stay in workspace."""
import argparse,copy,tempfile
from unittest.mock import patch
from production import *

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--job',required=True);args=p.parse_args()
    cfg=load_config(args.config);b=doctor(cfg);job=load_job(args.job,cfg)
    from ledger import digest
    old=next((x for x in read(resolve(cfg['history'],Path(cfg['workspace']))) if x['id']==job['id']),None)
    if old:job.update(mode='revision',revision_base_sha256=digest(old))
    validate(job,cfg,b)
    cases=[('old_schema',lambda j:j.update(schema_version=2),'旧版job'),('copy_voice_mismatch',lambda j:j['voice'].update(text_sha256='bad'),'配音与文案'),('double_speed',lambda j:j['voice'].update(speed_passes=2),'只执行一次'),('caption_version_mismatch',lambda j:j['captions'][0]['lines'].__setitem__(0,j['captions'][0]['lines'][0]+'，'),'字幕不对应'),('changed_interval',lambda j:j['shots'][1].update(source_start=999),'区间'),('missing_review',lambda j:j['shots'][0].update(review_note=''),'审核依据')]
    results=[]
    for name,mutate,expected in cases:
        j=copy.deepcopy(job);mutate(j)
        try: validate(j,cfg,b)
        except ValueError as e:
            require(expected in str(e),name+': unexpected '+str(e));results.append(name)
        else: raise AssertionError('未拦住 '+name)
    import production
    original_read=production.read
    history_path=resolve(cfg['history'],Path(cfg['workspace']))
    repeated=[{'id':'PREVIOUS','music_identity':job['music']['identity'],'music_sha256':job['music']['sha256']}]
    def fake_read(path):
        return repeated if Path(path)==history_path else original_read(path)
    with patch.object(production,'read',side_effect=fake_read):
        new=copy.deepcopy(job);new['mode']='new'
        try: validate(new,cfg,b)
        except ValueError as e: require('同一BGM' in str(e),'Unexpected history failure');results.append('adjacent_music_repeat')
        else: raise AssertionError('相邻重复BGM未拦截')
    revision_history=[dict(id=job['id'],music_identity=job['music']['identity'],music_sha256=job['music']['sha256']),dict(id='LATER',music_identity=job['music']['identity'],music_sha256=job['music']['sha256'])]
    with patch.object(production,'read',side_effect=lambda path:revision_history if Path(path)==history_path else original_read(path)):
        rev=copy.deepcopy(job);rev.update(mode='revision',revision_base_sha256=digest(revision_history[0]));validate(rev,cfg,b)
    results.append('revision_retains_music')
    # Mutations live in the test workspace; never alter accepted input evidence.
    from contracts import validate_evidence
    from align import compare,make_alignment
    testroot=Path(cfg['workspace'])/'contract_tests';testroot.mkdir(exist_ok=True)
    original_review=read(job['review_file'])
    provenance=read(job['shots'][0]['provenance_file']);provenance['source_sha256']='wrong'
    provenance_path=testroot/'wrong_provenance.json';save(provenance_path,provenance)
    j=copy.deepcopy(job);j['shots'][0]['provenance_file']=str(provenance_path)
    try:validate_evidence(j,cfg)
    except ValueError:results.append('wrong_source_provenance')
    else:raise AssertionError('源文件哈希不匹配未拦截')
    # A new job must never generate an apparently fresh QA for an older render.
    from evidence import qa
    render=testroot/'old_render';render.mkdir(exist_ok=True)
    video=render/'video.mp4';video.write_bytes(b'old-video-fixture')
    save(render/'job.json',job);save(render/'receipt.json',dict(video_sha256=sha(video),job_sha256=sha(render/'job.json')))
    j=copy.deepcopy(job);j['city']='changed'
    try:qa(cfg,j,str(video),testroot)
    except ValueError as e:require('实际渲染' in str(e),'Unexpected QA failure');results.append('old_render_new_job')
    else:raise AssertionError('旧片新QA未拦截')
    person_index=next(i for i,r in enumerate(original_review['shots']) if r['people_kind']=='approved_presenter')
    material_index=next(i for i,r in enumerate(original_review['shots']) if r['material_kind']=='micro_ceramic_mud')
    changes=[('pending',lambda r:r['shots'][0].update(status='pending')),('low_score',lambda r:r['shots'][0].update(semantic_score=79)),('missing_image',lambda r:r['shots'][0]['artifacts'][0].update(path=str(testroot/'absent.jpg'))),('wrong_person_approval',lambda r:r['shots'][person_index].update(presenter_approval_id='absent-person')),('missing_material_approval',lambda r:r['shots'][material_index].update(material_approval_id='absent'))]
    for name,mutate in changes:
        r=copy.deepcopy(original_review);mutate(r);dest=testroot/(name+'.json');save(dest,r);j=copy.deepcopy(job);j['review_file']=str(dest)
        try:validate_evidence(j,cfg)
        except (ValueError,FileNotFoundError):results.append(name)
        else:raise AssertionError('未拦住 '+name)
    for name,e,r,allow in [('unapproved_asr_substitution','哪里坏了改哪里','哪里坏了该哪里',[]),('stale_allowance','三天','三天',[dict(index=0,expected='3',recognized='三',kind='numeric',reason='old')]),('asr_length','一支团队','一支的团队',[])]:
        try:compare(e,r,allow)
        except ValueError:results.append(name)
        else:raise AssertionError('未拦住 '+name)
    compare('3天','三天',[dict(index=0,expected='3',recognized='三',kind='numeric',reason='本条数字核对')])
    try:make_alignment('你好',[{'text':'你 好','timestamp':[[0,100],[50,200]]}],[dict(lines=['你好'],highlights=[])],1,[])
    except ValueError:results.append('overlapping_timestamps')
    else:raise AssertionError('重叠时间戳未拦住')
    save(testroot/'result.json',dict(passed=True,cases=results))
    print('PASS',len(results),'regression cases:',','.join(results))

if __name__=='__main__':main()
