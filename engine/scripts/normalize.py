"""Normalize one explicitly selected source interval; never mark visual review passed."""
import argparse,sys
from production import *

def main():
    p=argparse.ArgumentParser(); p.add_argument('--config',required=True);p.add_argument('--source',required=True);p.add_argument('--start',type=float,required=True);p.add_argument('--duration',type=float,required=True);p.add_argument('--out',required=True);p.add_argument('--rotate',type=int,choices=[0,90,180,270],default=0);p.add_argument('--crop',help='x:y:width:height after display rotation'); args=p.parse_args()
    cfg=load_config(args.config); require(args.start>=0 and args.duration>0,'源区间无效')
    src=Path(args.source).resolve(); info=probe(cfg,src); v=next(s for s in info['streams'] if s['codec_type']=='video')
    require(args.start+args.duration<=float(info['format']['duration'])+.01,'源区间超出文件')
    out=output_dir(cfg,args.out); filters=[]
    if v.get('color_transfer') in ('smpte2084','arib-std-b67'):
        filters+=['zscale=t=linear:npl=100','format=gbrpf32le','zscale=p=bt709','tonemap=tonemap=hable:desat=0','zscale=t=bt709:m=bt709:r=tv']
    if args.rotate==90:filters+=['transpose=clock']
    elif args.rotate==180:filters+=['hflip','vflip']
    elif args.rotate==270:filters+=['transpose=cclock']
    if args.crop:
        values=[int(x) for x in args.crop.split(':')];require(len(values)==4,'crop须x:y:width:height')
        x,y,w,h=values;require(x>=0 and y>=0 and w>0 and h>0,'crop范围非法');filters+=[f'crop={w}:{h}:{x}:{y}']
    filters+=['scale=1080:1920:force_original_aspect_ratio=increase','crop=1080:1920','setsar=1','fps=30','format=yuv420p']
    run([cfg['ffmpeg'],'-v','error','-n','-ss',args.start,'-i',src,'-t',args.duration,'-vf',','.join(filters),'-an','-c:v','libx264','-preset','fast','-crf','18','-threads','2','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709',out/'normalized.mp4'])
    save(out/'provenance.json',{'source':str(src),'source_start':args.start,'source_duration':args.duration,'source_sha256':sha(src),'path':str(out/'normalized.mp4'),'sha256':sha(out/'normalized.mp4'),'filter':filters,'status':'pending_rotation_crop_exposure_semantics_people_material_review'})
    print(out)

if __name__=='__main__':
    try: main()
    except Exception as e: print('STOP:',e,file=sys.stderr);sys.exit(1)
