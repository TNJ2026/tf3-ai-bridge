import asyncio, json
from pathlib import Path
from tf3_mcp.server import find_facility_sites

async def main():
    snapshot_path = 'D:/Develop/game/tf3/exports/plan_20261004/snapshot-0365e4257d3f.json'
    out_dir = 'D:/Develop/game/tf3/exports/plan_20261004'

    # Siting requests for city hubs (heliport/cluster) and production hubs
    requests = [
        {
            'name': '黄冈城市集合',
            'kind': 'facility',
            'basis': '城市综合枢纽 (直升机场/货站/客车站/仓库/车库)，占地140x120m，扩建与接驳预留200x180m',
            'current': {'min': {'x': -70, 'y': -60}, 'max': {'x': 70, 'y': 60}},
            'reserved': {'min': {'x': -100, 'y': -90}, 'max': {'x': 100, 'y': 90}},
            'target': {'x': 1236, 'y': 232},
            'radius': 1200,
            'step': 75,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 100,
            'rotations': [0, 45, 90, 135]
        },
        {
            'name': '萍乡城市集合',
            'kind': 'facility',
            'basis': '城市综合枢纽 (含牧场共用接驳)，占地140x120m，扩建预留200x180m',
            'current': {'min': {'x': -70, 'y': -60}, 'max': {'x': 70, 'y': 60}},
            'reserved': {'min': {'x': -100, 'y': -90}, 'max': {'x': 100, 'y': 90}},
            'target': {'x': -2560, 'y': 3272},
            'radius': 1200,
            'step': 75,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 100,
            'rotations': [0, 45, 90, 135]
        },
        {
            'name': '阳泉城市集合',
            'kind': 'facility',
            'basis': '城市综合枢纽 (含伐木场共用接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': -70, 'y': -60}, 'max': {'x': 70, 'y': 60}},
            'reserved': {'min': {'x': -100, 'y': -90}, 'max': {'x': 100, 'y': 90}},
            'target': {'x': -2296, 'y': 112},
            'radius': 1200,
            'step': 75,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 100,
            'rotations': [0, 45, 90, 135]
        },
        {
            'name': '秦皇岛城市集合',
            'kind': 'facility',
            'basis': '城市综合枢纽 (含农场及锯木厂共用接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': -70, 'y': -60}, 'max': {'x': 70, 'y': 60}},
            'reserved': {'min': {'x': -100, 'y': -90}, 'max': {'x': 100, 'y': 90}},
            'target': {'x': 2840, 'y': 3168},
            'radius': 1200,
            'step': 75,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 100,
            'rotations': [0, 45, 90, 135]
        },
        {
            'name': '葫芦岛城市集合',
            'kind': 'facility',
            'basis': '城市综合枢纽 (含黏土坑及砖厂共用接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': -70, 'y': -60}, 'max': {'x': 70, 'y': 60}},
            'reserved': {'min': {'x': -100, 'y': -90}, 'max': {'x': 100, 'y': 90}},
            'target': {'x': -136, 'y': -2928},
            'radius': 1200,
            'step': 75,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 100,
            'rotations': [0, 45, 90, 135]
        },
        {
            'name': '葫芦岛农场独立生产集合',
            'kind': 'facility',
            'basis': '生产端双直升机坪集合 (双坪/仓库/货站)，占地100x80m，预留150x120m',
            'current': {'min': {'x': -50, 'y': -40}, 'max': {'x': 50, 'y': 40}},
            'reserved': {'min': {'x': -75, 'y': -60}, 'max': {'x': 75, 'y': 60}},
            'target': {'x': -3628, 'y': -3688},
            'radius': 450,
            'step': 50,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 80,
            'rotations': [0, 90]
        },
        {
            'name': '黄冈炼油厂生产端集合',
            'kind': 'facility',
            'basis': '炼化双直升机坪集合 (双坪/仓库/货站)，占地100x80m，预留150x120m',
            'current': {'min': {'x': -50, 'y': -40}, 'max': {'x': 50, 'y': 40}},
            'reserved': {'min': {'x': -75, 'y': -60}, 'max': {'x': 75, 'y': 60}},
            'target': {'x': 3504, 'y': -1432},
            'radius': 500,
            'step': 50,
            'ranking': 'flat_first',
            'max_height_range': 6.0,
            'min_separation': 80,
            'rotations': [0, 90]
        }
    ]

    res = await find_facility_sites(snapshot_path, out_dir, requests, max_candidates=3, max_evaluations=20000)
    data = json.loads(res.content[0].text)
    print('Siting completed. Searches count:', len(data.get('searches', [])))
    for s in data.get('searches', []):
        cands = s.get('candidates', [])
        print(f"[{s['name']}]: found {len(cands)} candidates")
        for i, c in enumerate(cands):
            dist = c.get('distanceToTarget', 0)
            slope = c.get('terrain', {}).get('meanSlope', 0)
            hrange = c.get('terrain', {}).get('heightRange', 0)
            pos = c.get('position', {})
            print(f"  Option {i+1}: pos=({pos.get('x',0):.1f}, {pos.get('y',0):.1f}), dist={dist:.1f}m, slope={slope:.3f}, h_range={hrange:.2f}m")

if __name__ == '__main__':
    asyncio.run(main())
