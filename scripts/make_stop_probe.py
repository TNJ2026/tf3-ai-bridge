import json
from pathlib import Path
s=Path('scripts/stop_crosswalk_factory.lua').read_text()
s=s[:s.index(' local pd=')]+'''
 local cmd=api.cmd.makeWorldBuildProposalCmd(p,nil,false,true)
 local out={}
 for _,v in pairs(getmetatable(cmd) or {}) do if type(v)=='table' then for k,f in pairs(v) do if type(k)=='string' then local ok,x=pcall(function()return cmd[k] end);out[k]=ok and type(x) or tostring(x) end end end end
 for _,k in ipairs({'data','proposal','getData'}) do local ok,x=pcall(function()return cmd[k]end);out[k]=ok and type(x) or tostring(x) end
 return B.json.encode(out)
end
'''
Path('scripts/stop_converted_inspect.lua').write_text('local f=assert(load('+json.dumps(s)+',"=stopinspect","t",_ENV))();return f({edge=61156,name="inspect"},B)',encoding='utf-8')
