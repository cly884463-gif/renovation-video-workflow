"""Versioned, deterministic file inventory; does not claim online freshness."""
import argparse,hashlib,json,zipfile
from pathlib import Path
from production import PACKAGE,read,save,sha,require

def inventory(root):
    return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='package-manifest.json'}

def check(root=PACKAGE):
    m=read(root/'package-manifest.json');require(m['schema_version']==3,'迁移包版本不支持')
    actual=inventory(root)
    missing=sorted(set(m['files'])-set(actual));extra=sorted(set(actual)-set(m['files']));changed=sorted(k for k in set(actual)&set(m['files']) if actual[k]!=m['files'][k])
    require(not(missing or extra or changed),'技能包校验失败：缺失='+str(missing)+'；新增='+str(extra)+'；改变='+str(changed)+'。machine配置、工作记录和输出应放技能目录外；不要重建manifest绕过。')
    require(read(root/'configs/release.json')['version']==m['version'],'版本不一致')
    return m

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['check','build']);p.add_argument('--out');a=p.parse_args()
    if a.command=='check':print(json.dumps(check(),ensure_ascii=False)[:160]);return
    require(a.out,'需要项目内ZIP输出路径');dest=Path(a.out).resolve();require(not dest.exists(),'输出已存在，换新版本文件名')
    release=read(PACKAGE/'configs/release.json');save(PACKAGE/'package-manifest.json',dict(schema_version=3,version=release['version'],snapshot_date=release['snapshot_date'],files=inventory(PACKAGE)))
    check();dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(list(inventory(PACKAGE))+['package-manifest.json']):z.write(PACKAGE/name,Path(PACKAGE.name)/name)
    print(dest,sha(dest))
if __name__=='__main__':main()
