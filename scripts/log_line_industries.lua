local CT=api.type.ComponentType;local out={}
for _,sid in ipairs({26829,76244}) do
 local con=api.engine.system.streetConnectorSystem.getConstructionEntityForStation(sid);local c=api.engine.getComponent(con,CT.CONSTRUCTION);local r={station=sid,construction=con,fileName=c.fileName,industries={}}
 for _,id in ipairs(c.industries) do local ind=api.engine.getComponent(id,CT.INDUSTRY);local io=api.engine.util.stock.getInputsOutputsFromRules(ind.stockList);r.industries[#r.industries+1]={id=id,inputs=B.toPlain(io[1]),outputs=B.toPlain(io[2])} end
 out[#out+1]=r
end
return B.json.encode(out)
