"""Filename discovery cache; not evidence of identity, access, material, or freshness."""
import argparse,json,os,time
from pathlib import Path
from production import load_config,read,require,resolve
from ledger import atomic_save
from source_paths import expand

def search(cfg,query,limit=30,refresh=False):
    require(1<=limit<=200,'limit须为1–200')
    cache=Path(cfg['workspace'])/'material_index.json'
    signature={k:cfg.get(k) for k in ('material_roots','source_roots','shared_root','_base')}
    old=read(cache) if cache.exists() else None
    if old and old.get('configuration')!=signature:require(refresh,'素材入口已变化，请用--refresh更新索引')
    if refresh or old is None:
        paths=set()
        for value in cfg['material_roots']:
            root=resolve(expand(value,cfg),Path(cfg['_base']))
            require(root.is_dir(),'索引根不可访问：'+str(root))
            def fail(error):raise error
            for directory,_,names in os.walk(root,onerror=fail,followlinks=False):
                paths.update((Path(directory)/name).as_posix() for name in names)
        old=dict(schema_version=1,configuration=signature,updated_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),paths=sorted(paths))
        cache.parent.mkdir(parents=True,exist_ok=True);atomic_save(cache,old)
    matches=[p for p in old['paths'] if all(q.casefold() in p.casefold() for q in query)]
    return dict(updated_at=old['updated_at'],total_indexed=len(old['paths']),matches=len(matches),paths=matches[:limit],truncated=len(matches)>limit,boundary='仅文件名线索；新增素材需--refresh，使用前仍检查源文件及准确审批')

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--query',action='append',default=[]);p.add_argument('--limit',type=int,default=30);p.add_argument('--refresh',action='store_true');a=p.parse_args()
    print(json.dumps(search(load_config(a.config),a.query,a.limit,a.refresh),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
