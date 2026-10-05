"""Validate explicit roadside snap geometry; no native snap success is inferred."""
import math


def validate_road_snaps(template):
    for f in template['facilities']:
        s=f.get('roadSnap')
        if s is None:continue
        expected={'helipad':-25,'helipad2':-25,'warehouse':-18,'road_maintenance':-16}
        if f['role'] not in expected:raise ValueError('Unsupported road snap role')
        for name in ('localPoint','target','roadPoint'):
            p=s.get(name,{})
            if set(p)!={'x','y'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in p.values()):
                raise ValueError('Invalid road snap point')
        if s['localPoint']!={'x':0,'y':expected[f['role']]}:raise ValueError('Unexpected native road snap offset')
        a=math.radians(f['relativeRotation']);q=f['localPosition'];v=s['localPoint']
        actual={'x':q['x']+math.cos(a)*v['x']-math.sin(a)*v['y'],
                'y':q['y']+math.sin(a)*v['x']+math.cos(a)*v['y']}
        if math.dist(tuple(actual.values()),tuple(s['target'][k] for k in ('x','y')))>.001:
            raise ValueError('Facility no longer aligns with road snap target')
        found=False
        for r in template['roads']:
            if r.get('buildPhase')!='frontage':continue
            p,z=r['position0'],r['position1'];dx,dy=z['x']-p['x'],z['y']-p['y'];length=math.hypot(dx,dy)
            if not length:continue
            v=s['roadPoint'];u=((v['x']-p['x'])*dx+(v['y']-p['y'])*dy)/length**2
            on=math.hypot(v['x']-p['x']-u*dx,v['y']-p['y']-u*dy)<.001
            ox,oy=s['target']['x']-v['x'],s['target']['y']-v['y']
            if on and 0<=u<=1 and abs(ox*dx+oy*dy)<.001 and abs(math.hypot(ox,oy)-7)<.001:
                if r['roadTemplate']!='country/country_new_small':raise ValueError('Road snap clearance requires revalidation for this street type')
                found=True
        if not found:raise ValueError('Road snap requires a matching frontage and 7m roadside offset')
        if f['role']=='road_maintenance':
            # Keep the service building beside a through frontage, not beyond a dead end.
            p=s['roadPoint'];directions=[]
            for r in template['roads']:
                if r.get('buildPhase')!='frontage':continue
                a,b=r['position0'],r['position1'];dx,dy=b['x']-a['x'],b['y']-a['y'];length=math.hypot(dx,dy)
                if not length:continue
                u=((p['x']-a['x'])*dx+(p['y']-a['y'])*dy)/length**2
                if abs((p['x']-a['x'])*dy-(p['y']-a['y'])*dx)>.001*length or not -.001<=u<=1.001:continue
                for q in (a,b):
                    x,y=q['x']-p['x'],q['y']-p['y'];d=math.hypot(x,y)
                    if d>1:directions.append((x/d,y/d))
            if not any(a[0]*b[0]+a[1]*b[1]<-.99 for a in directions for b in directions):
                raise ValueError('Road maintenance must sit beside continuing frontage, not its end')
