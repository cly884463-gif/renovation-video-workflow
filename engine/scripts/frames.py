"""Extract exact frame numbers with one decoder process, preserving full-size evidence."""
from pathlib import Path
from production import run, require


def extract(cfg, video, outputs):
    numbers=sorted(outputs)
    require(numbers and all(isinstance(n,int) and n>=0 for n in numbers),'无效抽帧序号')
    paths=[Path(outputs[n]) for n in numbers]
    require(len(set(paths))==len(paths) and len({p.parent for p in paths})==1,'抽帧输出须唯一且同目录')
    require(not any(p.exists() for p in paths),'抽帧输出已存在')
    suffix=paths[0].suffix
    require(all(p.suffix==suffix for p in paths),'抽帧格式须一致')
    prefix=paths[0].stem+'_batch_'
    pattern=paths[0].parent/(prefix+'%04d'+suffix)
    expression='+'.join(f'eq(n\\,{n})' for n in numbers)
    run([cfg['ffmpeg'],'-v','error','-n','-i',video,'-vf','select='+balanced_sum(expression.split('+')),
         '-fps_mode','vfr','-frames:v',len(numbers),pattern])
    for i,dest in enumerate(paths,1):
        source=dest.parent/(prefix+f'{i:04d}'+suffix)
        require(source.is_file(),'未取得所需帧 '+str(numbers[i-1]))
        source.rename(dest)


def balanced_sum(nodes):
    if len(nodes)==1:return nodes[0]
    middle=len(nodes)//2
    return "("+balanced_sum(nodes[:middle])+"+"+balanced_sum(nodes[middle:])+")"
