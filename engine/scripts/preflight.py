"""Collect readiness gaps by stage; never equate interface presence with voice QA."""
import argparse,json,sys,subprocess,urllib.request,os,shutil
from pathlib import Path
from production import load_config,doctor,resolve,require,save,probe


def inspect(cfg,stage='all',online=False):
    rows=[]
    def test(name,fn,optional=False):
        try:
            detail=fn();rows.append(dict(item=name,status='pass',detail=str(detail or '通过')))
        except Exception as e:rows.append(dict(item=name,status='warning' if optional else 'missing',detail=str(e)))
    def runtime(group,modules):
        python=cfg.get(group,{}).get('python') or sys.executable
        code='import sys; assert sys.version_info >= (3,10); '+ '; '.join('import '+x for x in modules)+'; print(sys.executable)'
        r=subprocess.run([python,'-B','-c',code],capture_output=True,text=True,encoding='utf8',errors='replace',timeout=40)
        require(r.returncode==0,r.stderr[-1500:] or r.stdout);return r.stdout.strip()
    def directory(value):
        from source_paths import expand
        p=Path(expand(value,cfg)) if value.startswith(('@shared/','@library/')) else resolve(value,Path(cfg['_base']))
        require(p.is_dir(),'目录不可访问：'+str(p));return p
    def reference():
        t=cfg.get('tts',{});require(t.get('reference_authorized') is True,'参考声音未标明已获授权')
        require(t.get('reference_audio'),'reference_audio为空；禁止使用默认音色')
        p=Path(t['reference_audio']);require(p.is_file(),'参考声音不存在：'+str(p))
        require(t.get('prompt_text','').strip(),'prompt_text须填写参考声音的准确原话')
        probe(cfg,p);return '音频可解码；原话与音色仍须短样人工确认'
    def model():
        a=cfg.get('asr',{});require(a.get('model_path'),'model_path为空')
        p=Path(a['model_path']);require(p.is_dir(),'模型目录不存在：'+str(p))
        for name in ('config.yaml','model.pt','tokens.json'):
            require((p/name).is_file() and (p/name).stat().st_size>0,'Paraformer模型缺文件：'+str(p/name))
        return '核心文件存在；须用短样align验证加载与时间戳'
    test('base_python',lambda:runtime('base',['PIL']))
    test('render_tools_and_brand',lambda:doctor(cfg) and 'FFmpeg、滤镜及品牌资源通过')
    def storage():
        p=Path(cfg['workspace'])
        while not p.exists():p=p.parent
        require(os.access(p,os.W_OK),'workspace父目录不可写：'+str(p))
        free=shutil.disk_usage(p).free/(1024**3)
        require(free>=cfg.get('minimum_free_gb',2),'可用空间不足：'+str(round(free,2))+'GB')
        return str(round(free,2))+'GB可用；实际创建输出时仍核对权限'
    test('workspace_storage',storage)
    if stage in ('all','assets'):
        for i,value in enumerate(cfg.get('material_roots',[])):test('material_root_'+str(i),lambda v=value:directory(v),optional=True)
        test('copy_root',lambda:directory(cfg['copy_root']))
        for field in ('history','approvals'):
            def datafile(f=field):
                from production import read
                p=resolve(cfg[f],Path(cfg['workspace']) if f=='history' else Path(cfg['_base']));read(p);return p
            test(field,datafile)
    if stage in ('all','voice'):
        from voice_lan import transport,service_check
        test('voice_transport',lambda:transport(cfg['tts']))
        test('voice_python',lambda:runtime('tts',['gradio_client'] if cfg['tts'].get('api','http')=='gradio' else (['torch','soundfile'] if cfg['tts'].get('api')=='local' else ['urllib.request','wave'])))
        test('voice_reference',reference)
        if online or cfg['tts'].get('api')=='local':
            test('voice_service',lambda:service_check(cfg['tts']))
        else:rows.append(dict(item='voice_service',status='unverified',detail='使用--online检查局域网服务'))
    if stage in ('all','asr'):
        test('asr_python',lambda:runtime('asr',['torch','funasr']))
        test('asr_model',model)
    rows.append(dict(item='subjective_short_sample',status='unverified',detail='需实际声音短样、识别对齐及封面字幕预览；本检查不自动宣称整套可制作'))
    if not cfg.get('team_directory'):rows.append(dict(item='team_sync',status='warning',detail='当前为本机历史；团队去重需各电脑配置同一个team_directory'))
    return dict(passed=not any(x['status']=='missing' for x in rows),stage=stage,checks=rows)


def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--stage',choices=['all','assets','voice','asr','render'],default='all');p.add_argument('--online',action='store_true');p.add_argument('--out');a=p.parse_args()
    cfg=load_config(a.config);report=inspect(cfg,a.stage,a.online)
    if a.out:
        out=resolve(a.out,Path(cfg['workspace']));require(out.is_relative_to(Path(cfg['workspace'])) and not out.exists(),'检查报告须在workspace内且不能覆盖旧文件');out.parent.mkdir(parents=True,exist_ok=True);save(out,report)
    print(json.dumps(report,ensure_ascii=False,indent=2));sys.exit(0 if report['passed'] else 2)


if __name__=='__main__':main()
