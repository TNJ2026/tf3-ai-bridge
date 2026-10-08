local out={};for k,v in pairs(api.type.ComponentType) do if type(v)=='number' and v>=25 and v<=35 then out[k]=v end end;return B.json.encode(out)
