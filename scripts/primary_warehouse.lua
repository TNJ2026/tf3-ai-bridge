-- One designated warehouse, one canonical STOCK_LIST, one pass per station.
-- Local to this evaluation. Does not infer access from distance or construction IDs.
local warehouseRows=nil
local function primaryWarehouse(warehouse, stationFacilities, selectedStock)
 local CT=api.type.ComponentType
 assert(type(warehouse)=='number' and warehouse>=0,'Primary warehouse required')
 assert(api.engine.getComponent(warehouse,CT.CONSTRUCTION),'Primary warehouse construction missing')
 local aliases,lists,stocks={},{},{}
 if not warehouseRows then
  warehouseRows={}
  api.engine.forEachEntityWithComponent(function(id)
   local w=api.engine.getComponent(id,CT.WAREHOUSE)
   warehouseRows[#warehouseRows+1]={id=id,component=w}
  end,CT.WAREHOUSE)
 end
 for _,row in ipairs(warehouseRows)do
  local id,w=row.id,row.component
  if w.construction==warehouse then
   local sid=w.stockList
   assert(type(sid)=='number' and sid>=0 and api.engine.entityExists(sid),'Invalid warehouse stock')
   local list=assert(api.engine.getComponent(sid,CT.STOCK_LIST),'Missing stock list')
   aliases[id]=sid;aliases[sid]=sid;lists[sid]=list
   stocks[#stocks+1]={entity=id,stockList=sid}
  end
 end
 local ids={};for sid in pairs(lists)do ids[#ids+1]=sid end;table.sort(ids)
 assert(#ids>0,'Primary warehouse has no inventory')
 if selectedStock==nil then assert(#ids==1,'Multiple inventories: explicitly select primaryStockList');selectedStock=ids[1]end
 assert(lists[selectedStock],'Selected inventory does not belong to primary warehouse')
 local out={primaryWarehouse=warehouse,primaryStockList=selectedStock,stocks=stocks,
  coverage={},stations={},capacity=0,quantity=0,verified=true,operationalAccepted=false,
  inventoryById={},commonWarehouseStockIds={}}
 for i,s in ipairs(lists[selectedStock].stocks)do
   assert(type(s.capacity)=='number' and s.capacity>=0 and s.capacity<math.huge,'Unreadable stock capacity')
  out.capacity=out.capacity+s.capacity
  local amount=api.engine.system.simEntityAtStockSystem.getStockCount(selectedStock,i-1)
  assert(type(amount)=='number' and amount>=0 and amount<math.huge,'Unreadable stock quantity')
  out.quantity=out.quantity+amount
 end
 out.inventoryById[tostring(selectedStock)]={stockList=selectedStock,capacity=out.capacity,quantity=out.quantity}
 local cache={};local count=0
 for role,entity in pairs(stationFacilities)do
  count=count+1
  local c=assert(api.engine.getComponent(entity,CT.CONSTRUCTION),'Station construction missing')
  local covered=false;local stations={}
  for _,st in ipairs(c.stations)do
   if cache[st]==nil then
    local caught=false
    for _,id in pairs(api.engine.system.catchmentAreaSystem.getStationCatchables(st,true))do
     if aliases[id]==selectedStock then caught=true end
    end
    cache[st]=caught
   end
   stations[#stations+1]={station=st,coversPrimaryStock=cache[st]}
   covered=covered or cache[st]
  end
  out.stations[role]=stations;out.coverage[role]=covered and {selectedStock}or{}
  out.verified=out.verified and covered
 end
 assert(count>0,'No cargo station facilities designated')
 if out.verified then out.commonWarehouseStockIds={selectedStock}end
 return out
end
