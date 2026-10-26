"""Synthetic renderer smoke test, NOT semantic/voice approval. Retains all evidence."""
import argparse,sys,subprocess
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine/scripts'))
import production
from production import save,read,sha,doctor,render,load_config
from evidence import qa

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--font',required=True);a=p.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=False)
 def call(args):subprocess.run(list(map(str,args)),check=True,capture_output=True)
 from PIL import Image,ImageDraw
 im=Image.new('RGBA',(300,100),(255,255,255,240));ImageDraw.Draw(im).text((20,30),'DEMO / TEST',fill='black');im.save(out/'logo.png')
 call([sys.executable,ROOT/'scripts/setup_brand.py','--font',a.font,'--logo',out/'logo.png','--out',out/'brand.json'])
 cfg=dict(workspace=str(out),ffmpeg='ffmpeg',ffprobe='ffprobe',brand_config=str(out/'brand.json'),source_roots={},tts={},asr={});save(out/'machine.json',cfg);cfg=load_config(out/'machine.json');b=doctor(cfg)
 shots=[]
 for i,color in enumerate(['0x234455','0x554433']):
  f=out/f'shot{i}.mp4';call(['ffmpeg','-v','error','-n','-f','lavfi','-i',f'color=c={color}:s=1080x1920:r=30:d=3.2','-c:v','libx264','-preset','ultrafast','-threads','2','-pix_fmt','yuv420p',f]);shots.append(dict(path=str(f),frames=90,transition='cut' if i==0 else 'dissolve'))
 for n,freq,dur in [('voice',440,5.7),('music',220,6)]:call(['ffmpeg','-v','error','-n','-f','lavfi','-i',f'sine=frequency={freq}:sample_rate=48000:duration={dur}','-af','volume=0.1',out/f'{n}.wav'])
 job=dict(city='示例',shots=shots,cover=dict(shot=0,time=.3,lines=['技术渲染测试','不含客户素材'],theme='测试'),voice=dict(path=str(out/'voice.wav')),music=dict(path=str(out/'music.wav'),mix_gain=.12),captions=[dict(start=0,end=3,lines=['字幕重点标黄'],highlights=['重点']),dict(start=3,end=6,lines=['转场技术测试'],highlights=['转场'])])
 renderdir=out/'render';renderdir.mkdir()
 # Only bypass business-evidence validation for these synthetic color cards.
 # Production CLI and delivery never use this patch. QA stays pending.
 with patch.object(production,'validate',return_value=6):render(job,cfg,b,renderdir)
 qadir=out/'qa';qadir.mkdir();qa(cfg,job,renderdir/'video.mp4',qadir);q=read(qadir/'qa.json')
 assert q['machine_pass'] and q['full_decode'] and q['visual_review']=='pending' and not q['subjective_listening']
 save(out/'result.json',dict(passed=True,boundary='Synthetic color cards and tones; renderer/QA only, no real TTS, ASR or business approval',video_sha256=sha(renderdir/'video.mp4')))
 print('MEDIA SMOKE PASS',renderdir/'video.mp4')
if __name__=='__main__':main()
