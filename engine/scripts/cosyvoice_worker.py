"""Isolated process using the colleague's existing CosyVoice Python environment."""
import argparse, json, sys, random, wave
from pathlib import Path


def synthesize(request):
    repo=Path(request['repo_dir']).resolve();model=Path(request['model_dir']).resolve()
    if not (model/'cosyvoice3.yaml').is_file():raise ValueError('Expected an existing local CosyVoice3 model')
    # Keep repository imports out of the base rendering interpreter.
    sys.path.insert(0,str(repo));sys.path.insert(1,str(repo/'third_party/Matcha-TTS'))
    import numpy as np
    import torch
    from cosyvoice.cli.cosyvoice import AutoModel
    seed=int(request['seed']);random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)
    cosy=AutoModel(model_dir=str(model),load_trt=False,load_vllm=False,fp16=False)
    if type(cosy).__name__!='CosyVoice3':raise ValueError('Loaded model is not CosyVoice3')
    prompt=request['prompt_text']
    if '<|endofprompt|>' not in prompt:prompt='You are a helpful assistant.<|endofprompt|>'+prompt
    frames=[]
    for output in cosy.inference_zero_shot(request['text'],prompt,request['reference'],stream=False,speed=1.0):
        audio=output['tts_speech'].detach().cpu()
        if audio.ndim!=2 or audio.shape[0]!=1 or audio.shape[1]==0:raise ValueError('Expected nonempty mono model audio')
        if not torch.isfinite(audio).all():raise ValueError('Model returned nonfinite audio')
        frames.append(audio)
    if not frames:raise ValueError('Model returned no audio')
    pcm=(torch.cat(frames,dim=1).squeeze(0).clamp(-1,1).numpy()*32767).astype('<i2').tobytes()
    dest=Path(request['output'])
    with dest.open('xb') as f:
        with wave.open(f,'wb') as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(int(cosy.sample_rate));w.writeframes(pcm)
    print('Local CosyVoice3 raw audio saved; speed=1.0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);a=p.parse_args()
    synthesize(json.loads(Path(a.request).read_text('utf-8')))
