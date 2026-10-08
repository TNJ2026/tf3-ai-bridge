local out={};for k,v in pairs(api.type) do if type(k)=='string' and (k:find('Edge') or k:find('Proposal')) then out[k]=type(v) end end;return B.json.encode(out)
