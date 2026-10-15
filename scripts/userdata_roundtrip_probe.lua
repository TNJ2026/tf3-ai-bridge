-- Standalone diagnostic factory. Only one named file; no engine/game commands.
return function(config, emit, clock)
    local phase, started, due, owns, bReads = 'start', nil, 0, false, 0
    local function report(event, extra)
        local row = extra or {}
        row.event = event; row.probeId = config.id
        row.directory = 'mod_presets'; row.filename = config.filename
        emit(row)
    end
    local function listed()
        local ok, names = pcall(app.getAllUserdata, 'mod_presets')
        if not ok or type(names) ~= 'table' then error('Cannot enumerate preset directory') end
        for _, name in pairs(names) do
            if name == config.filename or name == config.filename .. '.lua' then return true end
        end
        return false
    end
    local function cleanup(reason)
        phase = 'done'
        if not owns then report('failed', {reason=reason, cleaned=false}); return end
        local ok, value = pcall(app.loadUserdata, 'mod_presets', config.filename)
        if not ok or type(value) ~= 'table' or value.probeId ~= config.id then
            report('failed', {reason=reason, cleaned=false, cleanupError='Ownership not verified'}); return
        end
        local removed, err = pcall(app.removeUserdata, 'mod_presets', config.filename)
        local checked, present = pcall(listed)
        report(reason == 'roundtrip_passed' and 'complete' or 'failed',
            {reason=reason, cleaned=removed and checked and not present,
             cleanupError=not removed and tostring(err) or nil, bReads=bReads})
    end
    return function()
        if phase == 'done' then return end
        local now = clock()
        if not now or now < due then return end
        due = now + 0.5
        if not started then started = now end
        local ok, err = pcall(function()
            if phase == 'start' then
                if listed() then
                    phase='done'; report('failed', {reason='Test filename already exists; not overwritten', cleaned=false}); return
                end
                phase='save_attempted'
                app.saveUserdata('mod_presets', config.filename, {probeId=config.id, marker=config.a})
                owns=true; phase='await_a'
                report('saved_a')
            end
            local value = app.loadUserdata('mod_presets', config.filename)
            if type(value) ~= 'table' or value.probeId ~= config.id then error('Readback ownership mismatch') end
            if phase == 'await_a' then
                if value.marker ~= config.a then error('Initial A readback mismatch') end
                phase='await_b'
                report('read_a', {listedInNativePresets=listed(), marker=value.marker})
            elseif phase == 'await_b' then
                if value.marker == config.b then
                    bReads=bReads+1
                    report('read_b', {marker=value.marker, count=bReads})
                    if bReads >= 2 then cleanup('roundtrip_passed') end
                elseif value.marker ~= config.a then error('Unexpected marker') end
            end
            if phase ~= 'done' and now-started > 120 then cleanup('Timed out waiting for external B') end
        end)
        if not ok then cleanup(tostring(err)) end
    end
end
