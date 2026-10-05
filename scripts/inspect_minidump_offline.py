"""Read Windows minidump exception metadata without starting or touching the game."""
import argparse,json,struct
from pathlib import Path
def inspect(path):
    data=path.read_bytes()
    def u32(o):return struct.unpack_from('<I',data,o)[0]
    def u64(o):return struct.unpack_from('<Q',data,o)[0]
    assert data[:4]==b'MDMP','Not a Windows minidump'
    streams={}
    for n in range(u32(8)):
        o=u32(12)+n*12;streams[u32(o)]=(u32(o+4),u32(o+8))
    modules=[]
    if 4 in streams:
        _,r=streams[4]
        for k in range(u32(r)):
            o=r+4+k*108;name=u32(o+20);size=u32(name)
            modules.append(dict(name=data[name+4:name+4+size].decode('utf-16le'),base=u64(o),size=u32(o+8)))
    def module(address):
        return next((dict(name=m['name'],offset=hex(address-m['base']))for m in modules if m['base']<=address<m['base']+m['size']),None)
    out={'path':str(path.resolve()),'streams':sorted(streams),'modules':len(modules)}
    if 6 in streams:
        _,r=streams[6];ctx=u32(r+164);address=u64(r+24);code=u32(r+8)
        out['exception']={'thread':u32(r),'code':hex(code),'address':hex(address),'module':module(address),'parameters':[u64(r+40+k*8)for k in range(min(15,u32(r+32)))]}
        if u32(r+160)>=256:
            out['registers']={n:hex(u64(ctx+o))for n,o in [('RIP',248),('RSP',152),('RBP',160),('RCX',128),('RDX',136)]}
            rsp=u64(ctx+152)
            if 3 in streams:
                _,t=streams[3]
                for k in range(u32(t)):
                    o=t+4+k*48
                    if u32(o)!=u32(r):continue
                    start,size,at=u64(o+24),u32(o+32),u32(o+36);scan=[]
                    for delta in range(0,min(size,2048),8):
                        va=rsp+delta
                        if start<=va<=start+size-8:
                            value=u64(at+va-start);m=module(value)
                            if m:scan.append({'stackOffset':hex(delta),'address':hex(value),'module':m})
                    out['stackAddressCandidates']=scan[:45]
                    out['stackNote']='Raw stack pointer scan; NOT a symbolized or validated call stack'
    return out
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('path',type=Path);a.add_argument('--output',type=Path);args=a.parse_args();r=inspect(args.path)
    if args.output:args.output.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(r,ensure_ascii=True))
