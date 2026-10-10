#!/usr/bin/env python3
"""tier1 - robust, device-adaptive runtime cracking. Pulls ALL logic from RAM.

Handles every device case and picks the strongest available injection:
  - ROOTED device        -> push+run frida-server, spawn the app, attach.
  - NON-ROOT device      -> attach to a Frida GADGET that patch_apk.py injected
                            (repack+resign); if that is blocked by anti-tamper, report it.
  - Already-instrumented -> attach by name.

Once attached it loads BOTH scripts:
  - frida_lua_dump.js  : captures Lua at the load boundary (exact bytecode).
  - frida_mem_carve.js : sweeps live memory for Lua chunks + JSON/config blobs
                         (everything the app decrypted and left resident in RAM).
Then decompiles captured Lua with unluac. Engine-agnostic; works for any Lua game,
and the memory sweep captures config/economy for non-Lua targets too.

Usage: python tier1.py <package> <out_dir> [seconds]
Out:   <out_dir>/dynamic/{lua/raw, lua/decompiled, mem/json, mem/lua}, _chunks.json
"""
import sys, os, json, time, hashlib, subprocess

def sh(*a):
    return subprocess.run(a, capture_output=True, text=True, timeout=60)

def is_rooted():
    r = sh("adb", "shell", "su", "-c", "id")
    return "uid=0" in (r.stdout + r.stderr)

def ensure_frida_server(arch_hint="arm64"):
    """Rooted path: push a matching frida-server and start it (best-effort)."""
    # caller provides frida-server binary at $FRIDA_SERVER; push + run as root
    fs = os.environ.get("FRIDA_SERVER")
    if not fs or not os.path.exists(fs):
        print("no FRIDA_SERVER binary provided; assuming one already runs"); return
    sh("adb", "push", fs, "/data/local/tmp/frida-server")
    sh("adb", "shell", "su", "-c", "chmod 755 /data/local/tmp/frida-server")
    subprocess.Popen(["adb", "shell", "su", "-c", "/data/local/tmp/frida-server &"])
    time.sleep(3)

def main():
    if len(sys.argv) < 3:
        print("usage: tier1.py <package> <out_dir> [seconds]"); raise SystemExit(2)
    pkg, out = sys.argv[1], sys.argv[2]
    seconds = int(sys.argv[3]) if len(sys.argv) > 3 else int(os.environ.get("TIER1_SECONDS", "90"))
    here = os.path.dirname(os.path.abspath(__file__))
    dirs = {k: os.path.join(out, "dynamic", *p) for k, p in {
        "lua_raw": ("lua", "raw"), "lua_dec": ("lua", "decompiled"),
        "mem_json": ("mem", "json"), "mem_lua": ("mem", "lua")}.items()}
    for d in dirs.values(): os.makedirs(d, exist_ok=True)

    try:
        import frida
    except ImportError:
        print("frida not available"); raise SystemExit(3)

    rooted = is_rooted()
    print(f"device rooted: {rooted}")
    device = frida.get_usb_device(timeout=15)

    session = None
    if rooted:
        ensure_frida_server()
        pid = device.spawn([pkg]); session = device.attach(pid); resumed = pid
    else:
        # non-root: the app must already carry a Frida gadget (patch_apk.py).
        # Try to attach to the gadget; if the app is not patched this raises.
        print("non-root: attaching to Frida gadget (app must be gadget-patched)")
        for name in ("Gadget", pkg):
            try:
                session = device.attach(name); resumed = None; break
            except Exception as e:
                last = e
        if session is None:
            print(f"could not attach to a gadget ({last}). "
                  f"Run patch_apk.py first, or use a rooted device."); raise SystemExit(4)

    seen = {}
    def write(bucket, data, meta):
        h = hashlib.sha1(data).hexdigest()[:16]
        if h in seen: return
        seen[h] = meta
        ext = ".json" if bucket == "mem_json" else ".luac"
        open(os.path.join(dirs[bucket], f"{h}{ext}"), "wb").write(data)

    def on_message(message, data):
        if message.get("type") == "error":
            print("[frida-error]", message.get("description")); return
        p = message.get("payload", {}); t = p.get("t")
        if t == "lua" and data: write("lua_raw", data, {"src": "load", **p})
        elif t == "mem_lua" and data: write("mem_lua", data, {"src": "mem", **p})
        elif t == "mem_json" and data: write("mem_json", data, {"src": "mem", **p})
        elif t in ("hooked", "ready", "err", "mem_done"): print("[frida]", p)

    combined = (open(os.path.join(here, "frida_lua_dump.js")).read() + "\n" +
                open(os.path.join(here, "frida_mem_carve.js")).read())
    script = session.create_script(combined)
    script.on("message", on_message)
    script.load()
    if rooted: device.resume(resumed)
    print(f"capturing for {seconds}s (load hooks + RAM sweep)...")
    time.sleep(seconds)
    try: script.post({"type": "carve", "opts": {"json": True}}); time.sleep(8)
    except Exception: pass
    try: session.detach()
    except Exception: pass

    json.dump(seen, open(os.path.join(out, "dynamic", "_chunks.json"), "w"), indent=1)
    total = len(seen)
    print(f"captured {total} unique chunks (load + memory)")

    # decompile every captured Lua chunk with unluac
    unluac = os.environ.get("UNLUAC", "/tools/unluac.jar")
    ok = 0
    if os.path.exists(unluac):
        for src in (dirs["lua_raw"], dirs["mem_lua"]):
            for f in sorted(os.listdir(src)):
                if not f.endswith(".luac"): continue
                try:
                    r = subprocess.run(["java", "-jar", unluac, os.path.join(src, f)],
                                       capture_output=True, timeout=90)
                    if r.returncode == 0 and r.stdout:
                        open(os.path.join(dirs["lua_dec"], f[:-5] + ".lua"), "wb").write(r.stdout); ok += 1
                except Exception: pass
        print(f"decompiled {ok} Lua chunks -> {dirs['lua_dec']}")
    else:
        print(f"unluac missing at {unluac}; raw chunks kept for offline decompile")

if __name__ == "__main__":
    main()
