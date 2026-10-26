"""HTTP contract, malformed payload, timeout and no-retry tests; no real synthesis."""
import argparse,io,json,wave,urllib.error
from pathlib import Path
from unittest.mock import patch
from production import save
from voice_lan import http_audio,multipart,service_check,transport,PARAMETERS


class Response:
    def __init__(self,data,media='audio/wav',length=None):
        self.data=data;self.status=200;self.headers={'Content-Type':media}
        if length is not None:self.headers['Content-Length']=str(length)
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return self.data


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    buf=io.BytesIO()
    with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0'*480)
    wav=buf.getvalue();ref=out/'reference.wav';ref.write_bytes(wav);tts=dict(url='http://localhost',prompt_text='参考原话',seed=811,timeout_seconds=3)
    results=[]
    def passed(name,condition=True):assert condition,name;results.append(name)
    passed('default_http',transport(tts)=='http')
    passed('explicit_gradio',transport(dict(tts,api='gradio'))=='gradio')
    try:transport(dict(tts,api='auto'))
    except ValueError:passed('no_implicit_fallback')
    else:raise AssertionError('unknown transport accepted')
    boundary,body=multipart(tts,'测试文字',ref)
    passed('multipart_contract',b'name="prompt_wav"' in body and b'name="mode"\r\n\r\nzero_shot' in body and b'name="speed"\r\n\r\n1\r\n' in body and '参考原话'.encode() in body and wav in body)
    with patch('voice_lan.urllib.request.urlopen',return_value=Response(wav,length=len(wav))) as call:
        dest=http_audio(tts,'测试',ref,out,lambda *x:None)
        passed('wav_response_saved',dest.read_bytes()==wav and call.call_count==1)
    failures=[('http_400',urllib.error.HTTPError('http://localhost',400,'bad',{},io.BytesIO(b'bad parameters'))),('http_500',urllib.error.HTTPError('http://localhost',500,'bad',{},io.BytesIO(b'inference failed'))),('timeout',TimeoutError('wait')),('connection',urllib.error.URLError('unreachable'))]
    for name,error in failures:
        with patch('voice_lan.urllib.request.urlopen',side_effect=error) as call:
            try:http_audio(tts,'测试',ref,out,lambda *x:None)
            except ValueError:passed(name+'_no_retry',call.call_count==1)
            else:raise AssertionError(name)
    for name,response in [('json_response',Response(b'{}','application/json')),('fake_wav',Response(b'not wav')),('truncated_download',Response(wav,length=len(wav)+1)),('truncated_pcm',Response(wav[:-20]))]:
        with patch('voice_lan.urllib.request.urlopen',return_value=response):
            try:http_audio(tts,'测试',ref,out,lambda *x:None)
            except (ValueError,EOFError,wave.Error):passed(name)
            else:raise AssertionError(name)
    spec={'paths':{'/api/tts':{'post':{'requestBody':{'content':{'multipart/form-data':{'schema':{'$ref':'#/components/schemas/Tts'}}}}}}},'components':{'schemas':{'Tts':{'properties':{k:{} for k in ('tts_text','mode','prompt_text','prompt_wav','seed','speed')}}}}}
    with patch('voice_lan.urllib.request.urlopen',side_effect=[Response(b'{"status":"ok"}'),Response(json.dumps(spec).encode())]) as call:
        passed('http_precheck_uses_http_contract','HTTP' in service_check(tts) and call.call_count==2)
    with patch('voice_lan.urllib.request.urlopen',return_value=Response(json.dumps({'named_endpoints':{'/generate_audio':{'parameters':[{'parameter_name':k} for k in PARAMETERS]}}}).encode())) as call:
        passed('explicit_gradio_precheck','Gradio' in service_check(dict(tts,api='gradio')) and call.call_count==1)
    save(out/'result.json',dict(passed=True,cases=results));print('PASS',len(results),'voice HTTP tests')


if __name__=='__main__':main()
