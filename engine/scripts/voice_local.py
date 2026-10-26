"""Run existing CosyVoice3 in its own environment; no service or model download."""
import os, subprocess, sys, time
from pathlib import Path
from production import require, save, run


def check_local(tts):
    for key in ('repo_dir', 'model_dir', 'python'):
        require(tts.get(key), '本机配音缺少 tts.'+key)
    repo=Path(tts['repo_dir']); model=Path(tts['model_dir'])
    require((repo/'cosyvoice/cli/cosyvoice.py').is_file(), 'repo_dir须为CosyVoice源码根目录')
    require((repo/'third_party/Matcha-TTS').is_dir(), 'CosyVoice缺少third_party/Matcha-TTS')
    for name in ('cosyvoice3.yaml','llm.pt','flow.pt','hift.pt','campplus.onnx','speech_tokenizer_v3.onnx'):
        f=model/name
        require(f.is_file() and f.stat().st_size>0, 'CosyVoice3模型缺文件：'+str(f))
    require((model/'CosyVoice-BlankEN').is_dir(), '模型缺少CosyVoice-BlankEN；请核对已有部署')
    require(Path(tts['python']).is_file(), 'tts.python须指向CosyVoice已有环境的python可执行文件')
    return '本机CosyVoice3核心文件存在；尚未加载权重/合成短样'


def generate_local(cfg,text,reference,out,event):
    t=cfg['tts'];check_local(t)
    # Decode any supported reference format before passing it to the model.
    ref=out/'reference_16k.wav'
    run([cfg['ffmpeg'],'-v','error','-xerror','-n','-i',reference,'-ac','1','-ar','16000',ref],timeout=120)
    request=out/'local_request.json'
    save(request,dict(repo_dir=t['repo_dir'],model_dir=t['model_dir'],text=text,
        prompt_text=t['prompt_text'],reference=str(ref),output=str(out/'service.wav'),seed=int(t.get('seed',811))))
    env=os.environ.copy()
    for name,child in [('TEMP','tmp'),('TMP','tmp'),('HF_HOME','hf'),('MODELSCOPE_CACHE','modelscope'),('TORCH_HOME','torch'),('MPLCONFIGDIR','mpl'),('NUMBA_CACHE_DIR','numba')]:
        path=out/'cache'/child;path.mkdir(parents=True,exist_ok=True);env[name]=str(path)
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    # Keep sequential jobs inside a project from loading two model copies.
    from ledger import locked
    timeout=float(t.get('timeout_seconds',1200));require(1<=timeout<=1200,'本机配音超时须为1–1200秒')
    event('local_inference','调用本机CosyVoice3；模型加载和推理日志见local_inference.log，不调用局域网')
    with locked(Path(cfg['workspace'])/'local_voice',timeout=1):
        with (out/'local_inference.log').open('w',encoding='utf-8') as log:
            child=subprocess.Popen([t['python'],'-B',str(Path(__file__).with_name('cosyvoice_worker.py')),'--request',str(request)],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
            started=time.monotonic()
            try:
                while True:
                    remaining=timeout-(time.monotonic()-started)
                    if remaining<=0:raise TimeoutError('本机模型推理超时；本次子进程已停止，查看日志后再决定是否重试')
                    try:code=child.wait(timeout=min(15,remaining));break
                    except subprocess.TimeoutExpired:print('本机CosyVoice3加载/推理中，已等待 '+str(round(time.monotonic()-started))+' 秒',flush=True)
                require(code==0,'本机CosyVoice3退出码 '+str(code)+'；查看 '+str(out/'local_inference.log')+'；未切换接口或重试')
            finally:
                if child.poll() is None:child.kill();child.wait()
    require((out/'service.wav').is_file(),'本机模型没有输出音频')
    return out/'service.wav'
