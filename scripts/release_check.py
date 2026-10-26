"""Conservative source-only publication scan; no uploads or credential access."""
import argparse,hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'engine/scripts'))
from package import inventory,check
from production import save

def public_files():
 for p in ROOT.rglob('*'):
  if p.is_file() and not any(x in {'.git','__pycache__','.venv','local','private','work'} for x in p.relative_to(ROOT).parts) and p.suffix!='.pyc':yield p

def scan():
 errors=[];count=0
 allowed={'.py','.md','.json','.bat','.txt','.yml','.yaml','.gitignore'}
 patterns=[r'(?i)[A-Z]:[/\\](?:ASTRA|Users|develop)',r'192\.168\.\d+\.\d+',r'(?i)(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{15,}',r'史上最完整共享|陈翰文|ASUS-PC']
 for p in public_files():
  count+=1;rel=p.relative_to(ROOT).as_posix()
  if p.suffix not in allowed and p.name not in ('.gitignore','.gitattributes','LICENSE'):errors.append(rel+': unexpected file type');continue
  s=p.read_text(encoding='utf-8-sig')
  # The scanner contains its own detection patterns, not production data.
  if p.name=='release_check.py':continue
  for pattern in patterns:
   if re.search(pattern,s):errors.append(rel+': private-data pattern matched')
 if errors:raise ValueError('\n'.join(errors))
 print('PUBLIC SCAN PASS',count,'text files; pattern-based, manual review still required')

def main():
 p=argparse.ArgumentParser();p.add_argument('--refresh-manifest',action='store_true');a=p.parse_args()
 scan()
 if a.refresh_manifest:save(ROOT/'engine/package-manifest.json',dict(schema_version=3,version='0.1.0',snapshot_date='2026-10-26',files=inventory(ROOT/'engine')))
 print('ENGINE MANIFEST',check(ROOT/'engine')['version'])
if __name__=='__main__':main()
