"""Local FunASR alignment or audited import. No model download and no blanket equivalence."""
import argparse, os, json, importlib.metadata
from pathlib import Path
from production import read,save,sha,canon,text_hash,require,load_config,output_dir,probe,run

def compare(expected,recognized,allowances):
    require(len(expected)==len(recognized),'识别长度不同，先排查漏读/多读；不可强行按位置对齐')
    differences=[]; used=set()
    for i,(e,r) in enumerate(zip(expected,recognized)):
        if e==r:continue
        matches=[(k,x) for k,x in enumerate(allowances) if x.get('index')==i and x.get('expected')==e and x.get('recognized')==r and x.get('reason') and x.get('kind') in ('numeric','reviewed_homophone')]
        require(len(matches)==1,f'未核准识别差异 index={i}: {e}/{r}')
        k,x=matches[0];used.add(k);differences.append(x)
    require(len(used)==len(allowances),'差异说明包含未实际发生或重复的项')
    return differences

def make_alignment(text,result,pages,duration,allowances):
    expected=canon(text);item=result[0];recognized=canon(item['text'])
    differences=compare(expected,recognized,allowances)
    tokens=item['text'].split();times=item['timestamp'];require(len(tokens)==len(times),'识别token和时间戳数量不同')
    chars=[];previous=0
    for token,(start,end) in zip(tokens,times):
        token=canon(token);require(token and 0<=start<=end,'时间戳非法')
        # Small model tail overshoot is clipped, large overshoot fails.
        require(end<=duration*1000+200,'时间戳超出音轨200ms以上')
        for i,c in enumerate(token):
            st=min(duration,(start+(end-start)*i/len(token))/1000);en=min(duration,(start+(end-start)*(i+1)/len(token))/1000)
            require(st+0.002>=previous and en>st,'时间戳重叠或零长度')
            chars.append(dict(char=expected[len(chars)],recognized=c,start=st,end=en));previous=en
    require(len(chars)==len(expected),'字符时间戳缺失')
    captions=[];cursor=0
    for page in pages:
        lines=page['lines'];segment=''.join(lines)
        require(segment==canon(segment) and expected[cursor:cursor+len(segment)]==segment,'分页包含标点或与原稿不一致')
        require(1<=len(lines)<=2 and segment,'每页须1–2行非空文本')
        captions.append(dict(text=segment,lines=lines,highlights=page['highlights'],start=chars[cursor]['start'],spoken_end=chars[cursor+len(segment)-1]['end']))
        cursor+=len(segment)
    require(cursor==len(expected),'字幕未覆盖全文');captions[0]['start']=0
    for i,c in enumerate(captions):c['end']=captions[i+1]['start'] if i+1<len(captions) else duration+.22
    return chars,captions,dict(expected=expected,recognized=recognized,exact=expected==recognized,differences=differences,passed=True,subjective_listening=False)

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--audio',required=True);p.add_argument('--text',required=True);p.add_argument('--pages',required=True);p.add_argument('--allowances');p.add_argument('--import-result');p.add_argument('--import-audio-sha256');p.add_argument('--out',required=True);a=p.parse_args()
    cfg=load_config(a.config);out=output_dir(cfg,a.out);text=Path(a.text).read_text('utf-8-sig').strip()
    media_sha256=None
    if Path(a.audio).suffix.lower() in ('.mp4','.mov','.mkv'):
        media_sha256=sha(a.audio);converted=out/'final_mix.wav'
        run([cfg['ffmpeg'],'-v','error','-n','-i',a.audio,'-vn','-ac','1','-ar','16000',converted]);a.audio=str(converted)
    if a.import_result:
        require(a.import_audio_sha256==sha(a.audio),'导入ASR必须提供原识别音频的准确哈希');result=read(a.import_result);engine='imported timestamped ASR'
    else:
        ac=cfg.get('asr',{});model_path=Path(ac.get('model_path',''));require(model_path.is_dir() and ac.get('model_path'),'缺本机ASR模型路径，禁止自动下载')
        for key,sub in {'TEMP':'tmp','TMP':'tmp','HF_HOME':'hf','MODELSCOPE_CACHE':'modelscope','TORCH_HOME':'torch','NUMBA_CACHE_DIR':'numba','MPLCONFIGDIR':'mpl'}.items():
            d=out/'cache'/sub;d.mkdir(parents=True,exist_ok=True);os.environ[key]=str(d)
        os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONDONTWRITEBYTECODE='1')
        import torch
        torch.set_num_threads(2)
        from funasr import AutoModel
        version=importlib.metadata.version('funasr')
        if ac.get('timestamp_adapter')=='astra_funasr_1_3_14':
            require(version=='1.3.14','时间戳适配器只针对已验证的FunASR 1.3.14')
            import funasr.models.paraformer.model as pm
            original=pm.ts_prediction_lfr6_standard
            pm.ts_prediction_lfr6_standard=lambda peaks,alphas,characters,**kw:original(alphas,peaks,characters,**kw)
        model=AutoModel(model=str(model_path),device='cpu',ncpu=2,disable_update=True,disable_pbar=True,trust_remote_code=False)
        result=model.generate(input=a.audio,batch_size_s=60,pred_timestamp=True);engine='FunASR '+version
    save(out/'asr_result.json',result)
    duration=float(probe(cfg,a.audio)['format']['duration'])
    # Save mismatch diagnostics before failing; never lose an unsuccessful transcript.
    save(out/'comparison.json',dict(expected=canon(text),recognized=canon(result[0]['text']),audio_sha256=sha(a.audio),passed=False))
    chars,captions,report=make_alignment(text,result,read(a.pages),duration,read(a.allowances) if a.allowances else [])
    report.update(audio_sha256=sha(a.audio),media_sha256=media_sha256,text_sha256=text_hash(text),engine=engine,result_sha256=sha(out/'asr_result.json'),duration=duration)
    save(out/'character_timings.json',chars);save(out/'captions.json',captions);report['captions_sha256']=sha(out/'captions.json');save(out/'alignment.json',report)
    print(out)
if __name__=='__main__':main()
