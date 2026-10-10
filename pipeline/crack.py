#!/usr/bin/env python3
"""crack - engine-agnostic Android app static-extraction CLI.

This is the Tier-0 (static, no device) core of the app-cracker pipeline. It takes
an APK (or acquires one by package name) and produces a structured output bundle:
engine detection, TextAsset/JSON rip, deep asset rip (textures/sprites/meshes/audio),
IL2CPP string-literal pool, network endpoint scan, and a machine-readable manifest.

Nothing here is target-specific: pass any APK. Per-target keys/decoders live in
targets/<package>/ and are applied by the pipeline when present (not yet wired here).

Subcommands
  acquire  <package>  --out DIR     Fetch the full split set (XAPK) so native libs are present.
  extract  <apk>      --out DIR     Run every static stage and write the manifest.

Deeper stages that need the pinned worker image (jadx decompile, Il2CppDumper with
dotnet, AXML decode) and Tier-1 dynamic stages (Frida, mitmproxy, device DB pull)
are documented in the design spec and are TODO in this scaffold.
"""
import argparse, io, json, os, re, subprocess, sys, zipfile, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------- acquire
def acquire(package, out):
    """Fetch the FULL split set as an XAPK so libil2cpp.so / libunity.so are present.

    A base-only APK omits the per-architecture native libraries, which blocks the
    IL2CPP dump. This resolves that by pulling the XAPK (base + arch + dpi splits).
    """
    os.makedirs(out, exist_ok=True)
    xapk = os.path.join(out, f"{package}.xapk")
    url = f"https://d.apkpure.com/b/XAPK/{package}?version=latest"
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    subprocess.run(["curl", "-fsSL", "-A", ua, "-o", xapk, url], check=True)
    z = zipfile.ZipFile(xapk)
    apks = [n for n in z.namelist() if n.endswith(".apk")]
    for n in apks:
        z.extract(n, out)
    base = next((os.path.join(out, n) for n in apks if "config." not in n), None)
    if not base:
        raise SystemExit("no base apk inside xapk")
    print(json.dumps({"xapk": xapk, "apks": apks, "base": base}, indent=1))
    return base


# ----------------------------------------------------------------------------- helpers
def _zip(apk):
    return zipfile.ZipFile(apk)


def _ascii_strings(data, minlen=4):
    return re.findall(rb'[\x20-\x7e]{%d,}' % minlen, data)


# ----------------------------------------------------------------------------- engine
def engine_detect(apk, out):
    z = _zip(apk)
    names = z.namelist()
    libs = sorted({re.sub(r'lib/[^/]+/', '', n) for n in names if n.startswith('lib/')})
    has = lambda frag: any(frag in n for n in names)
    engine = "unknown"
    if has('bin/Data/Managed/Metadata/global-metadata.dat') or any('libil2cpp' in l for l in libs):
        engine = "unity-il2cpp"
    elif has('assets/bin/Data/Managed/'):
        engine = "unity-mono"
    elif any('libflutter' in l for l in libs):
        engine = "flutter"
    elif any('libreactnativejni' in l for l in libs):
        engine = "react-native"
    elif has('assets/www/'):
        engine = "cordova"
    lua = any(x in l for l in libs for x in ('libtolua', 'libxlua', 'liblua'))
    unity_version = None
    gm = 'assets/bin/Data/globalgamemanagers'
    if gm in names:
        m = re.search(rb'(\d+\.\d+\.\d+[a-z]\d+)', z.read(gm)[:200])
        if m:
            unity_version = m.group(1).decode()
    info = {"engine": engine, "unity_version": unity_version, "uses_lua": lua,
            "abis": sorted({re.sub(r'lib/([^/]+)/.*', r'\1', n) for n in names if n.startswith('lib/')}),
            "native_libs": libs, "dex_count": len([n for n in names if re.match(r'classes\d*\.dex$', n)])}
    json.dump(info, open(os.path.join(out, 'engine.json'), 'w'), indent=1)
    print(json.dumps({k: info[k] for k in ('engine', 'unity_version', 'uses_lua', 'dex_count')}, indent=1))
    return info


# ----------------------------------------------------------------------------- il2cpp strings
def il2cpp_strings(apk, out):
    z = _zip(apk)
    gm = 'assets/bin/Data/Managed/Metadata/global-metadata.dat'
    if gm not in z.namelist():
        print("no global-metadata.dat (not IL2CPP)"); return {}
    d = os.path.join(out, 'il2cpp'); os.makedirs(d, exist_ok=True)
    data = z.read(gm)
    open(os.path.join(d, 'global-metadata.dat'), 'wb').write(data)
    uniq = sorted({s.decode('latin-1') for s in _ascii_strings(data, 4)})
    open(os.path.join(d, 'il2cpp_metadata_strings.txt'), 'w', encoding='utf-8').write('\n'.join(uniq))
    pat = re.compile(r'https?://|\.com|/api|[Cc]onfig|Reward|Order|Item|Econom|Price|Currency|Gem|Coin|Drop|Chest|[Aa][Bb][Tt]est|Remote')
    interesting = [s for s in uniq if pat.search(s)]
    open(os.path.join(d, 'il2cpp_interesting_strings.txt'), 'w', encoding='utf-8').write('\n'.join(interesting))
    res = {"literal_strings": len(uniq), "interesting": len(interesting)}
    print(json.dumps(res, indent=1)); return res


# ----------------------------------------------------------------------------- endpoints
def endpoint_scan(apk, out):
    z = _zip(apk)
    targets = [n for n in z.namelist() if re.match(r'classes\d*\.dex$', n) or n.endswith('.json')]
    url_re = re.compile(rb'https?://[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]+')
    hosts = collections.Counter(); urls = set()
    for n in targets:
        for u in url_re.findall(z.read(n)):
            u = u.decode('latin-1').rstrip('.,")\'')
            urls.add(u)
            hosts[re.sub(r'https?://', '', u).split('/')[0]] += 1
    with open(os.path.join(out, 'endpoints.csv'), 'w', encoding='utf-8') as fp:
        fp.write("host,sample_url\n")
        seen = set()
        for u in sorted(urls):
            h = re.sub(r'https?://', '', u).split('/')[0]
            if h in seen: continue
            seen.add(h); fp.write(f'"{h}","{u}"\n')
    print(json.dumps({"unique_hosts": len(hosts), "urls": len(urls)}, indent=1))
    return {"unique_hosts": len(hosts), "urls": len(urls)}


# ----------------------------------------------------------------------------- textassets
def rip_textassets(apk, out):
    import UnityPy
    UnityPy.config.FALLBACK_UNITY_VERSION = "2022.3.0f1"
    z = _zip(apk)
    members = [n for n in z.namelist()
               if (n.startswith('assets/Bundles/') or n.startswith('assets/bin/Data/')) and not n.endswith('/')]
    counts = collections.Counter(); total = 0
    safe = lambda s: re.sub(r'[^A-Za-z0-9._-]', '_', str(s) or 'unnamed')[:100]
    for i, n in enumerate(members):
        data = z.read(n)
        if data[:7] != b'UnityFS' and 'bin/Data' not in n:
            continue
        try:
            env = UnityPy.load(io.BytesIO(data))
        except Exception:
            continue
        for obj in env.objects:
            if obj.type.name != 'TextAsset':
                continue
            try:
                d0 = obj.read()
                raw = d0.m_Script.encode('utf-8', 'surrogateescape') if isinstance(d0.m_Script, str) else bytes(d0.m_Script)
                name = getattr(d0, 'm_Name', 'asset')
            except Exception:
                continue
            total += 1
            s = raw.lstrip()
            if s[:4] == b'\x1bLua': cls, ext = 'luac', '.luac'
            elif s[:1] in (b'{', b'['): cls, ext = 'json', '.json'
            elif b'function' in raw[:200] or b'local ' in raw[:200]: cls, ext = 'lua', '.lua'
            else:
                pr = sum(1 for b in raw[:512] if 9 <= b <= 126)
                cls, ext = ('txt', '.txt') if raw and pr / max(1, len(raw[:512])) > 0.85 else ('other', '.bin')
            counts[cls] += 1
            dd = os.path.join(out, 'textassets', cls); os.makedirs(dd, exist_ok=True)
            open(os.path.join(dd, f"{safe(name)}_{total}{ext}"), 'wb').write(raw)
    print(json.dumps({"textassets": total, **counts}, indent=1))
    return {"textassets": total, **dict(counts)}


# ----------------------------------------------------------------------------- manifest (androguard)
def manifest_decode(apk, out):
    """Decode the binary AndroidManifest and DEX string pool with androguard."""
    try:
        from loguru import logger; logger.remove()
        from androguard.core.apk import APK
    except Exception as e:
        print("androguard unavailable:", e); return {}
    a = APK(apk)
    ns = '{http://schemas.android.com/apk/res/android}'
    meta = {}
    try:
        for md in a.get_android_manifest_xml().findall('.//meta-data'):
            if md.get(ns + 'name'):
                meta[md.get(ns + 'name')] = md.get(ns + 'value')
    except Exception:
        pass
    info = {"package": a.get_package(), "version_name": a.get_androidversion_name(),
            "version_code": a.get_androidversion_code(), "main_activity": a.get_main_activity(),
            "permissions": sorted(a.get_permissions()), "activities": a.get_activities(),
            "services": a.get_services(), "receivers": a.get_receivers(),
            "providers": a.get_providers(), "meta_data": meta}
    json.dump(info, open(os.path.join(out, 'manifest_analysis.json'), 'w'), indent=1)
    print(json.dumps({"package": info["package"], "version": info["version_name"],
                      "permissions": len(info["permissions"]), "activities": len(info["activities"])}, indent=1))
    return {k: info[k] for k in ("package", "version_name", "permissions")}


# ----------------------------------------------------------------------------- il2cpp dump
def _extract_libil2cpp(apk, dest):
    """Pull libil2cpp.so out of this APK or a sibling architecture split."""
    for cand in [apk] + sorted(__import__('glob').glob(os.path.join(os.path.dirname(apk), 'config.*.apk'))):
        z = zipfile.ZipFile(cand)
        for n in z.namelist():
            if n.endswith('lib/arm64-v8a/libil2cpp.so') or n.endswith('/libil2cpp.so'):
                p = os.path.join(dest, 'libil2cpp.so')
                open(p, 'wb').write(z.read(n)); return p
    return None


def il2cpp_dump(apk, out):
    """C# class/method/field dump via Il2CppDumper (needs dotnet + the tool in the worker)."""
    z = _zip(apk)
    gm = 'assets/bin/Data/Managed/Metadata/global-metadata.dat'
    if gm not in z.namelist():
        print("no global-metadata.dat (not IL2CPP)"); return {}
    d = os.path.join(out, 'il2cpp'); os.makedirs(d, exist_ok=True)
    meta = os.path.join(d, 'global-metadata.dat'); open(meta, 'wb').write(z.read(gm))
    so = _extract_libil2cpp(apk, d)
    if not so:
        print("libil2cpp.so not found - acquire the arch split first"); return {"error": "no libil2cpp.so"}
    dumpdir = os.path.join(d, 'dump'); os.makedirs(dumpdir, exist_ok=True)
    dll = os.environ.get('IL2CPPDUMPER', '/tools/Il2CppDumper/Il2CppDumper.dll')
    try:
        subprocess.run(['dotnet', dll, so, meta, dumpdir], stdin=subprocess.DEVNULL, timeout=1800)
    except FileNotFoundError:
        print("dotnet/Il2CppDumper missing (available in the worker image)"); return {"error": "no dotnet"}
    ok = os.path.exists(os.path.join(dumpdir, 'dump.cs'))
    print("il2cpp dump:", "ok" if ok else "failed")
    return {"dump_cs": ok}


# ----------------------------------------------------------------------------- extract (all)
def extract(apk, out):
    os.makedirs(out, exist_ok=True)
    manifest = {"target_apk": os.path.basename(apk),
                "utc": datetime.datetime.utcnow().isoformat() + "Z",
                "stages": {}}
    manifest["stages"]["engine"] = engine_detect(apk, out)
    manifest["stages"]["manifest"] = manifest_decode(apk, out)
    manifest["stages"]["il2cpp_strings"] = il2cpp_strings(apk, out)
    manifest["stages"]["il2cpp_dump"] = il2cpp_dump(apk, out)
    manifest["stages"]["endpoints"] = endpoint_scan(apk, out)
    manifest["stages"]["textassets"] = rip_textassets(apk, out)
    # deep asset rip is a separate long-running module
    subprocess.run([sys.executable, os.path.join(HERE, 'stages', 'rip_assets.py'),
                    apk, os.path.join(out, 'assets_full'),
                    manifest["stages"]["engine"].get("unity_version") or "2022.3.0f1"])
    cat = os.path.join(out, 'assets_full', '_asset_catalog.json')
    if os.path.exists(cat):
        manifest["stages"]["assets"] = json.load(open(cat))
    json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
    print("\nWROTE", os.path.join(out, 'manifest.json'))


def main():
    ap = argparse.ArgumentParser(prog="crack")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("acquire"); a.add_argument("package"); a.add_argument("--out", required=True)
    e = sub.add_parser("extract"); e.add_argument("apk"); e.add_argument("--out", required=True)
    t = sub.add_parser("tier1")   # device-adaptive runtime crack: RAM carve + decompile
    t.add_argument("package"); t.add_argument("--out", required=True); t.add_argument("--seconds", type=int, default=90)
    p = sub.add_parser("patch")   # non-root: inject a Frida gadget so tier1 can attach
    p.add_argument("base"); p.add_argument("split"); p.add_argument("--out", required=True); p.add_argument("--arch", default="arm64-v8a")
    args = ap.parse_args()
    if args.cmd == "acquire":
        acquire(args.package, args.out)
    elif args.cmd == "extract":
        extract(args.apk, args.out)
    elif args.cmd == "tier1":
        subprocess.run([sys.executable, os.path.join(HERE, "stages", "tier1.py"),
                        args.package, args.out, str(args.seconds)])
    elif args.cmd == "patch":
        subprocess.run([sys.executable, os.path.join(HERE, "stages", "patch_apk.py"),
                        args.base, args.split, args.out, args.arch])


if __name__ == "__main__":
    main()
