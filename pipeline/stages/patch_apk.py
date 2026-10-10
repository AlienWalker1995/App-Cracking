#!/usr/bin/env python3
"""patch_apk - make a NON-ROOT device instrumentable by injecting a Frida gadget.

Merges the split APKs into one, injects a Frida gadget, and re-signs, producing an
APK that exposes a Frida server-on-device so tier1.py can attach and pull Lua/logic
from RAM without root. Uses objection (which drives apktool + zipalign + apksigner).

CAVEAT: this repacks and re-signs the app. Titles that enforce a signature/integrity
check (this one ships libsigner + libAntiSpam) may refuse to run the patched build.
When that happens, a rooted/dev device (frida-server, no repack) is the reliable route.

Usage: python patch_apk.py <base.apk> <arch_split.apk> <out_dir> [arch]
Out:   <out_dir>/patched/<pkg>.gadget.apk  (install with: adb install-multiple? no -
       it is a single merged APK: adb install -r <that apk>)
"""
import sys, os, subprocess, glob

def run(*a, **k):
    print("+", " ".join(a)); return subprocess.run(a, **k)

def main():
    if len(sys.argv) < 4:
        print("usage: patch_apk.py <base.apk> <arch_split.apk> <out_dir> [arch]"); raise SystemExit(2)
    base, split, out = sys.argv[1], sys.argv[2], sys.argv[3]
    arch = sys.argv[4] if len(sys.argv) > 4 else "arm64-v8a"
    # optional in-process capture script -> SCRIPT-mode gadget (survives anti-debug that
    # blocks an external Frida session); default here for robustness against anti-tamper apps.
    here = os.path.dirname(os.path.abspath(__file__))
    script = sys.argv[5] if len(sys.argv) > 5 else os.path.join(here, "frida_gadget_script.js")
    patched = os.path.join(out, "patched"); os.makedirs(patched, exist_ok=True)
    merged = os.path.join(patched, "merged.apk")

    # 1) merge split set into one installable APK (APKEditor, pure-java)
    apkeditor = os.environ.get("APKEDITOR", "/tools/APKEditor.jar")
    # APKEditor merges a directory or a set; stage base+split into a dir it can merge
    if os.path.exists(merged) and os.path.getsize(merged) > 1_000_000:
        print(f"reusing existing merged apk: {merged}")
    else:
        stage = os.path.join(patched, "_splits"); os.makedirs(stage, exist_ok=True)
        for f in (base, split):
            dst = os.path.join(stage, os.path.basename(f))
            if os.path.abspath(f) != os.path.abspath(dst):
                open(dst, "wb").write(open(f, "rb").read())
        r = run("java", "-jar", apkeditor, "m", "-i", stage, "-o", merged)
        if r.returncode != 0 or not os.path.exists(merged):
            print("APKEditor merge failed"); raise SystemExit(5)

    # 2) inject the Frida gadget + re-sign (objection drives apktool/zipalign/apksigner).
    obj = ["objection", "patchapk", "--source", merged, "--architecture", arch, "--ignore-nativelibs"]
    if script and os.path.exists(script):
        # SCRIPT-mode gadget: autoloads our capture script in-process, no external session.
        cfg = os.path.join(patched, "gadget.config")
        open(cfg, "w").write('{"interaction":{"type":"script",'
                             '"path":"libfrida-gadget.script.so","on_change":"reload"}}')
        obj += ["--gadget-config", cfg, "--script-source", script]
        print("using SCRIPT-mode gadget with", os.path.basename(script))
    r = run(*obj)
    # objection writes <merged>.objection.apk next to the source
    cand = glob.glob(os.path.join(patched, "*.objection.apk"))
    if r.returncode != 0 or not cand:
        print("objection patchapk failed - anti-tamper or missing build-tools. "
              "Use a rooted device for a no-repack capture."); raise SystemExit(6)
    final = cand[0]
    print("PATCHED:", final)
    print("install with:  adb install -r", final)
    print("then run:      python tier1.py <package> <out_dir>")

if __name__ == "__main__":
    main()
