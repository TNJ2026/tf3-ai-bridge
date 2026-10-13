"""Portable HTML, SVG and PNG from the same north-up planning scene."""
from __future__ import annotations

import html
import json
import math
import os
import uuid
from pathlib import Path

from .development_planner import grid_bounds, validate_snapshot
from .localization import language, translate


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
    lang = language(plan.get("language"))
    def tr_text(zh, en):
        return translate(zh, en, lang)
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
    windows_fonts = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    font_paths = [os.environ.get('TF3_PLANNING_FONT', ''), windows_fonts/'msyh.ttc',
                  '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                  windows_fonts/'segoeui.ttf', windows_fonts/'arial.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                  '/System/Library/Fonts/Supplemental/Arial.ttf']
    warnings, font_path = [], None
    for candidate in font_paths:
        if not candidate:
            continue
        candidate = Path(os.path.expandvars(str(candidate))).expanduser()
        if not candidate.is_file():
            continue
        try:
            font = ImageFont.truetype(str(candidate), 18)
            small = ImageFont.truetype(str(candidate), 13)
        except OSError:
            warnings.append('Could not load font: '+str(candidate))
            continue
        font_path = str(candidate)
        break
    if font_path is None:
        font, small = ImageFont.load_default(size=18), ImageFont.load_default(size=13)
    has_cjk = lang == 'zh-CN' or any('\u3400' <= c <= '\u9fff' for c in json.dumps(plan, ensure_ascii=False))
    if has_cjk and not (font_path and any(v in font_path.lower() for v in ('msyh', 'cjk', 'pingfang', 'simsun'))):
        warnings.append('PNG font may not support Chinese; set TF3_PLANNING_FONT to a CJK font.')
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
    text(tr_text('N ↑  |  世界坐标：米  |  规划示意 · 未通过原生施工校验', 'N ↑  |  World coordinates: meters  |  Concept only; native construction not verified'), 35, 54, tiny=True)
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
    labels={'terrain':tr_text('地形 / 水域', 'Terrain / water'),'obstacles':tr_text('既有设施包围盒', 'Existing bounds'),'towns':tr_text('城镇', 'Towns'),'industries':tr_text('产业', 'Industries'),'reserved':tr_text('升级预留', 'Upgrade space'),'current':tr_text('当前占地', 'Current footprint'),'routes':tr_text('候选联系 / 走廊', 'Candidate routes')}
    x, y = 35, height-78
    for key,label in labels.items():
        label_width = draw.textlength(label, font=small) + 24
        if x + label_width > width-35:
            x, y = 35, y+19
        text(label,x,y,COLORS[key] if key!='terrain' else '#9ccaa7',tiny=True)
        x += label_width
    text(f"x: {bounds['min']['x']:g} … {bounds['max']['x']:g}    y: {bounds['min']['y']:g} … {bounds['max']['y']:g}    {tr_text('地形采样', 'Terrain sampling')} {g['spacing']:g} m",35,height-35,tiny=True)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="Microsoft YaHei,Noto Sans CJK SC,sans-serif"><rect width="{width}" height="{height}" fill="#101e28"/>'+''.join(header)+''.join(f'<g data-layer="{k}">{"".join(v)}</g>' for k,v in layers.items())+'</svg>'
    summary={k:v for k,v in plan.items() if k!='snapshot'}
    def table(rows, columns):
        if not rows:return '<p>'+tr_text('未提供；需要进一步调查。', 'Not supplied; further survey required.')+'</p>'
        return '<table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for _,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(row.get(k,tr_text('待核实', 'Unverified'))))+'</td>' for k,_ in columns)+'</tr>' for row in rows)+'</tbody></table>'
    checks=' '.join(f'<label><input type="checkbox" checked data-toggle="{k}">{v}</label>' for k,v in labels.items())
    content=f'''<!doctype html><html lang="{lang}"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(plan['title'])}</title>
<style>body{{margin:0;background:#101e28;color:#e4edf2;font:15px system-ui,"Microsoft YaHei",sans-serif}}main{{max-width:1500px;margin:auto;padding:24px}}h1{{font-size:26px}}section{{background:#192c38;padding:20px;margin:18px 0;border-radius:12px}}#map{{overflow:auto;max-height:80vh}}svg{{width:100%;display:block}}label{{display:inline-block;margin:8px}}button{{padding:8px;margin:6px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #39505d}}pre{{white-space:pre-wrap;word-break:break-word}}.muted{{color:#b4c5ce}}</style>
<main><h1>{html.escape(plan['title'])}</h1><p class="muted">{tr_text('只读规划', 'Read-only plan')} · {html.escape(plan['createdAt'])} · {tr_text('不构成建造授权', 'Not construction authorization')}</p><section>{checks}<br><button id="in">{tr_text('放大', 'Zoom in')}</button><button id="out">{tr_text('缩小', 'Zoom out')}</button><button id="reset">{tr_text('复位', 'Reset')}</button><div id="map">{svg}</div></section>
<section><h2>{tr_text('分期行动与验收条件', 'Phases and acceptance gates')}</h2>{table(plan['phases'], [('name',tr_text('阶段', 'Phase')),('actions',tr_text('行动', 'Actions')),('gate',tr_text('进入下一阶段前', 'Next-stage gate'))])}</section>
<section><h2>{tr_text('供给、运输与仓储', 'Supply, transport and storage')}</h2>{table(plan.get('supply',[]), [('name',tr_text('供应链', 'Supply chain')),('time_unit',tr_text('时间单位', 'Time unit')),('evidence',tr_text('依据', 'Evidence')),('effectiveDelivery',tr_text('有效交付上限', 'Delivery limit')),('unmetDemand',tr_text('需求缺口', 'Unmet demand')),('bottlenecks',tr_text('限制环节', 'Bottlenecks')),('bufferTarget',tr_text('建议缓冲', 'Buffer target')),('storageGap',tr_text('库容缺口', 'Storage gap'))])}</section>
<section><h2>{tr_text('设施与升级预留', 'Facilities and upgrade space')}</h2>{table(plan.get('sites',[]), [('name',tr_text('设施', 'Facility')),('basis',tr_text('尺寸依据', 'Dimensions basis')),('status',tr_text('状态', 'Status')),('conflicts',tr_text('既有冲突', 'Existing conflicts')),('siteConflicts',tr_text('预留区冲突', 'Reserved-space conflicts'))])}</section>
<section><h2>{tr_text('路线候选', 'Route candidates')}</h2>{table(plan.get('routes',[]), [('name',tr_text('路线', 'Route')),('mode',tr_text('类型', 'Type')),('status',tr_text('状态', 'Status')),('length',tr_text('长度 m', 'Length (m)')),('warning',tr_text('限制', 'Limitations'))])}</section>
<section><h2>{tr_text('待核实事项', 'Unverified items')}</h2><ul>{''.join('<li>'+html.escape(w)+'</li>' for w in plan['warnings']+warnings)}</ul></section>
<details><summary>{tr_text('完整规划参数（不含地图采样）', 'Plan parameters (excluding map samples)')}</summary><pre>{html.escape(json.dumps(summary,ensure_ascii=False,indent=2))}</pre></details></main>
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
    return dict(language=lang, files={ext:str(folder/f'plan.{ext}') for ext in ('html','png','svg','json')}, warnings=warnings, width=width,height=height,
                cardImage=str(folder/'card.png'), cardWidth=card_image.width, cardHeight=card_image.height)
