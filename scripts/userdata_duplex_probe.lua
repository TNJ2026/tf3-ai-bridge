-- Test-only mailbox; echoes data, never dispatches game commands.
return function(config, emit, clock, decode, encode)
    local started, due, done, ready = nil, 0, false, false
    local count, lastSeq, lastPayload, lastAttempt = 0, 0, nil, nil
    local function report(event, extra)
        local row=extra or {};row.event=event;row.probeId=config.id;row.session=config.session
        row.processed=count;emit(row)
    end
    local function exists(name)
        local names=app.getAllUserdata('mod_presets')
        assert(type(names)=='table','Cannot enumerate directory')
        for _,n in pairs(names) do if n==name or n==name..'.lua' then return true end end
        return false
    end
    local function cleanup(reason)
        done=true
        local cleaned=true
        for _,name in ipairs({config.request,config.response}) do
            local ok,err=pcall(function()
                if exists(name) then
                    local value=decode(app.loadUserdata('mod_presets',name))
                    assert(value.probeId==config.id,'Ownership mismatch; not removed')
                    app.removeUserdata('mod_presets',name)
                    assert(not exists(name),'File remains after removal')
                end
            end)
            if not ok then cleaned=false;report('cleanup_error',{error=tostring(err),filename=name}) end
        end
        report(reason=='passed' and 'complete' or 'failed',{reason=reason,cleaned=cleaned})
    end
    return function()
        if done then return end
        local now=clock();if not now or now<due then return end;due=now+0.1
        started=started or now
        local ok,err=pcall(function()
            if not ready then
                assert(not exists(config.request) and not exists(config.response),'Test filenames already exist')
                ready=true;report('ready')
            end
            if now-started>180 then cleanup('timeout');return end
            if not exists(config.request) then return end
            local req=decode(app.loadUserdata('mod_presets',config.request))
            assert(type(req)=='table' and req.probeId==config.id,'Foreign request; stop')
            assert(type(req.attempt)=='string' and #req.attempt<100,'Invalid attempt')
            if req.attempt==lastAttempt then return end
            lastAttempt=req.attempt
            local response={probeId=config.id,session=config.session,attempt=req.attempt,
                seq=req.seq,processed=count,status='rejected'}
            if req.session~=config.session then response.reason='wrong_session'
            elseif req.op=='finish' and lastSeq==config.rounds and req.seq==lastSeq+1 then cleanup('passed');return
            elseif req.op~='echo' or type(req.seq)~='number' or req.seq%1~=0
                or type(req.payload)~='string' or #req.payload>32768 then response.reason='invalid_request'
            elseif req.seq==lastSeq and req.payload==lastPayload then
                response.status='duplicate';response.payload=lastPayload
            elseif req.seq~=lastSeq+1 or req.seq>config.rounds then response.reason='sequence_or_payload_mismatch'
            else
                count=count+1;lastSeq=req.seq;lastPayload=req.payload
                response.status='ok';response.processed=count;response.payload=req.payload
            end
            app.saveUserdata('mod_presets',config.response,encode(response))
            report('reply',{seq=response.seq,status=response.status,attempt=req.attempt})
        end)
        if not ok then
            if ready then cleanup(tostring(err))
            else done=true;report('failed',{reason=tostring(err),cleaned=false}) end
        end
    end
end
