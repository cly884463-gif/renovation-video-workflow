"""Explicit-date inventory and reviewed delivery. Never starts generation or a timer."""
import argparse,datetime,html,json,re,shutil,subprocess,sys,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine/scripts'))
from production import read,save,sha,require
from ledger import locked,atomic_save

def name(value):
 require(isinstance(value,str) and bool(value.strip()) and not re.search(r'[<>:"/\\|?*\x00-\x1f]',value) and value not in ('.','..') and not value.endswith(('.', ' ')), '不安全的目录或文件名')
 require(value.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]},'保留文件名')
 return value

def config(path):
 path=Path(path).resolve();c=read(path)
 for key in ('delivery_root','workspace'):c[key]=str((path.parent/c[key]).resolve())
 ids=set();folders=set()
 for a in c['accounts']:
  name(a['id']);name(a['city']);name(a['folder'])
  require(a['id'] not in ids and a['folder'] not in folders,'账号ID或目录重复');ids.add(a['id']);folders.add(a['folder'])
  require(a['weekdays'] and all(type(d) is int and 0<=d<=6 for d in a['weekdays']),'weekdays须使用周一0至周日6')
 return c

def media(c,p):
 require(p.is_file() and p.stat().st_size>0,'视频为空或不存在')
 raw=subprocess.check_output([c['ffprobe'],'-v','error','-show_streams','-show_format','-of','json',str(p)],timeout=60)
 m=json.loads(raw);require(any(x['codec_type']=='video' for x in m['streams']) and any(x['codec_type']=='audio' for x in m['streams']),'缺画面或音轨')
 require(float(m['format']['duration'])>0,'时长无效')
 subprocess.run([c['ffmpeg'],'-v','error','-xerror','-i',str(p),'-f','null','-'],check=True,capture_output=True,timeout=1800)
 return dict(sha256=sha(p),bytes=p.stat().st_size,duration=float(m['format']['duration']),full_decode=True)

def inventory(c,date):
 day=datetime.date.fromisoformat(date);root=Path(c['delivery_root']);require(root.is_dir(),'发布根目录离线或未配置；停止检查，未认定全部缺片')
 batch=Path(c['workspace'])/date;batch.mkdir(parents=True,exist_ok=True)
 with locked(batch/'inventory'):
  old=read(batch/'inventory.json') if (batch/'inventory.json').exists() else {'accounts':[]};cache={str(v['path']):v for a in old['accounts'] for v in a.get('valid',[])};rows=[]
  for a in c['accounts']:
   folder=root/a['folder'];require(folder.is_dir() and folder.resolve().is_relative_to(root.resolve()),'账号目录缺失或越界：'+a['id'])
   row=dict(account=a['id'],city=a['city'],folder=str(folder),valid=[],invalid=[])
   if day.weekday() not in a['weekdays']:row['status']='not_scheduled';rows.append(row);continue
   for p in sorted(folder.glob(date+' 待发布 *.mp4')):
    try:
     digest=sha(p);prior=cache.get(str(p));m=prior if prior and prior['sha256']==digest and prior.get('full_decode') else dict(path=str(p),**media(c,p));row['valid'].append(m)
    except (OSError,ValueError,subprocess.SubprocessError) as e:row['invalid'].append(dict(path=str(p),error=str(e)))
   # Existing jobs are resumed, never submitted again by the inventory command.
   local=batch/a['id'];row['status']='available' if row['valid'] else ('resume_existing' if local.exists() else 'needs_production')
   rows.append(row)
  known={a['folder'] for a in c['accounts']};report=dict(date=date,accounts=rows,unconfigured_folders=sorted(p.name for p in root.iterdir() if p.is_dir() and p.name not in known))
  atomic_save(batch/'inventory.json',report);print(json.dumps(report,ensure_ascii=False,indent=2));return report

def review(c,date):
 datetime.date.fromisoformat(date)
 batch=Path(c['workspace'])/date;items=read(batch/'review_items.json');cards=[]
 for r in items:
  p=(batch/r['file']).resolve();require(p.is_relative_to(batch.resolve()) and p.is_file(),'审核文件必须在本批目录')
  require(sha(p)==r['sha256'],'审核媒体已变化')
  tag='audio' if r['kind']=='voice' else 'video';require(r['kind'] in ('voice','video'),'审核类型错误')
  url=urllib.parse.quote(p.relative_to(batch).as_posix())
  cards.append(f'<section><h2>{html.escape(r["account"])}</h2><{tag} controls preload="metadata" src="{url}"></{tag}><p>{html.escape(r.get("text",""))}</p><small>SHA256 {r["sha256"]}</small></section>')
 (batch/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>批次审核</title><style>body{max-width:1100px;margin:24px auto;font-family:system-ui}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}video,audio{width:100%}small{overflow-wrap:anywhere}</style><h1>批次审核 '+date+'</h1><p>按账号＋秒数反馈；此页面不自动批准任何版本。</p><main>'+''.join(cards)+'</main>',encoding='utf-8')
 print(batch/'review.html')

def deliver(c,date,account,receipt):
 datetime.date.fromisoformat(date);a=next(x for x in c['accounts'] if x['id']==account)
 require(datetime.date.fromisoformat(date).weekday() in a['weekdays'],'目标日期不在该账号排期')
 r=read(receipt);require(r['status']=='reviewed_delivery' and r['subjective_listening'] is True and r['realtime_playback'] is True,'需要完整成片听看审核后的finalize回执')
 src=Path(r['video']);require(sha(src)==r['sha256'],'成片与回执哈希不符')
 q=read(r['qa']);require(q['video_sha256']==r['sha256'] and q['machine_pass'] is True and q['visual_review']=='accepted' and q['subjective_listening'] is True and q['realtime_playback'] is True and q['reviewer'] and q['review_note'] and q['listening_note'],'QA不完整或版本不符')
 root=Path(c['delivery_root']).resolve();folder=root/a['folder'];require(folder.is_dir() and folder.resolve().is_relative_to(root),'目标目录离线或越界')
 target=folder/f'{date} 待发布 {a["city"]}旧房翻新.mp4';batch=Path(c['workspace'])/date;batch.mkdir(parents=True,exist_ok=True)
 with locked(batch/('deliver-'+account)):
  if target.exists():require(sha(target)==r['sha256'],'目标存在其他版本，保留原文件；先由用户决定替换方案')
  else:
   media(c,src);partial=target.with_suffix('.mp4.copying')
   with src.open('rb') as f,partial.open('xb') as g:shutil.copyfileobj(f,g,8*1024*1024)
   require(sha(partial)==r['sha256'],'复制校验失败');require(not target.exists(),'目标文件已出现');partial.rename(target)
  require(sha(target)==r['sha256'],'交付文件哈希不符');atomic_save(batch/(account+'-delivery.json'),dict(account=account,date=date,destination=str(target),sha256=r['sha256'],verified=True));print(target)

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['inventory','review','deliver']);p.add_argument('--config',required=True);p.add_argument('--date',required=True);p.add_argument('--account');p.add_argument('--receipt');a=p.parse_args();c=config(a.config)
 if a.command=='inventory':inventory(c,a.date)
 elif a.command=='review':review(c,a.date)
 else:require(a.account and a.receipt,'交付须提供账号和finalize回执');deliver(c,a.date,a.account,a.receipt)
if __name__=='__main__':main()
