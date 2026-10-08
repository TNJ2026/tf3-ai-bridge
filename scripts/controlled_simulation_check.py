"""Controlled simulation check: preserve prior speed, sample actual speed/ticks, stop on speed changes.
Run only against a loaded disposable/checkpoint save. No automatic retry after timeout/crash.
"""
import asyncio, json, time
from pathlib import Path
from tf3_mcp.bridge import Bridge

async def main():
    bridge = Bridge(timeout=3)
    rows = []
    initial = await bridge.call('get_game_state', {}, engine=True)
    if initial.get('speedup') != 0:
        raise RuntimeError('Start paused; do not alter a running user session')
    output = Path('controlled_simulation_trace.json')
    reason = 'completed'
    try:
        await bridge.call('set_game_speed', {'speed': 1}, engine=True)
        started = time.monotonic()
        while time.monotonic() - started < 40:
            state = await bridge.call('get_game_state', {}, engine=True)
            rows.append({'elapsed': time.monotonic()-started, **state})
            output.write_text(json.dumps({'status':'running','samples':rows}, ensure_ascii=False, indent=2), encoding='utf-8')
            if state.get('speedup') != 1:
                reason = 'speed_changed; comparison invalid'
                break
            await asyncio.sleep(0.5)
    except Exception as exc:
        reason = 'failed: ' + str(exc)
    finally:
        try:
            await bridge.call('set_game_speed', {'speed': 0}, engine=True)
        except Exception as exc:
            reason += '; pause unconfirmed: ' + str(exc)
        output.write_text(json.dumps({'status':reason,'samples':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    print(reason)

if __name__ == '__main__':
    asyncio.run(main())
