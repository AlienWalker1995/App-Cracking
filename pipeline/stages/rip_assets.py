#!/usr/bin/env python3
"""Deep Unity asset rip: textures, sprites, meshes, audio, + a type catalog.

Reads AssetBundles straight out of an APK (assets/Bundles/**) and the standard
serialized files (assets/bin/Data/**), exporting every renderable asset UnityPy
can decode. Engine-agnostic: pass the APK path and an output dir.

Usage: python rip_assets.py <base.apk> <out_dir> [fallback_unity_version]
"""
import sys, os, re, io, json, zipfile, collections
import UnityPy

def safe(s):
    return re.sub(r'[^A-Za-z0-9._-]', '_', str(s) or 'unnamed')[:100]

def main():
    apk, out = sys.argv[1], sys.argv[2]
    UnityPy.config.FALLBACK_UNITY_VERSION = sys.argv[3] if len(sys.argv) > 3 else "2022.3.0f1"
    for d in ('textures', 'sprites', 'meshes', 'audio', 'fonts'):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    z = zipfile.ZipFile(apk)
    members = [n for n in z.namelist()
               if (n.startswith('assets/Bundles/') or n.startswith('assets/bin/Data/'))
               and not n.endswith('/')]
    typecount = collections.Counter()
    saved = collections.Counter()
    errs = 0
    uid = 0  # global monotonic id so assets sharing name+path_id never overwrite each other
    for i, n in enumerate(members):
        if i % 500 == 0:
            print(f"  ...{i}/{len(members)} saved={dict(saved)}", flush=True)
        data = z.read(n)
        if data[:7] != b'UnityFS' and b'bin/Data' not in n.encode():
            continue
        try:
            env = UnityPy.load(io.BytesIO(data))
        except Exception:
            errs += 1; continue
        for obj in env.objects:
            t = obj.type.name
            typecount[t] += 1
            uid += 1
            try:
                if t in ('Texture2D', 'Sprite'):
                    d = obj.read()
                    img = d.image
                    if img is None: continue
                    sub = 'sprites' if t == 'Sprite' else 'textures'
                    img.save(os.path.join(out, sub, f"{safe(d.m_Name)}_{uid}.png"))
                    saved[sub] += 1
                elif t == 'Mesh':
                    d = obj.read()
                    obj_str = d.export()  # Wavefront OBJ
                    open(os.path.join(out, 'meshes', f"{safe(d.m_Name)}_{uid}.obj"),
                         'w', encoding='utf-8').write(obj_str)
                    saved['meshes'] += 1
                elif t == 'AudioClip':
                    d = obj.read()
                    for sname, samp in (d.samples or {}).items():
                        open(os.path.join(out, 'audio', f"{safe(sname)}_{uid}.wav"), 'wb').write(samp)
                        saved['audio'] += 1
                elif t == 'Font':
                    d = obj.read()
                    blob = getattr(d, 'm_FontData', None)
                    if blob:
                        open(os.path.join(out, 'fonts', f"{safe(d.m_Name)}_{uid}.ttf"), 'wb').write(bytes(blob))
                        saved['fonts'] += 1
            except Exception:
                errs += 1
    json.dump({'type_catalog': dict(typecount), 'saved': dict(saved), 'errors': errs},
              open(os.path.join(out, '_asset_catalog.json'), 'w'), indent=1)
    print("DONE. saved:", dict(saved), "errors:", errs)
    print("top types:", typecount.most_common(15))

if __name__ == '__main__':
    main()
