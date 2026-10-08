-- Read-only, bounded export helpers. Loaded in a separate environment, not installed
-- as a game callback. Python pauses/resumes the simulation around this session.
return function(internal)
    local CT = api.type.ComponentType
    local terrain = api.engine.getComponent(api.engine.util.getWorld(), CT.TERRAIN)
    local bounds = api.engine.terrain.getBoundingBox()
    local minX, minY = math.floor(bounds.min.x/256), math.floor(bounds.min.y/256)
    local maxX, maxY = math.ceil(bounds.max.x/256)-1, math.ceil(bounds.max.y/256)-1
    local tileColumns, tileRows = maxX-minX+1, maxY-minY+1
    local modelIds = {}
    api.engine.forEachEntity(function(id)
        if api.engine.getComponent(id, CT.MODEL_INSTANCE_LIST) ~= nil then
            modelIds[#modelIds+1] = id
        end
    end)
    table.sort(modelIds)

    local function integer(n, low, high)
        assert(type(n)=="number" and n==math.floor(n) and n>=low and n<=high, "invalid export range")
        return n
    end
    local function checkPaused()
        assert(api.engine.getComponent(api.engine.util.getWorld(), CT.GAME_SPEED).speedup==0,
            "simulation resumed during export")
    end
    local commands = {}
    commands.info = function()
        checkPaused()
        local layers={}
        for name,layer in pairs(terrain.dataMaps) do
            local size=layer:getSize()
            layers[#layers+1]={name=name,width=size.x,height=size.y}
        end
        table.sort(layers,function(a,b) return a.name<b.name end)
        return {map=internal.commands.get_map_info(), state=internal.commands.get_game_state(),
            terrain={minTileX=minX,minTileY=minY,tileColumns=tileColumns,tileRows=tileRows,
                totalTiles=tileColumns*tileRows,baseResolution=internal.toPlain(terrain.baseResolution),
                offsetZ=terrain.offsetZ}, modelEntities=#modelIds,layers=layers}
    end
    commands.terrain = function(args)
        checkPaused()
        local offset=integer(args.offset,0,tileColumns*tileRows)
        local count=integer(args.count,1,8)
        local out={}
        for i=offset,math.min(offset+count,tileColumns*tileRows)-1 do
            local x,y=minX+i%tileColumns,minY+math.floor(i/tileColumns)
            local id=api.engine.terrain.getHeightmapEntity(api.type.Vec2i.new(x,y))
            local comp=api.engine.getComponent(id,CT.TERRAIN_TILE_HEIGHTMAP)
            assert(comp~=nil,"missing terrain tile")
            local raw={}
            for j=1,#comp.vertices do raw[j]=comp.vertices[j] end
            local side=math.sqrt(#raw)
            assert(side==math.floor(side),"non-square terrain tile")
            local probes={}
            for _,j in ipairs({1,math.floor(#raw/2)+1,#raw}) do
                local px=x*256+((j-1)%side)*terrain.baseResolution.x
                local py=y*256+math.floor((j-1)/side)*terrain.baseResolution.y
                probes[#probes+1]={index=j,height=api.engine.terrain.getBaseHeightAt(api.type.Vec2f.new(px,py))}
            end
            out[#out+1]={x=x,y=y,id=id,side=side,values=raw,probes=probes}
        end
        return out
    end
    commands.layer = function(args)
        checkPaused()
        local layer=terrain.dataMaps[args.name]
        assert(layer~=nil,"unknown map data layer")
        local size=layer:getSize()
        local offset=integer(args.offset,0,size.x*size.y)
        local count=integer(args.count,1,8192)
        local out={}
        for i=offset,math.min(offset+count,size.x*size.y)-1 do
            out[#out+1]=layer:at(i%size.x,math.floor(i/size.x))
        end
        return {offset=offset,total=size.x*size.y,values=out}
    end
    commands.models = function(args)
        checkPaused()
        local offset=integer(args.offset,0,#modelIds)
        local count=integer(args.count,1,100)
        local out={}
        for i=offset+1,math.min(offset+count,#modelIds) do
            local id=modelIds[i]
            local comp=api.engine.getComponent(id,CT.MODEL_INSTANCE_LIST)
            assert(comp~=nil,"model entity disappeared while paused: "..id)
            local row={id=id,dynamic=comp.dynamic,fat={},thin={}}
            for j=1,#comp.fatInstances do
                row.fat[j]=internal.toPlain(comp.fatInstances[j],0,nil,"ModelInstance")
            end
            for j=1,#comp.thinInstances do
                row.thin[j]=internal.toPlain(comp.thinInstances[j],0,nil,"ThinModelInstance")
            end
            out[#out+1]=row
        end
        return out
    end
    commands.check = function()
        checkPaused()
        local seen,count={},0
        for _,id in ipairs(modelIds) do seen[id]=true end
        api.engine.forEachEntity(function(id)
            if api.engine.getComponent(id,CT.MODEL_INSTANCE_LIST)~=nil then
                assert(seen[id],"model entity added during export")
                seen[id]=nil
                count=count+1
            end
        end)
        assert(next(seen)==nil,"model entity removed during export")
        return {modelEntities=count,state=internal.commands.get_game_state()}
    end
    return {run=function(name,args) return internal.json.encode(assert(commands[name],"unknown export command")(args or {})) end}
end
