"""Single dispatch entry; missing capabilities fail rather than silently downgrade."""
import argparse,hashlib,json,shutil,subprocess,sys,uuid
from pathlib import Path
from production import PACKAGE,read,save,sha,require,load_config,load_job,output_dir,doctor,validate,text_hash
from package import check


def configure(args):
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args(args);dest=Path(a.out).resolve()
    require(not dest.is_relative_to(PACKAGE),'配置须放技能目录外的工作项目')
    require(not dest.exists(),'配置已存在，不能覆盖')
    cfg=read(PACKAGE/'configs/machine.example.json');cfg.update(workspace='./work',approvals='./work/approvals.json',history='history.json')
    dest.parent.mkdir(parents=True,exist_ok=True);save(dest,cfg);print(dest,'请填写真实素材、声音和模型路径，再init及doctor；此模板尚未就绪')

def initialize(args):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args(args);cfg=load_config(a.config)
    root=Path(cfg['workspace']);root.mkdir(parents=True,exist_ok=True)
    from ledger import seed
    for name in ('history','approvals'):
        destination=Path(cfg[name]);destination=destination if destination.is_absolute() else root/destination
        allowed=[root]+([Path(cfg['team_directory'])] if cfg.get('team_directory') else [])
        require(any(destination.resolve().is_relative_to(x) for x in allowed),'初始清单须放workspace或明确配置的team_directory内')
        destination.parent.mkdir(parents=True,exist_ok=True)
        print(name,seed(destination,read(PACKAGE/f'data/{name}.json')))
    print('已补缺失清单，保留已有记录；新版审批请按具体差异核对合并，不覆盖工作清单。')


def new_job(args):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--draft',required=True);p.add_argument('--revision',action='store_true');p.add_argument('--out',required=True);a=p.parse_args(args)
    cfg=load_config(a.config);job=read(a.draft)
    if job.get('copy',{}).get('text'):
        from production import canon
        from production import load_brand
        supported=set(read(load_brand(cfg)['font_codepoints']))
        text=job['copy']['text']+job.get('city','')+''.join(job.get('cover',{}).get('lines',[]))+job.get('cover',{}).get('theme','')
        missing=sorted({c for c in canon(text) if ord(c) not in supported})
        require(not missing,'配音前发现品牌字体缺字：'+''.join(missing)+'；先核对文案/字体，不生成配音')
    from ledger import digest,check_job
    from production import resolve
    history=read(resolve(cfg['history'],Path(cfg['workspace'])))
    if a.revision:
        old=next((x for x in history if x['id']==job.get('id')),None);require(old is not None,'找不到返修ID')
        job.update(mode='revision',revision_base_sha256=digest(old))
    else:
        job.update(id='video-'+uuid.uuid4().hex,mode='new');job.pop('revision_base_sha256',None)
    check_job(job,history);out=output_dir(cfg,a.out);save(out/'draft.json',job);print(out/'draft.json')

def finalize(args):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--job',required=True);p.add_argument('--qa',required=True);p.add_argument('--mix-alignment',required=True);p.add_argument('--out',required=True);a=p.parse_args(args)
    cfg=load_config(a.config);job=load_job(a.job,cfg);validate(job,cfg,doctor(cfg));q=read(a.qa);m=read(a.mix_alignment)
    digest=hashlib.sha256(json.dumps(job,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    require(q['job_sha256']==digest and q['video_sha256']==sha(q['video']),'QA对应旧版视频或旧job')
    require(sha(q['render_receipt'])==q['render_receipt_sha256'],'渲染收据变化')
    receipt=read(q['render_receipt']);rendered_job=Path(q['render_receipt']).parent/'job.json'
    require(receipt['video_sha256']==q['video_sha256'] and receipt['job_sha256']==sha(rendered_job) and read(rendered_job)==job,'实际渲染输入与交付计划不一致')
    require(q['machine_pass'] and q['full_decode'] and not q['black_segments'] and q['peak_db']<0,'机器检查未通过')
    require(q['visual_review']=='accepted' and q['reviewer'] and q['review_note'],'需实视全部审核图并填写结果')
    for x in q['contacts']:require(sha(x['path'])==x['sha256'],'成片联系图缺失/变化')
    require(m.get('passed') and m.get('media_sha256')==q['video_sha256'] and m['text_sha256']==job['copy']['sha256'],'缺当前成片终混全文识别')
    from align import compare
    compare(m['expected'],m['recognized'],m['differences'])
    require(m['expected']==__import__('production').canon(job['copy']['text']),'终混预期文字不符')
    raw=Path(a.mix_alignment).parent/'asr_result.json';require(sha(raw)==m['result_sha256'],'终混原始识别记录变化')
    out=output_dir(cfg,a.out)
    # No complete-listening claim when the evaluator only reviewed stills and ASR.
    status='reviewed_delivery' if q['subjective_listening'] and q['realtime_playback'] else 'ready_for_user_review'
    history_path=Path(cfg['history']);history_path=history_path if history_path.is_absolute() else Path(cfg['workspace'])/history_path
    from contracts import source_key
    entry=dict(id=job['id'],music_identity=job['music']['identity'],music_sha256=job['music']['sha256'],status=status,shots=[dict(source=source_key(s['source'],cfg),source_start=s['source_start'],source_duration=s['source_duration'],scene_id=s['scene_id'],intent=s['intent']) for s in job['shots']])
    entry.update(video_sha256=q['video_sha256'],revision_token=uuid.uuid4().hex)
    from ledger import commit
    commit(history_path,job,entry,out)
    save(out/'delivery.json',dict(id=job['id'],status=status,video=q['video'],sha256=q['video_sha256'],subjective_listening=q['subjective_listening'],realtime_playback=q['realtime_playback'],qa=str(Path(a.qa).resolve()),job=str(Path(a.job).resolve()),boundary='未试听/未连贯播放时必须随交付明确说明，机器与抽帧不能冒充听感验收'))
    print(out/'delivery.json')

def assemble(args):
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--draft',required=True);p.add_argument('--alignment',required=True);p.add_argument('--review',required=True);p.add_argument('--out',required=True);a=p.parse_args(args)
    cfg=load_config(a.config);job=load_job(a.draft,cfg);alignment=Path(a.alignment).resolve();out=output_dir(cfg,a.out)
    report=read(alignment/'alignment.json');job['schema_version']=3
    job['copy']['sha256']=text_hash(job['copy']['text']);require(report['text_sha256']==job['copy']['sha256'],'对齐稿与制作稿不同')
    voice=job['voice'];meta=read(Path(voice['path']).parent/'voice.json')
    require(meta['sha256']==sha(voice['path']) and meta['text_sha256']==job['copy']['sha256'],'原配音记录不对应稿件/音轨')
    require(meta['speed']==1.21 and meta['speed_passes']==1,'配音提速记录错误')
    voice.update(sha256=meta['sha256'],text_sha256=meta['text_sha256'],speed=meta['speed'],speed_passes=meta['speed_passes'],alignment_file=str(alignment/'alignment.json'),asr_result_file=str(alignment/'asr_result.json'),captions_file=str(alignment/'captions.json'),alignment_review='识别证据见alignment_file，听感状态以最终QA为准')
    require(report['audio_sha256']==voice['sha256'],'对齐音轨不符')
    job['captions']=read(alignment/'captions.json');job['review_file']=str(Path(a.review).resolve())
    for s in job['shots']:
        s['sha256']=sha(s['path']);s.setdefault('provenance_file',str(Path(s['path']).parent/'provenance.json'))
    job['music']['sha256']=sha(job['music']['path']);save(out/'job.json',job)
    print(out/'job.json','（未审批，先evidence再实视填写）')

def main():
    require(len(sys.argv)>1,'需要子命令；见仓库docs/workflow.md')
    command=sys.argv[1];args=sys.argv[2:]
    if command=='package-check':print(check()['version']);return
    if command=='package-build':subprocess.run([sys.executable,'-B',str(PACKAGE/'scripts/package.py'),'build']+args,check=True);return
    check()
    if command=='configure':configure(args);return
    if command=='init':initialize(args);return
    if command=='new-job':new_job(args);return
    if command=='finalize':finalize(args);return
    if command=='assemble':assemble(args);return
    routes={'doctor':('preflight.py',[]),'validate':('production.py',['validate']),'preview':('production.py',['preview']),'render':('production.py',['render']),'normalize':('normalize.py',[]),'voice-check':('preflight.py',['--stage','voice','--online']),'voice':('voice_lan.py',['generate']),'align':('align.py',[]),'evidence':('evidence.py',['shots']),'qa':('evidence.py',['qa'])}
    routes['material-index']=('material_index.py',[])
    require(command in routes,'未知命令 '+command)
    python=sys.executable
    if '--config' in args:
        cfg=load_config(args[args.index('--config')+1]);key='asr' if command=='align' else 'tts' if command=='voice' else None
        if key and not (key=='tts' and cfg['tts'].get('api')=='local'):python=cfg.get(key,{}).get('python') or python
    script,prefix=routes[command]
    subprocess.run([python,'-B',str(PACKAGE/'scripts'/script)]+prefix+args,check=True,timeout=1800)
if __name__=='__main__':
    try:main()
    except Exception as e:print('STOP:',e,file=sys.stderr);sys.exit(1)
