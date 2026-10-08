"""Portable HTML, SVG and PNG from the same north-up planning scene."""
from __future__ import annotations

import html
import json
import math
import os
import uuid
from pathlib import Path

from .development_planner import grid_bounds, validate_snapshot


COLORS = {'terrain':'#263b42', 'obstacles':'#80919d', 'towns':'#ffce78', 'industries':'#db9fea',
          'reserved':'#f2b45b', 'current':'#6ed5b2', 'routes':'#79c7ff'}


def report_bounds(plan):
    full = grid_bounds(plan['snapshot']['grid'])
    if plan['scope'] == 'global':
        return full
    points = []
    for site in plan.get('sites', []):
        points.extend([site['reserved']['min'], site['reserved']['max']])
    for route in plan.get('routes', []):
        points.extend(route.get('path', []))
        points.extend(route.get('endpoints', []))
    if not points:
        return full
    result = {'min': {}, 'max': {}}
    for axis in ('x','y'):
        lo, hi = min(p[axis] for p in points), max(p[axis] for p in points)
        margin = max(50, (hi-lo)*.15)
        result['min'][axis] = max(full['min'][axis], lo-margin)
        result['max'][axis] = min(full['max'][axis], hi+margin)
        if result['max'][axis] <= result['min'][axis]:
            return full
    return result


def export_report(plan, output_dir, width=1600, height=1100):
    from PIL import Image, ImageDraw, ImageFont
    if not 800 <= width <= 4096 or not 600 <= height <= 4096:
        raise ValueError('image size must be 800..4096 by 600..4096')
    s = validate_snapshot(plan['snapshot'])
    bounds = report_bounds(plan)
    dx, dy = bounds['max']['x']-bounds['min']['x'], bounds['max']['y']-bounds['min']['y']
    scale = min((width-120)/dx, (height-190)/dy)
    ox, oy = (width-dx*scale)/2, 100+(height-190-dy*scale)/2
    def project(p):
        return ox+(p['x']-bounds['min']['x'])*scale, oy+(bounds['max']['y']-p['y'])*scale
    image = Image.new('RGBA', (width,height), (0,0,0,0))
    draw = ImageDraw.Draw(image)
    font_paths = [os.environ.get('TF3_PLANNING_FONT', ''), 'C:/Windows/Fonts/msyh.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    font_path = next((p for p in font_paths if p and Path(p).is_file()), None)
    font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default(size=18)
    small = ImageFont.truetype(font_path, 13) if font_path else ImageFont.load_default(size=13)
    warnings = [] if font_path and ('msyh' in font_path.lower() or 'cjk' in font_path.lower()) else ['PNG font may not support Chinese; set TF3_PLANNING_FONT to a CJK font.']
    layers = {k: [] for k in COLORS}
    header = []
    def text(label, x, y, color='#e4edf2', layer=None, tiny=False):
        label = str(label)
        draw.text((x,y), label, fill=color, font=small if tiny else font)
        target = layers[layer] if layer else header
        target.append(f'<text x="{x:.2f}" y="{y+16:.2f}" fill="{color}" font-size="{13 if tiny else 18}">{html.escape(label)}</text>')
    def rect(b, fill, layer, outline=None):
        x,y = project(dict(x=b['min']['x'],y=b['max']['y']))
        x2,y2 = project(dict(x=b['max']['x'],y=b['min']['y']))
        # Clamp off-survey rectangles to keep outside sites from obscuring the report header.
        x,x2=max(ox,x),min(ox+dx*scale,x2);y,y2=max(oy,y),min(oy+dy*scale,y2)
        if x2<x or y2<y:return
        draw.rectangle((x,y,x2,y2), fill=fill, outline=outline, width=2)
        layers[layer].append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{x2-x:.2f}" height="{y2-y:.2f}" fill="{fill or "none"}" stroke="{outline or "none"}" stroke-width="2"/>')
    text(plan['title'], 35, 22)
    text('N ↑  |  世界坐标：米  |  规划示意 · 未通过原生施工校验', 35, 54, tiny=True)
    g=s['grid']; stride=max(1,math.ceil(max(g['nx'],g['ny'])/100))
    hmin,hmax=min(g['heights']),max(g['heights'])
    for j in range(0,g['ny']-1,stride):
        for i in range(0,g['nx']-1,stride):
            index=j*g['nx']+i; h=g['heights'][index]
            t=(h-hmin)/max(1,hmax-hmin)
            color='#295b79' if g['water'][index] else '#%02x%02x%02x' % (int(38+45*t),int(64+50*t),int(55+40*t))
            rect(dict(min=dict(x=g['x']+i*g['spacing'],y=g['y']+j*g['spacing']),
                      max=dict(x=g['x']+min(i+stride,g['nx']-1)*g['spacing'],y=g['y']+min(j+stride,g['ny']-1)*g['spacing'])),color,'terrain')
    for o in s.get('obstacles',[]):rect(o, COLORS['obstacles'], 'obstacles')
    for site in plan.get('sites',[]):
        rect(site['reserved'],None,'reserved',COLORS['reserved'])
        rect(site['current'],None,'current',COLORS['current'])
        x,y=project(site['current']['min']);text(site['name'],x,y,COLORS['current'],'current',True)
    for r in plan.get('routes',[]):
        points=[project(p) for p in r['path']]
        if len(points)<2:continue
        draw.line(points,fill=COLORS['routes'],width=3)
        coords=' '.join(f'{x:.2f},{y:.2f}' for x,y in points)
        layers['routes'].append(f'<polyline points="{coords}" fill="none" stroke="{COLORS["routes"]}" stroke-width="3" stroke-dasharray="8 5"><title>{html.escape(r["name"])}</title></polyline>')
    occupied_labels=[]
    for key in ('towns','industries'):
        for p in s.get('map',{}).get(key,[]):
            pos=p.get('position')
            if not pos or not (bounds['min']['x']<=pos['x']<=bounds['max']['x'] and bounds['min']['y']<=pos['y']<=bounds['max']['y']):continue
            x,y=project(pos);color=COLORS[key]
            draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
            full_label=str(p.get('name',p.get('fileName',p.get('id'))))
            label=str(p.get('name',Path(full_label).stem))
            if len(label)>26:label=label[:23]+'…'
            layers[key].append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="{color}"><title>{html.escape(full_label)} · {p.get("id", "")}</title></circle>')
            label_width=draw.textlength(label,font=small)
            tx=min(width-label_width-20,x+7)
            ty=y-16
            for shift in (0,18,-18,36,-36):
                test=(tx,ty+shift,tx+label_width,ty+shift+16)
                if not any(test[0]<r[2] and test[2]>r[0] and test[1]<r[3] and test[3]>r[1] for r in occupied_labels):
                    ty+=shift;occupied_labels.append(test);break
            text(label,tx,ty,color,key,True)
    labels={'terrain':'地形 / 水域','obstacles':'既有设施包围盒','towns':'城镇','industries':'产业','reserved':'升级预留','current':'当前占地','routes':'候选联系 / 走廊'}
    x=35
    for key,label in labels.items():
        text(label,x,height-68,COLORS[key] if key!='terrain' else '#9ccaa7',tiny=True);x+=max(130,len(label)*14)
    text(f"x: {bounds['min']['x']:g} … {bounds['max']['x']:g}    y: {bounds['min']['y']:g} … {bounds['max']['y']:g}    地形采样 {g['spacing']:g} m",35,height-35,tiny=True)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif"><rect width="{width}" height="{height}" fill="#101e28"/>'+''.join(header)+''.join(f'<g data-layer="{k}">{"".join(v)}</g>' for k,v in layers.items())+'</svg>'
    summary={k:v for k,v in plan.items() if k!='snapshot'}
    def table(rows, columns):
        if not rows:return '<p>未提供；需要进一步调查。</p>'
        return '<table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for _,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(row.get(k,'待核实')))+'</td>' for k,_ in columns)+'</tr>' for row in rows)+'</tbody></table>'
    checks=' '.join(f'<label><input type="checkbox" checked data-toggle="{k}">{v}</label>' for k,v in labels.items())
    content=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(plan['title'])}</title>
<style>body{{margin:0;background:#101e28;color:#e4edf2;font:15px system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}h1{{font-size:26px}}section{{background:#192c38;padding:20px;margin:18px 0;border-radius:12px}}#map{{overflow:auto;max-height:80vh}}svg{{width:100%;display:block}}label{{display:inline-block;margin:8px}}button{{padding:8px;margin:6px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #39505d}}pre{{white-space:pre-wrap;word-break:break-word}}.muted{{color:#b4c5ce}}</style>
<main><h1>{html.escape(plan['title'])}</h1><p class="muted">只读规划 · {html.escape(plan['createdAt'])} · 不构成建造授权</p><section>{checks}<br><button id="in">放大</button><button id="out">缩小</button><button id="reset">复位</button><div id="map">{svg}</div></section>
<section><h2>分期行动与验收条件</h2>{table(plan['phases'], [('name','阶段'),('actions','行动'),('gate','进入下一阶段前')])}</section>
<section><h2>供给、运输与仓储</h2>{table(plan.get('supply',[]), [('name','供应链'),('time_unit','时间单位'),('evidence','依据'),('effectiveDelivery','有效交付上限'),('unmetDemand','需求缺口'),('bottlenecks','限制环节'),('bufferTarget','建议缓冲'),('storageGap','库容缺口')])}</section>
<section><h2>设施与升级预留</h2>{table(plan.get('sites',[]), [('name','设施'),('basis','尺寸依据'),('status','状态'),('conflicts','既有冲突'),('siteConflicts','预留区冲突')])}</section>
<section><h2>路线候选</h2>{table(plan.get('routes',[]), [('name','路线'),('mode','类型'),('status','状态'),('length','长度 m'),('warning','限制')])}</section>
<section><h2>待核实事项</h2><ul>{''.join('<li>'+html.escape(w)+'</li>' for w in plan['warnings']+warnings)}</ul></section>
<details><summary>完整规划参数（不含地图采样）</summary><pre>{html.escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details></main>
<script>let zoom=100;const svg=document.querySelector('svg');document.querySelectorAll('[data-toggle]').forEach(e=>e.onchange=()=>document.querySelector('[data-layer="'+e.dataset.toggle+'"]').style.display=e.checked?'':'none');function scale(n){{zoom=Math.max(50,Math.min(500,n));svg.style.width=zoom+'%';}}document.querySelector('#in').onclick=()=>scale(zoom+25);document.querySelector('#out').onclick=()=>scale(zoom-25);document.querySelector('#reset').onclick=()=>scale(100);</script></html>'''
    folder=Path(output_dir).expanduser().resolve()/('report-'+uuid.uuid4().hex[:12])
    folder.mkdir(parents=True,exist_ok=False)
    # Unique directories keep previous reports intact; manifest is returned only after all writes succeed.
    (folder/'plan.svg').write_text(svg,encoding='utf-8')
    report_image = Image.new('RGBA', image.size, '#101e28')
    report_image.alpha_composite(image)
    report_image.convert('RGB').save(folder/'plan.png')
    # Card title is HTML; omit report captions, legend and sampling notes from its image.
    card_image = image.crop((0, 90, width, height-90))
    # The report centres the map on a wide canvas. Trim that transparent
    # letterboxing before the card applies its initial cover scale.
    visible_bounds = card_image.getchannel('A').getbbox()
    if visible_bounds:
        card_image = card_image.crop(visible_bounds)
    card_image.save(folder/'card.png')
    (folder/'plan.html').write_text(content,encoding='utf-8')
    (folder/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return dict(files={ext:str(folder/f'plan.{ext}') for ext in ('html','png','svg','json')}, warnings=warnings, width=width,height=height,
                cardImage=str(folder/'card.png'), cardWidth=card_image.width, cardHeight=card_image.height)
