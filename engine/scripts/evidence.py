"""Bind review artifacts to actual inputs. Artifacts never imply human approval."""
import argparse, json, math, subprocess, shutil, time
from pathlib import Path
from production import read, save, sha, require, load_config, load_job, output_dir, probe, run

def frame(cfg, video, number, output):
    run([cfg['ffmpeg'],'-v','error','-n','-i',video,'-vf',f'select=eq(n\\,{number})','-frames:v',1,output])
    require(Path(output).is_file(), '未取得所需帧 '+str(number))

def sheet(files, output, labels=None):
    from PIL import Image, ImageDraw
    cols=3; w=240; h=450
    im=Image.new('RGB',(cols*w,math.ceil(len(files)/cols)*h),'#eeeeee')
    for i,f in enumerate(files):
        src=Image.open(f).convert('RGB'); src.thumbnail((240,426))
        x=i%cols*w; y=i//cols*h
        im.paste(src,(x+(240-src.width)//2,y+24))
        ImageDraw.Draw(im).text((x+4,y+4),str(labels[i] if labels else i),fill='black')
    im.save(output)

def binding(s):
    return dict(path=str(Path(s['path']).resolve()),sha256=sha(s['path']),source=str(Path(s['source']).resolve()),source_start=s['source_start'],source_duration=s['source_duration'],frames=s['frames'],transition=s['transition'],intent=s['intent'])

def create(cfg,job,out,reuse_review=None):
    from frames import extract
    started=time.perf_counter();reused=0
    prior=read(reuse_review).get('shots',[]) if reuse_review else []
    reviews=[]
    for i,s in enumerate(job['shots']):
        v=next(x for x in probe(cfg,s['path'])['streams'] if x['codec_type']=='video')
        count=int(v['nb_frames']); extra=6 if i+1<len(job['shots']) and job['shots'][i+1]['transition']=='dissolve' else 0
        last=s['frames']+extra-1; require(last<count,'运动余量不足')
        numbers=sorted(set([0,last//2,last]+list(range(0,last+1,15))))
        current=binding(s);outputs={n:out/f'shot_{i:02}_{n:04}.jpg' for n in numbers}
        previous=next((r for r in prior if r.get('binding')==current and
                       sorted(a['frame'] for a in r.get('artifacts',[]))==numbers),None)
        # Reuse bytes only. Prior semantic/person/material decisions never auto-approve a new job.
        valid=previous and all(Path(a['path']).is_file() and sha(a['path'])==a['sha256'] for a in previous['artifacts'])
        if valid:
            for a in previous['artifacts']:shutil.copy2(a['path'],outputs[a['frame']])
            reused+=1
        else:extract(cfg,s['path'],outputs)
        artifacts=[dict(path=str(outputs[n]),sha256=sha(outputs[n]),frame=n) for n in numbers]
        contact=out/f'shot_{i:02}_contact.jpg';sheet([a['path'] for a in artifacts],contact,numbers)
        reviews.append(dict(shot_index=i,binding=current,artifacts=artifacts,contact=str(contact),status='pending',reviewer='',note='',semantic_score=None,people_kind='',presenter_approval_id=None,material_kind='',material_approval_id=None,reused_images=bool(valid)))
    save(out/'review.json',dict(schema_version=3,shots=reviews,boundary='仅复用哈希核对一致的图片，不继承语义审批；实际核对当前上下文后填写',reused_shots=reused,generated_shots=len(reviews)-reused,elapsed_seconds=round(time.perf_counter()-started,3)))

def qa(cfg,job,video,out):
    render_dir=Path(video).resolve().parent
    receipt=read(render_dir/'receipt.json');rendered_job=read(render_dir/'job.json')
    require(receipt['video_sha256']==sha(video) and receipt['job_sha256']==sha(render_dir/'job.json') and rendered_job==job,'成片与实际渲染收据/job不一致；修改后必须重新render，不能直接给旧片生成新QA')
    duration=sum(s['frames'] for s in job['shots'])/30;total=round(duration*30)
    p=probe(cfg,video);v=next(s for s in p['streams'] if s['codec_type']=='video');a=next(s for s in p['streams'] if s['codec_type']=='audio')
    require((v['width'],v['height'],v['r_frame_rate'],int(v['nb_frames']))==(1080,1920,'30/1',total),'成片规格不符')
    require(abs(float(v['duration'])-float(a['duration']))<.1,'音画时长差超限')
    process=subprocess.run([cfg['ffmpeg'],'-hide_banner','-nostats','-i',str(video),'-vf','blackdetect=d=0.06:pix_th=0.10','-af','astats=metadata=0:reset=0','-f','null','-'],capture_output=True,text=True,encoding='utf-8',errors='replace')
    require(process.returncode==0,'全解码失败');(out/'decode.log').write_text(process.stderr,encoding='utf-8')
    import re
    black=[l for l in process.stderr.splitlines() if 'black_start:' in l]
    peaks=[float(x) for x in re.findall(r'Peak level dB:\s*([-\d.]+)',process.stderr)]
    require(peaks,'缺音频峰值证据')
    groups={'captions':[min(total-1,round((c['start']+c['end'])*15)) for c in job['captions']], 'continuity':list(range(0,total,15)), 'cuts':[], 'shots':[],'opening':[0,1,30,31,total-1]}
    cursor=0
    for i,s in enumerate(job['shots']):
        groups['shots'] += [cursor,min(total-1,cursor+s['frames']//2),cursor+s['frames']-1]
        if i:groups['cuts'] += [cursor-1,cursor,min(total-1,cursor+3),min(total-1,cursor+6)]
        cursor+=s['frames']
    numbers=sorted(set(n for ns in groups.values() for n in ns))
    # One decoder pass, one output per required exact frame.
    expression='+'.join(f'eq(n\\,{n})' for n in numbers)
    run([cfg['ffmpeg'],'-v','error','-n','-i',video,'-vf','select='+balanced_sum(expression.split('+')),'-fps_mode','vfr',out/'frame_%04d.jpg'])
    files={n:out/f'frame_{i+1:04d}.jpg' for i,n in enumerate(numbers)}
    contacts=[]
    # Same required frames, shown only once; group membership remains auditable.
    for k in range(0,len(numbers),9):
        ns=numbers[k:k+9]
        dest=out/f'review_{k//9+1:02}.jpg';sheet([files[n] for n in ns],dest,ns);contacts.append(dict(path=str(dest),sha256=sha(dest)))
    save(out/'frame_groups.json',dict(groups=groups,unique_frames=numbers))
    save(out/'qa.json',dict(schema_version=3,video=str(Path(video).resolve()),video_sha256=sha(video),render_receipt=str(render_dir/'receipt.json'),render_receipt_sha256=sha(render_dir/'receipt.json'),job_sha256=__import__('hashlib').sha256(json.dumps(job,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),full_decode=True,black_segments=black,peak_db=max(peaks),machine_pass=not black and max(peaks)<0,contacts=contacts,visual_review='pending',reviewer='',review_note='',subjective_listening=False,listening_note='',realtime_playback=False))
    save(out/'probe.json',p)

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['shots','qa']);p.add_argument('--config',required=True);p.add_argument('--job',required=True);p.add_argument('--out',required=True);p.add_argument('--video');p.add_argument('--reuse-review');a=p.parse_args()
    cfg=load_config(a.config);job=load_job(a.job,cfg);out=output_dir(cfg,a.out)
    if a.command=='shots':create(cfg,job,out,a.reuse_review)
    else:
        require(a.video,'需要 --video');qa(cfg,job,a.video,out)
    print(out)


def balanced_sum(nodes):
    if len(nodes)==1:return nodes[0]
    middle=len(nodes)//2
    return "("+balanced_sum(nodes[:middle])+"+"+balanced_sum(nodes[middle:])+")"

if __name__=='__main__':main()
