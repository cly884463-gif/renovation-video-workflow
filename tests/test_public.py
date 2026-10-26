import datetime,json,sys,uuid,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'engine/scripts'))
import batch
from production import save,load_config,load_brand

class BatchTests(unittest.TestCase):
 def setUp(self):
  base=ROOT/'local/tests';base.mkdir(parents=True,exist_ok=True);self.root=base/uuid.uuid4().hex;self.root.mkdir()
  (self.root/'publish/a').mkdir(parents=True);self.c=dict(delivery_root=str(self.root/'publish'),workspace=str(self.root/'work'),ffmpeg='ffmpeg',ffprobe='ffprobe',accounts=[dict(id='a',city='Demo',folder='a',weekdays=[0])]);self.date='2026-11-02'
 def test_offline_is_not_missing(self):
  self.c['delivery_root']=str(self.root/'offline')
  with self.assertRaises(ValueError):batch.inventory(self.c,self.date)
 def test_schedule_and_resume(self):
  r=batch.inventory(self.c,'2026-11-03');self.assertEqual(r['accounts'][0]['status'],'not_scheduled')
  r=batch.inventory(self.c,self.date);self.assertEqual(r['accounts'][0]['status'],'needs_production')
  (self.root/'work'/self.date/'a').mkdir();r=batch.inventory(self.c,self.date);self.assertEqual(r['accounts'][0]['status'],'resume_existing')
 def test_unknown_directory(self):
  (self.root/'publish/new-account').mkdir();self.assertEqual(batch.inventory(self.c,self.date)['unconfigured_folders'],['new-account'])
 def test_invalid_video_not_available(self):
  (self.root/'publish/a'/f'{self.date} 待发布 bad.mp4').write_bytes(b'broken')
  with patch.object(batch,'media',side_effect=ValueError('invalid')):r=batch.inventory(self.c,self.date)
  self.assertEqual(r['accounts'][0]['status'],'needs_production');self.assertEqual(len(r['accounts'][0]['invalid']),1)
 def test_verified_cache_requires_same_hash(self):
  p=self.root/'publish/a'/f'{self.date} 待发布 Demo.mp4';p.write_bytes(b'first')
  def fake(c,p):return dict(sha256=batch.sha(p),full_decode=True,bytes=p.stat().st_size,duration=3)
  with patch.object(batch,'media',side_effect=fake) as m:
   batch.inventory(self.c,self.date);batch.inventory(self.c,self.date);self.assertEqual(m.call_count,1)
   p.write_bytes(b'changed');batch.inventory(self.c,self.date);self.assertEqual(m.call_count,2)
 def test_unsafe_names(self):
  for value in ['../x','a/b','a\\b','CON','x.','x:ads','']:
   with self.assertRaises(ValueError):batch.name(value)
 def test_review_hash_and_escape(self):
  b=self.root/'work'/self.date;b.mkdir(parents=True);(b/'v.mp4').write_bytes(b'fixture');items=[dict(account='<script>',kind='video',file='v.mp4',sha256=batch.sha(b/'v.mp4'))];save(b/'review_items.json',items);batch.review(self.c,self.date)
  self.assertIn('&lt;script&gt;',(b/'review.html').read_text(encoding='utf-8'));items[0]['sha256']='bad';save(b/'review_items.json',items)
  with self.assertRaises(ValueError):batch.review(self.c,self.date)
 def test_delivery_requires_actual_review_flags(self):
  p=self.root/'receipt.json';save(p,dict(status='ready_for_user_review',subjective_listening=False,realtime_playback=False))
  with self.assertRaises(ValueError):batch.deliver(self.c,self.date,'a',p)
 def test_approved_copy_and_no_overwrite(self):
  src=self.root/'source.mp4';src.write_bytes(b'fixture');q=self.root/'qa.json';sha=batch.sha(src)
  save(q,dict(video_sha256=sha,machine_pass=True,visual_review='accepted',subjective_listening=True,realtime_playback=True,reviewer='test',review_note='synthetic unit test',listening_note='synthetic unit test'))
  r=self.root/'r.json';save(r,dict(status='reviewed_delivery',subjective_listening=True,realtime_playback=True,video=str(src),sha256=sha,qa=str(q)))
  with patch.object(batch,'media',return_value={}):batch.deliver(self.c,self.date,'a',r);batch.deliver(self.c,self.date,'a',r)
  dst=self.root/'publish/a'/f'{self.date} 待发布 Demo旧房翻新.mp4';self.assertEqual(dst.read_bytes(),b'fixture');dst.write_bytes(b'user change')
  with self.assertRaises(ValueError):batch.deliver(self.c,self.date,'a',r)
  self.assertEqual(dst.read_bytes(),b'user change')
 def test_empty_approvals(self):
  a=json.loads((ROOT/'engine/data/approvals.json').read_text(encoding='utf-8'));self.assertFalse(a['presenters']);self.assertFalse(a['materials'])
 def test_brand_is_external_and_hashed(self):
  brand=self.root/'brand.json';save(brand,dict(font='font.ttf',logo='logo.png',font_codepoints='cmap.json',asset_sha256={}))
  with self.assertRaises(ValueError):load_brand(dict(brand_config=str(brand),_base=str(self.root)))

if __name__=='__main__':unittest.main()
