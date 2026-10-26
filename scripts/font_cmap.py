"""Read Unicode coverage from sfnt cmap formats 4/12 without extra dependencies."""
import struct
from pathlib import Path

def codepoints(path):
 data=Path(path).read_bytes()
 def u16(p):return struct.unpack_from('>H',data,p)[0]
 def u32(p):return struct.unpack_from('>I',data,p)[0]
 if data[:4] not in (b'\x00\x01\x00\x00',b'OTTO',b'true'):raise ValueError('请使用独立TTF/OTF字体，不支持字体集合')
 tables={data[p:p+4]:u32(p+8) for p in range(12,12+16*u16(4),16)}
 cmap=tables[b'cmap'];result=set()
 for i in range(u16(cmap+2)):
  rec=cmap+4+8*i;platform=u16(rec);enc=u16(rec+2)
  if not (platform==0 or (platform==3 and enc in (1,10))):continue
  sub=cmap+u32(rec+4);fmt=u16(sub)
  if fmt==12:
   for j in range(u32(sub+12)):
    p=sub+16+12*j;start,end,glyph=u32(p),u32(p+4),u32(p+8)
    if end>0x10FFFF or start>end:raise ValueError('无效Unicode字符范围')
    result.update(range(start+(glyph==0),end+1))
  elif fmt==4:
   n=u16(sub+6)//2;ends=sub+14;starts=ends+2*n+2;deltas=starts+2*n;ranges=deltas+2*n
   for j in range(n):
    start,end=u16(starts+2*j),u16(ends+2*j);delta=u16(deltas+2*j);offset=u16(ranges+2*j)
    for cp in range(start,min(end,65534)+1):
     glyph=u16(ranges+2*j+offset+2*(cp-start)) if offset else cp
     mapped=((glyph+delta)&65535) if glyph else 0
     if not offset:mapped=(cp+delta)&65535
     if mapped:result.add(cp)
 if not result:raise ValueError('字体缺少支持的Unicode cmap格式4/12')
 return sorted(result)
