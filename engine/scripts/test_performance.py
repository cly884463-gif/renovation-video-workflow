"""Actual media and cache invalidation regression; fixtures remain under --out."""
import argparse,copy
from pathlib import Path
from unittest.mock import patch
from production import read,save,load_config,load_job,run
from evidence import create,frame
from frames import extract
from material_index import search

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--job',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    root=Path(a.out).resolve();root.mkdir(parents=True,exist_ok=False)
    cfg=load_config(a.config);job=load_job(a.job,cfg);cases=[]
    def make(name,j,prior=None):
        out=root/name;out.mkdir()
        import frames
        with patch.object(frames,'run',wraps=run) as calls:create(cfg,j,out,prior)
        return out,calls.call_count
    first,count=make('initial',job);assert count==len(job['shots']);cases.append('one_decoder_per_shot')
    second,count=make('reuse',job,first/'review.json');assert count==0
    assert all(s['status']=='pending' and s['reused_images'] for s in read(second/'review.json')['shots']);cases.append('reuse_images_without_auto_approval')
    altered=copy.deepcopy(job);altered['shots'][2]['intent']+=' revised'
    _,count=make('intent',altered,first/'review.json');assert count==1;cases.append('changed_intent_rebuilds')
    altered=copy.deepcopy(job);altered['shots'][1]['transition']='dissolve'
    _,count=make('handles',altered,first/'review.json');assert count==2;cases.append('next_transition_invalidates_handle_frames')
    first_review=read(first/'review.json');Path(first_review['shots'][0]['artifacts'][0]['path']).write_bytes(b'broken')
    _,count=make('corrupt',job,first/'review.json');assert count==1;cases.append('corrupt_cached_image_rebuilt')
    exact=root/'exact';exact.mkdir();numbers=[0,15,30]
    extract(cfg,job['shots'][0]['path'],{n:exact/f'batch_{n}.png' for n in numbers})
    from PIL import Image
    for n in numbers:
        frame(cfg,job['shots'][0]['path'],n,exact/f'single_{n}.png')
        assert Image.open(exact/f'batch_{n}.png').tobytes()==Image.open(exact/f'single_{n}.png').tobytes()
    cases.append('batch_frames_pixel_identical_to_exact_indices')
    try:extract(cfg,job['shots'][0]['path'],{999:exact/'missing.png'})
    except ValueError:cases.append('absent_frame_rejected')
    else:raise AssertionError('missing frame silently accepted')
    assets=root/'assets';assets.mkdir();(assets/'南阳.mp4').write_bytes(b'index only')
    index_cfg=dict(workspace=str(root/'index'),_base=str(root),material_roots=[str(assets)])
    assert search(index_cfg,['南阳'])['matches']==1
    (assets/'南阳新.mp4').write_bytes(b'index only')
    assert search(index_cfg,['南阳'])['matches']==1
    assert search(index_cfg,['南阳'],refresh=True)['matches']==2;cases.append('index_explicit_refresh')
    changed=copy.deepcopy(index_cfg);changed['material_roots']=[str(root/'absent')]
    try:search(changed,[])
    except ValueError:cases.append('index_root_change_rejected')
    else:raise AssertionError('stale root accepted')
    old=read(Path(index_cfg['workspace'])/'material_index.json')
    try:search(changed,[],refresh=True)
    except ValueError:pass
    else:raise AssertionError('missing index root accepted')
    assert read(Path(index_cfg['workspace'])/'material_index.json')==old;cases.append('failed_refresh_preserves_index')
    save(root/'result.json',dict(passed=len(cases),cases=cases));print(len(cases),'performance regressions passed')

if __name__=='__main__':main()
