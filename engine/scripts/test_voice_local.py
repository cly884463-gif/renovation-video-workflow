"""Real isolated worker/FFmpeg with a synthetic model fixture, not actual weights."""
import argparse,json,sys,math,struct,wave
from pathlib import Path
from unittest.mock import patch
from production import save,load_config,probe,read
from voice_local import check_local
from voice_lan import main,service_check


def test():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--python',required=True);a=p.parse_args()
    root=Path(a.out).resolve();root.mkdir(parents=True,exist_ok=False)
    repo=root/'中文 model repo';(repo/'cosyvoice/cli').mkdir(parents=True);(repo/'third_party/Matcha-TTS').mkdir(parents=True)
    for part in ['cosyvoice/__init__.py','cosyvoice/cli/__init__.py']:(repo/part).write_text('',encoding='utf8')
    (repo/'cosyvoice/cli/cosyvoice.py').write_text('''import torch
class CosyVoice3:
    sample_rate=24000
    def inference_zero_shot(self,text,prompt,reference,stream,speed):
        assert stream is False and speed==1.0
        assert prompt=='You are a helpful assistant.<|endofprompt|>参考声音'
        from pathlib import Path
        assert Path(reference).is_file()
        yield {'tts_speech':torch.sin(torch.arange(12000).reshape(1,-1)*0.08)*0.1}
        yield {'tts_speech':torch.sin(torch.arange(12000).reshape(1,-1)*0.08)*0.1}
def AutoModel(model_dir,load_trt,load_vllm,fp16):
    assert not load_trt and not load_vllm and not fp16
    return CosyVoice3()
''',encoding='utf8')
    model=root/'本机权重';model.mkdir();(model/'CosyVoice-BlankEN').mkdir()
    for name in ['cosyvoice3.yaml','llm.pt','flow.pt','hift.pt','campplus.onnx','speech_tokenizer_v3.onnx']:(model/name).write_bytes(b'fixture')
    ref=root/'参考.wav'
    with wave.open(str(ref),'wb') as w:w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(b'\0\0'*16000)
    cfg=dict(workspace='work',ffmpeg='ffmpeg',ffprobe='ffprobe',source_roots={},tts=dict(api='local',python=str(Path(a.python).resolve()),repo_dir=repo.name,model_dir=model.name,reference_audio=ref.name,reference_authorized=True,prompt_text='参考声音',timeout_seconds=120,seed=811))
    config=root/'machine.json';save(config,cfg);loaded=load_config(config);cases=[]
    assert loaded['tts']['model_dir']==str(model);assert loaded['tts']['repo_dir']==str(repo);cases.append('relative_unicode_space_paths')
    assert '尚未' in check_local(loaded['tts']);cases.append('honest_precheck')
    try:check_local(dict(loaded['tts'],model_dir=str(root/'missing')))
    except ValueError:cases.append('missing_model_rejected_no_download')
    else:raise AssertionError('missing model accepted')
    try:service_check(dict(api='http',url='http://192.0.2.10:9881'))
    except ValueError:cases.append('remote_voice_url_rejected')
    else:raise AssertionError('remote service accepted')
    text=root/'sample.txt';text.write_text('测试正文',encoding='utf8')
    with patch('sys.argv',['voice_lan','generate','--config',str(config),'--text',str(text),'--out','sample']),patch('urllib.request.urlopen',side_effect=AssertionError('local mode attempted HTTP')):
        main()
    out=root/'work/sample';v=read(out/'voice.json');assert v['api']=='local' and v['speed_passes']==1 and v['speed']==1.21
    raw=float(probe(loaded,out/'narration_raw.wav')['format']['duration']);final=float(probe(loaded,out/'narration.wav')['format']['duration']);assert abs(raw-1)<.005 and .78<final<.88
    cases+=['local_worker_existing_interpreter','model_chunks_joined_in_order','no_http_call','real_ffmpeg_single_speed_pass','retained_request_log_raw_and_final']
    save(root/'result.json',dict(passed=True,cases=cases,boundary='Synthetic CosyVoice3 API fixture using real PyTorch/FFmpeg; no actual model weights or subjective listening tested'))
    print('PASS',len(cases),'local voice checks')


if __name__=='__main__':test()
