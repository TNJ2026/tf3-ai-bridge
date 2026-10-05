import asyncio, json
from pathlib import Path
from tf3_mcp.server import plan_local_development

async def main():
    snapshot_path = 'D:/Develop/game/tf3/exports/plan_20261004/snapshot-0365e4257d3f.json'
    out_dir = 'D:/Develop/game/tf3/exports/plan_20261004'

    # Sited clusters (absolute coordinates for current & reserved)
    sites = [
        {
            'name': '黄冈城市综合枢纽',
            'basis': '五设施综合集合 (直升机场/仓库/货站/客车站/车库)，占地140x120m，扩建预留200x180m',
            'current': {'min': {'x': 1761 - 70, 'y': -743 - 60}, 'max': {'x': 1761 + 70, 'y': -743 + 60}},
            'reserved': {'min': {'x': 1761 - 100, 'y': -743 - 90}, 'max': {'x': 1761 + 100, 'y': -743 + 90}}
        },
        {
            'name': '萍乡城市综合枢纽',
            'basis': '城市综合集合 (含萍乡牧场公路接驳)，占地140x120m，扩建预留200x180m',
            'current': {'min': {'x': -3235 - 70, 'y': 2522 - 60}, 'max': {'x': -3235 + 70, 'y': 2522 + 60}},
            'reserved': {'min': {'x': -3235 - 100, 'y': 2522 - 90}, 'max': {'x': -3235 + 100, 'y': 2522 + 90}}
        },
        {
            'name': '阳泉城市综合枢纽',
            'basis': '城市综合集合 (含阳泉伐木场公路接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': -2446 - 70, 'y': 1012 - 60}, 'max': {'x': -2446 + 70, 'y': 1012 + 60}},
            'reserved': {'min': {'x': -2446 - 100, 'y': 1012 - 90}, 'max': {'x': -2446 + 100, 'y': 1012 + 90}}
        },
        {
            'name': '秦皇岛城市综合枢纽',
            'basis': '城市综合集合 (含农场及锯木厂公路接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': 2540 - 70, 'y': 2043 - 60}, 'max': {'x': 2540 + 70, 'y': 2043 + 60}},
            'reserved': {'min': {'x': 2540 - 100, 'y': 2043 - 90}, 'max': {'x': 2540 + 100, 'y': 2043 + 90}}
        },
        {
            'name': '葫芦岛城市综合枢纽',
            'basis': '城市综合集合 (含黏土坑及砖厂公路接驳)，占地140x120m，预留200x180m',
            'current': {'min': {'x': -1186 - 70, 'y': -2703 - 60}, 'max': {'x': -1186 + 70, 'y': -2703 + 60}},
            'reserved': {'min': {'x': -1186 - 100, 'y': -2703 - 90}, 'max': {'x': -1186 + 100, 'y': -2703 + 90}}
        },
        {
            'name': '葫芦岛农场生产端双坪集合',
            'basis': '生产端集合 (双直升机坪/仓库/货站)，占地100x80m，预留150x120m',
            'current': {'min': {'x': -3528 - 50, 'y': -3988 - 40}, 'max': {'x': -3528 + 50, 'y': -3988 + 40}},
            'reserved': {'min': {'x': -3528 - 75, 'y': -3988 - 60}, 'max': {'x': -3528 + 75, 'y': -3988 + 60}}
        },
        {
            'name': '黄冈炼油厂生产端双坪集合',
            'basis': '炼化生产端集合 (双直升机坪/仓库/货站)，占地100x80m，预留150x120m',
            'current': {'min': {'x': 3504 - 50, 'y': -1032 - 40}, 'max': {'x': 3504 + 50, 'y': -1032 + 40}},
            'reserved': {'min': {'x': 3504 - 75, 'y': -1032 - 60}, 'max': {'x': 3504 + 75, 'y': -1032 + 60}}
        }
    ]

    # Corridors: road feeder connections between industries/towns and clusters
    corridors = [
        {
            'name': '黄冈城市接驳干道',
            'mode': 'road',
            'start': {'x': 1427.7, 'y': -38.3},
            'end': {'x': 1761.0, 'y': -630.0}
        },
        {
            'name': '萍乡城市接驳干道',
            'mode': 'road',
            'start': {'x': -2568.4, 'y': 2917.4},
            'end': {'x': -3110.0, 'y': 2522.0}
        },
        {
            'name': '阳泉城市接驳干道',
            'mode': 'road',
            'start': {'x': -2400.0, 'y': 500.0},
            'end': {'x': -2446.0, 'y': 750.0}
        },
        {
            'name': '秦皇岛城市接驳干道',
            'mode': 'road',
            'start': {'x': 2800.0, 'y': 2600.0},
            'end': {'x': 2540.0, 'y': 2180.0}
        },
        {
            'name': '葫芦岛城市接驳干道',
            'mode': 'road',
            'start': {'x': -550.0, 'y': -2780.0},
            'end': {'x': -950.0, 'y': -2703.0}
        }
    ]

    chains = [
        {
            'name': '黄冈与秦皇岛·燃料供给链',
            'cargo': '燃料',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 433,
            'production': 450,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 40,
            'delay': 0.1,
            'storage': 0
        },
        {
            'name': '黄冈与葫芦岛·肉类食品链',
            'cargo': '肉类',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 251,
            'production': 300,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 30,
            'delay': 0.1,
            'storage': 0
        },
        {
            'name': '阳泉与秦皇岛·生鲜水产链',
            'cargo': '鱼',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 197,
            'production': 250,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 20,
            'delay': 0.1,
            'storage': 0
        },
        {
            'name': '阳泉与葫芦岛·木材建材链',
            'cargo': '木板',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 163,
            'production': 200,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 30,
            'delay': 0.1,
            'storage': 0
        },
        {
            'name': '萍乡·蔬菜直供链',
            'cargo': '蔬菜',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 201,
            'production': 250,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 25,
            'delay': 0.1,
            'storage': 0
        },
        {
            'name': '萍乡·砖块建材链',
            'cargo': '砖块',
            'time_unit': '年',
            'evidence': 'forecast',
            'demand': 136,
            'production': 200,
            'transport': 0,
            'handling': 0,
            'delivery': 0,
            'batch': 30,
            'delay': 0.1,
            'storage': 0
        }
    ]

    res = await plan_local_development(snapshot_path, out_dir, sites=sites, corridors=corridors, supply_chains=chains, title='全域综合枢纽与供给走廊规划')
    data = json.loads(res.content[0].text)
    print('Local plan saved. Path:', data.get('plan_path'))
    print('Sites verified count:', len(data.get('sites', [])))
    print('Corridor routes count:', len(data.get('routes', [])))
    for s in data.get('sites', []):
        print(f"  Site: {s['name']}, status={s.get('status')}")
    for r in data.get('routes', []):
        length_str = f"{r.get('length'):.1f}m" if r.get('length') is not None else "N/A"
        print(f"  Route: {r['name']}, mode={r.get('mode')}, status={r.get('status')}, length={length_str}")

if __name__ == '__main__':
    asyncio.run(main())
