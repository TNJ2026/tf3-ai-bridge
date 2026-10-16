"""Build a separate repaint package from explicit archive resources and UV placement.

Never executes model Lua, overwrites game files, or claims a world-space decal API.
"""
import io
import json
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image, ImageDraw


RESOURCE = re.compile(r'(["\'])([^"\'\n]+\.(?:mdl|mtl|msh|ani|dds|tga|png|wav|ogg|snd|trf))\1')


def build_repaint(source_archive, model_entry, source_resource, texture_entry,
                  output_dir, mod_id, title, overlays=None, replacement_image=None):
    if not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', mod_id):
        raise ValueError('Use a distinct lowercase mod ID, 3-64 characters')
    if not isinstance(title, str) or not title or len(title) > 100:
        raise ValueError('A title of 1-100 characters is required')
    if '::/' not in source_resource or not source_resource.endswith('.mdl'):
        raise ValueError('A fully qualified source model resource is required')
    namespace, resource = source_resource.split('::/', 1)
    if namespace == mod_id:
        raise ValueError('Repaint must have a separate mod ID')
    output = Path(output_dir).resolve()
    if output.exists():
        raise ValueError('Output must be a new directory; existing mods are never overwritten')
    if not model_entry.endswith('.mdl') or not texture_entry.lower().endswith(('.dds','.tga','.png')):
        raise ValueError('Expected model and albedo texture entries')
    # Caller explicitly identifies the atlas. No guessed vehicle-side/UV mapping.
    with zipfile.ZipFile(source_archive) as archive:
        for entry in (model_entry, texture_entry):
            if entry not in archive.namelist() or archive.getinfo(entry).file_size > 128 * 1024 * 1024:
                raise ValueError('Missing or oversized source resource')
        model = archive.read(model_entry).decode('utf-8')
        original = Image.open(io.BytesIO(archive.read(texture_entry))).convert('RGBA')
        atlas = Image.open(replacement_image).convert('RGBA') if replacement_image else original.copy()
        if atlas.size != original.size or max(atlas.size) > 8192:
            raise ValueError('Replacement must match original atlas dimensions (max 8192)')
        if not overlays and not replacement_image:
            raise ValueError('Provide a replacement atlas or explicit pixel-box overlays')
        for overlay in overlays or []:
            if not isinstance(overlay, dict) or set(overlay) - {'image','text','box','color'}:
                raise ValueError('Overlay fields: image or text, box, optional color')
            box = overlay.get('box')
            if (not isinstance(box, list) or len(box) != 4 or any(type(v) is not int for v in box)
                    or not 0 <= box[0] < box[2] <= atlas.width or not 0 <= box[1] < box[3] <= atlas.height):
                raise ValueError('Overlay box must fit the UV atlas')
            if ('image' in overlay) == ('text' in overlay):
                raise ValueError('Choose image or text for each overlay')
            size = (box[2]-box[0], box[3]-box[1])
            if 'image' in overlay:
                patch = Image.open(overlay['image']).convert('RGBA').resize(size, Image.Resampling.LANCZOS)
            else:
                patch = Image.new('RGBA', size)
                draw = ImageDraw.Draw(patch)
                draw.text((2,2), str(overlay['text']), fill=overlay.get('color', 'white'),
                          font_size=max(8, min(size[1]-4, 96)))
            atlas.alpha_composite(patch, (box[0], box[1]))
        entry_root = posixpath.dirname(model_entry)
        resource_root = posixpath.dirname(resource)
        def qualified(path, base=resource_root):
            if '::/' in path:
                return path
            if path.startswith('/'):
                return namespace + '::' + path
            return namespace + '::/' + posixpath.normpath(posixpath.join(base, path))
        replacements = {}
        materials = {}
        for match in RESOURCE.finditer(model):
            value = match[2]
            if value in replacements or not value.endswith('.mtl') or '::/' in value or value.startswith('/'):
                continue
            name = posixpath.normpath(posixpath.join(entry_root, value))
            if name not in archive.namelist():
                raise ValueError('Source material is outside this archive: ' + name)
            material = archive.read(name).decode('utf-8')
            # Only an albedo sampler may be changed, not a normal/cblend atlas.
            sampler = re.compile(r'(albedo(?:Opacity)?Tex\s*=\s*\{[^{}]*?fileName\s*=\s*)(["\'])([^"\']+)(\2)', re.S)
            hits = [m for m in sampler.finditer(material)
                    if posixpath.normpath(posixpath.join(posixpath.dirname(name), m[3])) == texture_entry]
            if not hits:
                continue
            if len(hits) != 1:
                raise ValueError('Ambiguous albedo sampler')
            target = f'vehicle/repaint/material_{len(materials)}.mtl'
            hit = hits[0]
            material = material[:hit.start(3)] + mod_id + '::/vehicle/repaint/albedo.tga' + material[hit.end(3):]
            material_root = posixpath.normpath(posixpath.join(resource_root, posixpath.dirname(value)))
            material = RESOURCE.sub(lambda m: json.dumps(qualified(m[2], material_root)), material)
            materials[target] = material
            replacements[value] = mod_id + '::/' + target
        if not materials:
            raise ValueError('No model material references the selected albedo atlas')
        model = RESOURCE.sub(lambda m: json.dumps(replacements.get(m[2], qualified(m[2]))), model)
        if len(re.findall(r'function\s+data\s*\(\s*\)', model)) != 1:
            raise ValueError('Only declarative models with one data() function are supported')
        model = re.sub(r'function\s+data\s*\(\s*\)', 'local function originalData()', model, count=1)
        model += '\nfunction data()\n local d=originalData()\n d.metadata.description.name=' + json.dumps(title, ensure_ascii=False) + '\n d.metadata.transportVehicle.groupFileName=' + json.dumps(source_resource) + '\n return d\nend\n'
    # All source validation precedes output creation; never extract ZIP paths.
    output.mkdir(parents=True)
    content = output / 'content'
    folder = content / 'vehicle/repaint'
    folder.mkdir(parents=True)
    (folder / 'repaint.mdl').write_text(model, encoding='utf-8')
    for name, material in materials.items():
        (content / name).write_text(material, encoding='utf-8')
    # TF3 DDS resources use the opposite vertical convention to TGA. Keep
    # atlas coordinates in decoded-source space for overlays and previews,
    # then convert only the exported texture to the TGA convention.
    tga_atlas = atlas.transpose(Image.Transpose.FLIP_TOP_BOTTOM) if texture_entry.lower().endswith('.dds') else atlas
    tga_atlas.save(folder / 'albedo.tga')
    atlas.save(output / 'atlas_preview.png')
    (output / '_metadata').mkdir()
    (output / 'mod.json').write_text(json.dumps(dict(modId=mod_id, revision=1,
        dependencies=[{'mod': {'modId': namespace}}] if namespace else None,
        incompatibilities=None, options=None, params=None,
        preRunScript={'fileName':''}, runScript={'fileName':''}, postRunScript={'fileName':''},
        severityAdd='None', severityRemove='None', cosmetic=True), indent=2), encoding='utf-8')
    (output / '_metadata/modinfo.json').write_text(json.dumps(dict(name=title,
        summary='Custom vehicle repaint', description='Independent repaint; inspect UV placement and generate vehicle UI icons in Model Editor.'), indent=2), encoding='utf-8')
    report = dict(modDirectory=str(output), modelResource=mod_id+'::/vehicle/repaint/repaint.mdl',
                  sourceResource=source_resource, changedMaterials=len(materials),
                  atlasSize=list(atlas.size), installed=False, nativeValidated=False,
                  tgaFlippedFromDDS=texture_entry.lower().endswith('.dds'),
                  requires=['Model Editor UV/LOD visual validation', 'Generate vehicle UI icons',
                            'Install and load mod before listing or switching models'],
                  preview=str(output/'atlas_preview.png'))
    (output / 'build_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
