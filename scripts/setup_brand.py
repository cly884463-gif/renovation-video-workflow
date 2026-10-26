"""Register user-owned brand assets outside the distributable engine."""
import argparse,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine/scripts'))
from production import read,save,sha,require

def main():
 p=argparse.ArgumentParser();p.add_argument('--font',required=True);p.add_argument('--logo',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 out=Path(a.out).resolve();require(not out.is_relative_to(ROOT/'engine'),'品牌配置应位于engine外');require(not out.exists(),'保留已有配置，请指定新路径')
 font=Path(a.font).resolve();logo=Path(a.logo).resolve();require(font.is_file() and logo.is_file(),'字体或Logo不存在')
 from PIL import Image,ImageFont
 from font_cmap import codepoints
 Image.open(logo).verify()
 points=codepoints(font);family=ImageFont.truetype(str(font),36).getname()[0]
 require(family and points,'字体缺名称或字符映射')
 cp=out.with_name(out.stem+'-font-codepoints.json');require(not cp.exists(),'字符表已存在')
 out.parent.mkdir(parents=True,exist_ok=True);save(cp,points)
 b=read(ROOT/'examples/brand.example.json');b.update(font=str(font),logo=str(logo),font_family=family,font_codepoints=str(cp),asset_sha256={str(x):sha(x) for x in (font,logo,cp)})
 save(out,b);print(out)
if __name__=='__main__':main()
