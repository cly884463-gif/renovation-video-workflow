"""CosyVoice HTTP WAV adapter; explicit Gradio compatibility, never auto-retry."""
import argparse, json, os, sys, time, uuid, urllib.request, urllib.error, socket, wave, io, threading
from pathlib import Path
from production import save, load_config, output_dir, require, run, sha, text_hash, resolve, probe

PARAMETERS=['tts_text','mode_checkbox_group','sft_dropdown','prompt_text','prompt_wav_upload','prompt_wav_record','instruct_text','seed','stream','speed']


def transport(tts):
    mode=tts.get('api','http');require(mode in ('local','http','gradio'),'tts.api须为local、http或gradio，不自动猜测切换')
    return mode


def service_check(tts):
    mode=transport(tts)
    if mode=='local':
        from voice_local import check_local
        return check_local(tts)
    base=tts['url'].rstrip('/')
    from urllib.parse import urlsplit
    require(urlsplit(base).hostname in ('127.0.0.1','localhost','::1'), '新版仅连接本机配音；请填写localhost或127.0.0.1及实际端口')
    require(base.startswith(('http://','https://')),'tts.url须为服务根地址')
    def get(path):
        with urllib.request.urlopen(base+path,timeout=10) as r:return json.load(r)
    if mode=='gradio':
        info=get('/gradio_api/info')
        require([x['parameter_name'] for x in info['named_endpoints']['/generate_audio']['parameters']]==PARAMETERS,'Gradio接口参数不匹配')
        return 'Gradio接口通过；尚未合成或确认音色'
    require(get('/api/health').get('status')=='ok','HTTP声音服务健康检查未通过')
    spec=get('/openapi.json');body=spec['paths']['/api/tts']['post']['requestBody']['content']['multipart/form-data']['schema']
    if '$ref' in body:body=spec['components']['schemas'][body['$ref'].split('/')[-1]]
    require({'tts_text','mode','prompt_text','prompt_wav','seed','speed'}.issubset(body['properties']),'HTTP声音服务参数不匹配')
    return 'HTTP /api/tts接口通过；尚未合成或确认音色'


def multipart(tts,text,reference):
    boundary='----cosy'+uuid.uuid4().hex;parts=[]
    fields={'tts_text':text,'mode':'zero_shot','prompt_text':tts['prompt_text'],'seed':str(tts.get('seed',811)),'speed':'1'}
    for key,value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode('utf8'))
    require(reference.stat().st_size<=32*1024*1024,'参考音频超过32MB，请使用获准的短参考片段')
    suffix=reference.suffix.lower();require(suffix in ('.wav','.mp3','.m4a','.flac','.ogg'),'参考音频格式不支持')
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="prompt_wav"; filename="reference{suffix}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    parts.extend([reference.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()])
    return boundary,b''.join(parts)


def http_audio(tts,text,reference,out,event):
    boundary,body=multipart(tts,text,reference)
    request=urllib.request.Request(tts['url'].rstrip('/')+'/api/tts',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    timeout=float(tts.get('timeout_seconds',900));require(1<=timeout<=1200,'timeout_seconds须为1–1200秒')
    event('request','提交参考音频并等待服务器合成；不自动重试')
    stop=threading.Event();started=time.monotonic()
    def heartbeat():
        while not stop.wait(15):print('配音请求仍在等待响应/接收中，已等待 '+str(round(time.monotonic()-started))+' 秒；不代表获知服务器队列位置',flush=True)
    thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:
            require(response.status==200,'HTTP状态异常：'+str(response.status))
            event('download','收到响应，正在接收WAV')
            media=response.headers.get('Content-Type','').split(';')[0].lower()
            require(media in ('audio/wav','audio/x-wav','application/octet-stream'),'服务器未返回WAV，Content-Type='+media)
            data=response.read(256*1024*1024+1);require(len(data)<=256*1024*1024,'响应音频超过256MB')
            length=response.headers.get('Content-Length')
            if length:require(len(data)==int(length),'WAV响应下载不完整')
        require(data[:4]==b'RIFF' and data[8:12]==b'WAVE','响应不是有效WAV，不能当作音频继续')
        with wave.open(io.BytesIO(data),'rb') as w:
            expected=w.getnframes()*w.getnchannels()*w.getsampwidth()
            require(expected>0 and len(w.readframes(w.getnframes()))==expected,'WAV为空或音频帧被截断')
        dest=out/'service.wav';dest.write_bytes(data);return dest
    except urllib.error.HTTPError as e:
        detail=e.read(3000).decode('utf8','replace')
        raise ValueError(f'HTTP {e.code}：{detail}；参数错误请修配置，服务错误请查服务日志；本次未重试') from e
    except (TimeoutError,socket.timeout) as e:
        raise ValueError('配音请求超时；服务器可能仍在处理，先核对服务任务状态，禁止自动重复提交') from e
    except urllib.error.URLError as e:
        raise ValueError('配音连接失败：'+str(e.reason)+'；检查同事电脑网络/代理/服务地址，不自动切换接口') from e
    finally:stop.set();thread.join(timeout=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['check','generate']);p.add_argument('--config',required=True);p.add_argument('--text');p.add_argument('--out');a=p.parse_args()
    cfg=load_config(a.config);tts=cfg['tts'];mode=transport(tts)
    require(tts.get('reference_authorized') is True,'须先配置已获授权的参考声音')
    require(tts.get('reference_audio'),'reference_audio为空，禁止默认音色替代')
    reference=resolve(tts['reference_audio'],Path(cfg['_base']));require(reference.is_file(),'参考声音不可访问')
    require(tts.get('prompt_text','').strip(),'prompt_text须填写参考音频准确原话')
    if a.command=='check':print(service_check(tts));return
    require(a.text and a.out,'需要--text及新的--out目录')
    text=Path(a.text).read_text('utf-8-sig').strip();require(text,'配音文本为空')
    out=output_dir(cfg,a.out);started=time.monotonic();state=dict(api=mode,status='running',events=[])
    def event(stage,message):
        state['stage']=stage;state['elapsed_seconds']=round(time.monotonic()-started,2);state['events'].append(dict(stage=stage,message=message,elapsed_seconds=state['elapsed_seconds']));save(out/'request_status.json',state);print(message,flush=True)
    try:
        event('precheck','检查参考音频和所选接口 '+mode)
        probe(cfg,reference);service_check(tts)
        if mode=='local':
            from voice_local import generate_local
            audio=generate_local(cfg,text,reference,out,event)
        elif mode=='http':audio=http_audio(tts,text,reference,out,event)
        else:
            os.environ['GRADIO_TEMP_DIR']=str(out/'cache');os.environ['HF_HOME']=str(out/'cache/hf')
            from gradio_client import Client,handle_file
            event('request','显式Gradio模式：提交并等待，不自动重试')
            timeout=float(tts.get('timeout_seconds',900));require(1<=timeout<=1200,'timeout_seconds须为1–1200秒')
            client=Client(tts['url'],verbose=False,download_files=False)
            job=client.submit(tts_text=text,mode_checkbox_group='3s极速复刻',sft_dropdown='',prompt_text=tts['prompt_text'],prompt_wav_upload=handle_file(str(reference)),prompt_wav_record=None,instruct_text='',seed=tts.get('seed',811),stream=False,speed=1,api_name='/generate_audio')
            result=job.result(timeout=timeout)
            require(isinstance(result,dict) and result.get('url'),'Gradio未返回可访问音频URL')
            audio=result['url'];event('download','接收Gradio音频流')
        event('decode','验证音频并转为原速48kHz WAV')
        run([cfg['ffmpeg'],'-v','error','-xerror','-n','-i',audio,'-c:a','pcm_s16le','-ar','48000',out/'narration_raw.wav'],timeout=120)
        event('speed','仅执行一次1.21倍提速')
        run([cfg['ffmpeg'],'-v','error','-xerror','-n','-i',out/'narration_raw.wav','-af','atempo=1.21','-ar','48000',out/'narration.wav'],timeout=120)
        require(float(probe(cfg,out/'narration.wav')['format']['duration'])>0,'配音为空')
        save(out/'voice.json',dict(path=str(out/'narration.wav'),sha256=sha(out/'narration.wav'),raw_sha256=sha(out/'narration_raw.wav'),text_sha256=text_hash(text),speed=1.21,speed_passes=1,engine='CosyVoice3 '+mode+' zero-shot',api=mode,alignment_review='',status='pending_full_asr_alignment_and_listening'))
        state['status']='succeeded';event('done','配音文件已保存；仍需全文识别和听感核验')
    except Exception as e:
        state.update(status='failed',error=type(e).__name__+': '+str(e),elapsed_seconds=round(time.monotonic()-started,2));save(out/'request_status.json',state);raise
    print(out)


if __name__=='__main__':
    try:main()
    except Exception as e:print('STOP:',e,file=sys.stderr);sys.exit(1)
