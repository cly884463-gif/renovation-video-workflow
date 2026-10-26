"""Portable, fail-closed renovation renderer. Python 3.10+, Pillow, FFmpeg."""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, unicodedata
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def save(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def text_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def canon(text):
    return ''.join(c for c in text if not c.isspace() and not unicodedata.category(c).startswith('P'))

def require(ok, message):
    if not ok: raise ValueError(message)

def run(cmd, cwd=None, timeout=1800):
    p = subprocess.run([str(x) for x in cmd], cwd=cwd, capture_output=True, encoding='utf-8', errors='replace', timeout=timeout)
    if p.returncode: raise RuntimeError(p.stderr[-6000:] or p.stdout[-6000:])
    return p.stdout

def probe(cfg, path):
    return json.loads(run([cfg['ffprobe'], '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))

def resolve(value, base):
    p = Path(value)
    return p.resolve() if p.is_absolute() else (base/p).resolve()

def load_config(path):
    cfg = read(path)
    cfg['_base'] = str(Path(path).resolve().parent)
    cfg['workspace'] = str(resolve(cfg['workspace'], Path(cfg['_base'])))
    for key in ('shared_root','approvals'):
        if cfg.get(key): cfg[key]=str(resolve(cfg[key],Path(cfg['_base'])))
    from source_paths import roots
    roots(cfg)
    for group, fields in [('tts',('reference_audio','python','repo_dir','model_dir')),('asr',('model_path','python'))]:
        for field in fields:
            value=cfg.get(group,{}).get(field)
            if value and (field!='python' or '/' in value or '\\' in value):cfg[group][field]=str(resolve(value,Path(cfg['_base'])))
    for field in ('ffmpeg','ffprobe'):
        value=cfg.get(field,'')
        if '/' in value or '\\' in value:cfg[field]=str(resolve(value,Path(cfg['_base'])))
    if cfg.get('team_directory'):
        team=resolve(cfg['team_directory'],Path(cfg['_base']))
        cfg['team_directory']=str(team);cfg['history']=str(team/'history.json');cfg['approvals']=str(team/'approvals.json')
    return cfg

def load_job(path,cfg):
    job=read(path)
    def expand(value):
        if not isinstance(value,str): return value
        if value.startswith(('@shared/','@library/')):
            from source_paths import expand as expand_source
            return expand_source(value,cfg)
        for prefix,root in [('@workspace/',cfg['workspace']),('@package/',str(PACKAGE))]:
            if value.startswith(prefix):
                require(root,'未配置路径根 '+prefix)
                p=(Path(root)/value[len(prefix):]).resolve()
                require(p.is_relative_to(Path(root).resolve()),'路径越界')
                return str(p)
        return value
    for owner,keys in [(job['copy'],['source']),(job['voice'],['path','alignment_file','asr_result_file','captions_file']),(job['music'],['path']),(job,['review_file'])]+[(s,['path','source','provenance_file']) for s in job['shots']]:
        for key in keys:
            if key in owner:owner[key]=expand(owner[key])
    return job

def output_dir(cfg, value):
    p = resolve(value, Path(cfg['workspace']))
    require(p.is_relative_to(Path(cfg['workspace'])), '输出必须在配置的 workspace 内')
    if p.exists():
        n=2
        while p.with_name(p.name+f'_retry{n}').exists():n+=1
        raise ValueError('输出已存在，保留失败产物用于恢复。检查错误并复用已成功步骤；下一次可使用 --out '+str(p.with_name(p.name+f'_retry{n}')))
    p.mkdir(parents=True)
    return p

def load_brand(cfg):
    require(cfg.get('brand_config'), '请配置 brand_config，品牌素材由使用者提供')
    path=resolve(cfg['brand_config'],Path(cfg['_base']))
    b=read(path)
    for field in ('font','logo','font_codepoints'):
        b[field]=str(resolve(b[field],path.parent))
    b['asset_sha256']={str(resolve(k,path.parent)):v for k,v in b['asset_sha256'].items()}
    require(all(b[field] in b['asset_sha256'] for field in ('font','logo','font_codepoints')), '先运行 setup_brand.py 登记资源哈希')
    return b

def doctor(cfg):
    for tool in ('ffmpeg','ffprobe'): run([cfg[tool], '-version'])
    filters = run([cfg['ffmpeg'], '-hide_banner', '-filters'])
    encoders = run([cfg['ffmpeg'], '-hide_banner', '-encoders'])
    for name in ('libx264','aac'):require(name in encoders,'FFmpeg缺少编码器 '+name)
    for name in (' ass ', ' xfade ', ' sidechaincompress ', ' zscale ', ' tonemap '):
        require(name in filters, 'FFmpeg 缺少滤镜 '+name.strip())
    from PIL import ImageFont
    b = load_brand(cfg)
    require(b['canvas']==[1080,1920] and b['logical_canvas']==[360,640] and b['fps']==30, '当前固定制作合同仅支持1080P竖屏30fps')
    require(b['subtitle']['size']==36 and b['subtitle']['highlight_size']==39 and b['subtitle']['highlight_color']=='#FFD600', '字号/高亮品牌合同变更需同步脚本并重新验证')
    require(4 <= b['transition_frames'] <= 6, '短叠化仅支持4–6帧')
    for name, digest in b['asset_sha256'].items():
        require(sha(PACKAGE/name)==digest, '品牌资源缺失或变更：'+name)
    ImageFont.truetype(str(PACKAGE/b['font']), 36)
    return b

def validate(job, cfg, b):
    from contracts import validate_evidence
    validate_evidence(job,cfg)
    copy = job['copy']
    supported=set(read(b['font_codepoints']))
    all_text=copy['text']+job['city']+''.join(job['cover']['lines'])+job['cover']['theme']
    missing=sorted(set(c for c in canon(all_text) if ord(c) not in supported))
    require(not missing, '品牌字体缺字：'+''.join(missing)+'；需配置经过验证的完整字体，禁止静默回退')
    require(copy['sha256']==text_hash(copy['text']), '批准文案哈希不符')
    require(Path(copy['source']).is_file() and copy['paragraph'], '缺准确文案来源或段落')
    edited = copy['original']
    for change in copy['changes']:
        require(change['kind']=='address' or change.get('authorization'), '正文改动缺逐项授权')
        require(change['before'] in edited, '文案改动来源不匹配')
        edited = edited.replace(change['before'], change['after'])
    require(edited==copy['text'], '使用稿含未登记改动')
    require(copy['review_note'], '缺全文审稿记录')
    voice = job['voice']
    require(voice['text_sha256']==copy['sha256'], '配音与文案不是同一版本')
    require(voice['speed_passes']==1 and voice['speed']==1.21, '配音必须只执行一次 1.21 倍处理')
    require(voice['sha256']==sha(voice['path']), '配音文件变化')
    require(voice['alignment_review'], '缺配音读字及时间对齐核验记录')
    caps = job['captions']; previous = 0
    require(canon(''.join(c['text'] for c in caps))==canon(copy['text']), '字幕文字与批准稿不同')
    from PIL import ImageFont
    font = ImageFont.truetype(str(PACKAGE/b['font']), b['subtitle']['size'])
    high = ImageFont.truetype(str(PACKAGE/b['font']), b['subtitle']['highlight_size'])
    for c in caps:
        require(c['start'] >= previous and c['end'] > c['start'], '字幕时间重叠或倒序')
        previous = c['end']
        lines = c['lines']
        require(1 <= len(lines) <= 2 and ''.join(lines)==canon(c['text']), '字幕换行缺字、多字或含标点')
        flags = [False]*len(''.join(lines))
        for word in c['highlights']:
            require(any(word in line for line in lines), '关键词缺失或被拆行：'+word)
            for match in re.finditer(re.escape(word), ''.join(lines)):
                flags[match.start():match.end()] = [True]*len(word)
        offset = 0
        for line in lines:
            width = sum((high if flags[offset+i] else font).getlength(ch) for i,ch in enumerate(line))
            require(width <= 320, '字幕超出安全宽度，请按语义重排，禁止缩小字号：'+line)
            offset += len(line)
    shots = job['shots']; require(bool(shots), '至少需要一个经过核验的镜头')
    scenes = set()
    for i,s in enumerate(shots):
        require(isinstance(s['frames'], int), '镜头帧数必须为整数')
        require(s['frames'] > 0, '镜头帧数须大于零；按完整动作与语义确定长度')
        require(s['transition'] in ('cut','dissolve'), '仅支持直切或短叠化')
        require(i>0 or s['transition']=='cut', '首镜不设置前置转场')
        require(s['review_note'] and s['intent'] and s['material_basis'] and s['people_basis'], '缺实际选段/语义/材料/人物审核依据')
        require(Path(s['source']).is_file() and s['source_start']>=0 and s['source_duration']>0, '源素材路径或源区间缺失')
        require(s['scene_id'] not in scenes or s.get('reuse_reason'), '片内场景重复，需换镜或记录原因')
        scenes.add(s['scene_id'])
        require(s['sha256']==sha(s['path']), '已审规范化镜头变更')
        v = next(x for x in probe(cfg,s['path'])['streams'] if x['codec_type']=='video')
        extra = b['transition_frames'] if i+1<len(shots) and shots[i+1]['transition']=='dissolve' else 0
        require(int(v['nb_frames']) >= s['frames']+extra, '真实运动余量不足，禁止冻帧补时长')
        require((v['width'],v['height'],v['r_frame_rate'])==(1080,1920,'30/1'), '先规范化为1080x1920 30fps并实看')
        require(v.get('color_transfer') not in ('smpte2084','arib-std-b67'), 'HDR素材未完成SDR转换')
    music = job['music']
    require(music['sha256']==sha(music['path']) and music['identity'] and music['fit_note'], '音乐来源/适配缺失')
    require(0 < music['mix_gain'] <= 10, '混音增益异常，不能累计历史增益')
    history = read(resolve(cfg['history'], Path(cfg['workspace'])))
    from ledger import check_job
    check_job(job,history)
    current = [x for x in history if x['id']!=job['id']]
    existing = next((x for x in history if x['id']==job['id']),None)
    retains_music = existing and existing['music_identity']==music['identity'] and existing['music_sha256']==music['sha256']
    if current and not retains_music:
        require(current[-1]['music_identity']!=music['identity'] and current[-1]['music_sha256']!=music['sha256'], '相邻新视频用了同一BGM')
    require(job['selection_review'], '缺跨片场景和曲目轮换检查记录')
    duration = sum(s['frames'] for s in shots)/30
    vd = float(probe(cfg,voice['path'])['format']['duration'])
    require(vd+.2 <= duration and caps[-1]['end']<=duration, '配音尾部或字幕被截断')
    require(job['cover']['shot'] in range(len(shots)), '封面须取本片已用镜头')
    return duration

def stamp(t):
    cs = round(t*100); return f'{cs//360000}:{cs//6000%60:02d}:{cs//100%60:02d}.{cs%100:02d}'

def captions(job, b, out):
    s=b['subtitle']
    head=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: 360\nPlayResY: 640\nScaledBorderAndShadow: yes\nWrapStyle: 2\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{b['font_family']},{s['size']},&H00FFFFFF,&H00FFFFFF,&HFF000000,&H33000000,0,0,0,0,100,100,0,0,1,0,1,2,20,20,{s['bottom']},1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    events=[]
    for c in job['captions']:
        lines=[]
        for line in c['lines']:
            pattern='|'.join(re.escape(w) for w in sorted(c['highlights'], key=len, reverse=True))
            if pattern:
                line=re.sub(pattern, lambda m: '{\\fs39\\1c&H00D6FF&}'+m[0]+'{\\fs36\\1c&HFFFFFF&}', line)
            lines.append(line)
        events.append(f"Dialogue: 0,{stamp(c['start'])},{stamp(c['end'])},Default,,0,0,0,,"+r'{\fad(30,30)}'+r'\N'.join(lines)+'\n')
    (out/'captions.ass').write_text(head+''.join(events),encoding='utf-8-sig')

def make_cover(job,cfg,b,out):
    from PIL import Image, ImageDraw, ImageFont
    cover=job['cover']; shot=job['shots'][cover['shot']]
    require(0 <= cover['time'] < shot['frames']/30, '封面抽帧超出选用区间')
    run([cfg['ffmpeg'],'-v','error','-n','-ss',cover['time'],'-i',shot['path'],'-frames:v',1,out/'base.png'])
    im=Image.open(out/'base.png').convert('RGBA')
    logo=Image.open(PACKAGE/b['logo']).convert('RGBA'); logo.thumbnail((360,360)); im.alpha_composite(logo,(32,32))
    def label(text, xy, size, color, angle=0):
        layer=Image.new('RGBA',(1080,500)); d=ImageDraw.Draw(layer); f=ImageFont.truetype(str(PACKAGE/b['font']),size)
        # The approved font lacks U+0020; space is layout, never draw a .notdef box.
        width=sum(size*.25 if c==' ' else d.textlength(c,font=f) for c in text)
        require(width<=1020, '封面文字超宽，需明确调整品牌模板')
        line_top=min(f.getbbox(c,anchor="la")[1] for c in text if c != " ")
        x=0
        for ch in text:
            if ch==' ': x+=size*.25; continue
            d.text((x+7,209-line_top),ch,font=f,fill=(0,0,0,190),anchor='la')
            d.text((x,200-line_top),ch,font=f,fill=color,anchor='la')
            x+=d.textlength(ch,font=f)
        if angle: layer=layer.rotate(angle,resample=Image.Resampling.BICUBIC,expand=False,center=(0,200))
        im.alpha_composite(layer,(xy[0],xy[1]-200))
    layout=b['cover']; city=layout['city']; headline=layout['headline']; theme=layout['theme']
    label(job['city'],tuple(city['xy']),city['size'],city['color'])
    # PIL positive angle tilts the line upwards to the right, matching CSS -7deg.
    label(cover['lines'][0],tuple(headline['xy']),headline['size'],headline['color'],headline['angle'])
    label(cover['lines'][1],(headline['xy'][0],headline['xy'][1]+headline['line_gap']),headline['size'],headline['color'],headline['angle'])
    label(cover['theme'],tuple(theme['xy']),theme['size'],theme['color'])
    im.convert('RGB').save(out/'cover.png')

def render(job,cfg,b,out):
    duration=validate(job,cfg,b); make_cover(job,cfg,b,out); captions(job,b,out)
    shutil.copy2(PACKAGE/b['font'],out/'brand.ttf')
    shots=job['shots']; n=len(shots); parts=[]; cmd=[cfg['ffmpeg'],'-v','error','-n']
    for i,s in enumerate(shots):
        cmd+=['-threads','1','-i',s['path']]
        extra=b['transition_frames'] if i+1<n and shots[i+1]['transition']=='dissolve' else 0
        parts.append(f"[{i}:v]fps=30,trim=end_frame={s['frames']+extra},settb=AVTB,setpts=PTS-STARTPTS,setsar=1,format=yuv420p[c{i}]")
    prev='c0'; total=shots[0]['frames']
    for i,s in enumerate(shots[1:],1):
        operation=f"xfade=transition=fade:duration={b['transition_frames']/30}:offset={total/30:.9f}" if s['transition']=='dissolve' else 'concat=n=2:v=1:a=0'
        parts.append(f'[{prev}][c{i}]{operation}[x{i}]'); prev=f'x{i}'; total+=s['frames']
    cmd+=['-loop','1','-framerate','30','-i',str(out/'cover.png'),'-loop','1','-framerate','30','-i',str(PACKAGE/b['logo']),'-i',job['voice']['path'],'-stream_loop','-1','-i',job['music']['path']]
    parts += [f'[{prev}]trim=end_frame={total},ass=captions.ass:fontsdir=.[sub]', f'[{n+1}:v]scale=360:-1,format=rgba[logo]', '[sub][logo]overlay=32:32[branded]', f'[branded][{n}:v]overlay=0:0:enable=eq(n\\,0),format=yuv420p[v]', f'[{n+2}:a]apad,asplit=2[voice][control]', f'[{n+3}:a]volume={job["music"]["mix_gain"]},afade=t=in:d=0.5,afade=t=out:st={duration-2}:d=2[bed]', '[bed][control]sidechaincompress=threshold=0.03:ratio=5:attack=15:release=300[ducked]', f'[voice][ducked]amix=inputs=2:normalize=0,atrim=duration={duration},alimiter=limit=0.89:level=0[a]']
    cmd+=['-filter_complex_threads','1','-filter_complex',';'.join(parts),'-map','[v]','-map','[a]','-frames:v',str(total),'-t',str(duration),'-c:v','libx264','-preset','fast','-crf','19','-threads','3','-c:a','aac','-b:a','192k','-ar','48000','-map_metadata','-1','-movflags','+faststart',str(out/'video.mp4')]
    save(out/'job.json',job); save(out/'render_command.json',cmd)
    run(cmd,cwd=out)
    report=verify(cfg,out,total)
    save(out/'receipt.json',{'status':'rendered_pending_visual_and_listening_review','job_sha256':sha(out/'job.json'),'video_sha256':sha(out/'video.mp4'),'machine_checks':report})

def verify(cfg,out,total):
    p=probe(cfg,out/'video.mp4'); v=next(x for x in p['streams'] if x['codec_type']=='video')
    require((v['width'],v['height'],v['r_frame_rate'],int(v['nb_frames']))==(1080,1920,'30/1',total),'成片规格不符')
    from frames import extract
    extract(cfg,out/'video.mp4',{frame:out/f'frame_{frame}.png' for frame in (0,1,30,31,total//2,total-1)})
    save(out/'probe.json',p)
    return {'full_decode':False,'frames':total,'visual_review':'pending','full_listening':'pending','note':'完整音视频解码、黑段与峰值检查统一在必需qa阶段执行'}

def main():
    p=argparse.ArgumentParser(); p.add_argument('command',choices=['doctor','validate','preview','render']); p.add_argument('--config',required=True); p.add_argument('--job'); p.add_argument('--out')
    args=p.parse_args(); cfg=load_config(args.config); b=doctor(cfg)
    if args.command=='doctor': print('环境、目录和品牌资源检查通过；不等于LAN配音或成片验收通过'); return
    require(args.job, '需要 --job'); job=load_job(args.job,cfg)
    if args.command!='render': validate(job,cfg,b)
    if args.command=='validate': print('制作计划机器检查通过；语义、曝光与听感仍需实际核验'); return
    require(args.out, '需要 --out 新版本目录'); out=output_dir(cfg,args.out)
    if args.command=='preview': make_cover(job,cfg,b,out); captions(job,b,out)
    else: render(job,cfg,b,out)
    print(out)

if __name__=='__main__':
    try: main()
    except Exception as e: print('STOP:',e,file=sys.stderr); sys.exit(1)
