#!/usr/bin/env python3
"""tier1_lua - GENERIC runtime Lua capture + decompile (Tier 1, needs a device).

Engine-agnostic: spawns any Lua-scripted game with the standard-loader Frida hook
(frida_lua_dump.js), collects every Lua chunk the app decrypts and loads at runtime,
then decompiles each with unluac. Not tied to any one title or genre.

Prerequisites (all device-side, verified here before running):
  - A device reachable over ADB (USB into the host, via the host adb-server bridge).
  - frida-server running on the device (matching arch; pushed by the caller or here).
  - The target app installed.

Usage: python tier1_lua.py <package> <out_dir> [seconds]
Output: <out_dir>/dynamic/lua/{raw/*.luac, decompiled/*.lua, _chunks.json}
"""
import sys, os, json, time, hashlib, subprocess

def main():
    if len(sys.argv) < 3:
        print("usage: tier1_lua.py <package> <out_dir> [seconds]"); raise SystemExit(2)
    pkg, out = sys.argv[1], sys.argv[2]
    seconds = int(sys.argv[3]) if len(sys.argv) > 3 else int(os.environ.get("TIER1_SECONDS", "60"))
    rawdir = os.path.join(out, "dynamic", "lua", "raw")
    decdir = os.path.join(out, "dynamic", "lua", "decompiled")
    os.makedirs(rawdir, exist_ok=True); os.makedirs(decdir, exist_ok=True)

    try:
        import frida
    except ImportError:
        print("frida not available (worker image only)"); raise SystemExit(3)

    device = frida.get_usb_device(timeout=15)  # reaches the host adb-server bridge
    print(f"device: {device}")
    pid = device.spawn([pkg])
    session = device.attach(pid)
    here = os.path.dirname(os.path.abspath(__file__))
    script = session.create_script(open(os.path.join(here, "frida_lua_dump.js")).read())

    seen = {}
    def on_message(message, data):
        if message.get("type") == "error":
            print("[frida-error]", message.get("description")); return
        p = message.get("payload", {})
        t = p.get("t")
        if t == "lua" and data:
            h = hashlib.sha1(data).hexdigest()[:16]
            if h in seen: return
            seen[h] = {"name": p.get("name", ""), "sym": p.get("sym"), "size": p.get("size")}
            open(os.path.join(rawdir, f"{h}.luac"), "wb").write(data)
        elif t in ("hooked", "ready", "err"):
            print("[frida]", p)

    script.on("message", on_message)
    script.load()
    device.resume(pid)
    print(f"capturing for {seconds}s while the app boots and loads its Lua...")
    time.sleep(seconds)
    try: session.detach()
    except Exception: pass

    json.dump(seen, open(os.path.join(rawdir, "_chunks.json"), "w"), indent=1)
    print(f"captured {len(seen)} unique Lua chunks -> {rawdir}")

    # decompile with unluac (standard Lua 5.x bytecode; the captured buffer is post-decrypt)
    unluac = os.environ.get("UNLUAC", "/tools/unluac.jar")
    ok = 0
    if os.path.exists(unluac):
        for f in sorted(os.listdir(rawdir)):
            if not f.endswith(".luac"): continue
            dst = os.path.join(decdir, f[:-5] + ".lua")
            try:
                r = subprocess.run(["java", "-jar", unluac, os.path.join(rawdir, f)],
                                   capture_output=True, timeout=90)
                if r.returncode == 0 and r.stdout:
                    open(dst, "wb").write(r.stdout); ok += 1
            except Exception:
                pass
        print(f"decompiled {ok}/{len(seen)} -> {decdir}")
    else:
        print(f"unluac not found at {unluac}; raw chunks kept for offline decompile")

if __name__ == "__main__":
    main()
