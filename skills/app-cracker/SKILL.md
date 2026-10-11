---
name: app-cracker
description: >
  Reverse-engineer an Android app end to end. Use ONLY when the operator explicitly asks
  to analyze/crack/extract an app AND provides an APK (attachment) or a package name/Play
  URL. Extracts assets, binary/memory data, network endpoints, and economy/config; on an
  explicitly requested run with a connected device, also monitors reads/writes and dumps
  runtime memory. Returns a report in Discord plus a full bundle saved to disk.
---

# app-cracker

Operator-driven general Android app reverse-engineering. Validated on reference
Unity/IL2CPP titles with a Lua runtime; works on any APK the operator has the right to
analyze.

## Trigger contract (hard rules)

Act ONLY when BOTH hold:
1. The operator explicitly asks to analyze / crack / extract an app.
2. The operator provides the app: an APK attachment, or a package name / Play URL.

Never run on a bare attachment with no request. Tier 1 (dynamic, on-device) runs ONLY
when the operator explicitly asks for it AND a device is connected. Gated to the operator.

## Nature: long-running and self-provisioning

This is a LONG-RUNNING extraction, not a quick lookup. A full static pass on a large game
takes several minutes (unpack, IL2CPP dump, rip thousands of assets). Run it to completion,
stream progress, and do not abandon it early.

Spin up whatever tools the job needs:
- If the worker image is missing, build it first:
  `docker build -t app-cracker-worker:0.1.0 -f <REPO>/worker/Dockerfile <REPO>`
  The image bundles the pinned toolchain (UnityPy, androguard, .NET + Il2CppDumper, jadx,
  apktool, platform-tools, frida-tools, mitmproxy). Build once; reuse across jobs.
- For Tier 1, start the host adb bridge and push frida-server as needed.
Everything runs in the worker container; do not install extraction tools into Hermes itself.

**Launch the extraction DETACHED, then poll.** It runs for several minutes, longer than a
single tool call may allow, so never run it as one blocking foreground command (that is why a
prior run produced the bundle but skipped the report - the blocking call timed out). Instead:
1. `docker run -d --name crack_<pkg> -v <indir>:/in:ro -v <outdir>:/out app-cracker-worker:0.1.0 extract /in/base.apk --out /out`
2. Poll every ~30s with short calls until `<outdir>/manifest.json` exists AND the container has
   exited (`docker ps -a --filter name=crack_<pkg> --format '{{.Status}}'`).
3. `docker rm crack_<pkg>` and continue to synthesis. Keep each poll call short.

## Where things live

- Tooling + pipeline (source of truth): `<REPO>/` (mirror-mounted into Hermes).
- Output bundles (NOT committed): `<REPO>/out/<package>/<UTC-timestamp>/`.
- Worker image (pinned toolchain): `app-cracker-worker:<tag>` built from `worker/Dockerfile`.
- Entry point: `pipeline/crack.py` (`acquire`, then `extract`). Validated stages: engine
  detect, androguard manifest, IL2CPP string pool, IL2CPP C# dump (Il2CppDumper), endpoint
  scan, TextAsset rip, deep asset rip (textures/sprites/meshes/audio/fonts).

## Flow

1. **Stage the app.** If given an APK, save it under the output dir. If given a package
   name / Play URL, acquire the FULL split set (XAPK), not just the base APK - a base-only
   download omits `libil2cpp.so` and breaks the IL2CPP dump:
   `python <REPO>/pipeline/crack.py acquire <package> --out <outdir>/_input`

2. **Tier 0 - static (always).** Run the static pipeline in the pinned worker:
   `docker run --rm -v <base.apk>:/in/app.apk:ro -v <outdir>:/out app-cracker-worker:<tag> extract /in/app.apk --out /out`
   Produces: `engine.json`, `il2cpp/` (metadata + string pools), `endpoints.csv`,
   `textassets/{json,lua,luac,txt}/`, `assets_full/{textures,sprites,meshes,audio,fonts}/`,
   and `manifest.json`. On the host today the same stages run with Python + UnityPy directly.

3. **Tier 1 - dynamic runtime crack (explicit + device only).** For any Lua-scripted game the
   economy (item and progression definitions, reward/drop tables, costs, timers) is Lua that
   loads only at runtime, so it is captured from the LIVE PROCESS, not from static files. The
   flow is device-adaptive and pulls all logic from RAM; it works for any game format (tolua /
   XLua / vanilla Lua, and the memory sweep captures config/economy even for non-Lua targets):
   - Verify a device (`adb devices`, via `worker/adb-bridge.sh` +
     `ADB_SERVER_SOCKET=tcp:host.docker.internal:5037`). `tier1` auto-detects root.
   - **Rooted device (reliable):** it pushes frida-server and attaches directly - no repack.
   - **Non-root device:** first inject a Frida gadget (repack + re-sign):
     `python crack.py patch <base.apk> <arch_split.apk> --out <outdir>` -> install the patched
     APK -> then `tier1` attaches to the gadget. Anti-tamper (libsigner) may block the repacked
     build; if so, use a rooted/dev device.
   - **Capture + decompile (both cases):**
     `python crack.py tier1 <package> --out <outdir> --seconds 90`
     Loads `frida_lua_dump.js` (hooks the standard Lua loaders `luaL_loadbuffer(x)`, `lua_load`,
     `xluaL_loadbuffer`, `luaL_loadstring` - the game decrypts before calling them, so packed
     Lua comes out plaintext) AND `frida_mem_carve.js` (sweeps live memory for Lua bytecode
     headers `\x1bLua` and JSON/config blobs the app decrypted into RAM). Decompiles every
     captured chunk with unluac into `<outdir>/dynamic/{lua/decompiled, mem/*}`.
   - Also available: mitmproxy on the game's API/CDN for the server-authoritative economy;
     repack-debuggable + `run-as` for on-disk private files; live DB pull + decrypt.
   - Then extract the economy tables (item and progression definitions, reward/drop tables,
     costs, timers) from the decompiled Lua and fold them into the synthesis report.

4. **Tier 2 - synthesis.** Read the decompiled code, configs, IL2CPP strings, and any live
   state, and write `REPORT.md`: architecture, economy and reward tables, config surfaces,
   endpoints, and a plain-language "how it works."

5. **Return.** Post the report summary + the bundle path to Discord. Large artifacts stay
   on disk (Discord caps attachments at 25MB).

## Notes proven on real targets

- Unity IL2CPP economy/config lives in TextAssets inside `assets/Bundles/**` AssetBundles,
  not in `assets/bin/Data`. Rip TextAssets from every bundle.
- Games using `libtolua.so` / `libxlua.so` run Lua; expect Lua bytecode TextAssets (may be
  obfuscated with a non-standard header - keep the per-target decoder in a private
  `targets/<package>/`).
- `Firebase.RemoteConfig` in the IL2CPP strings means the economy is partly server-driven;
  the full picture needs Tier 1 network capture.
- Anti-cheat / emulator-detection libs (`libAntiSpam`, `libemulator_checker`, `libsigner`)
  affect Tier 1; use a physical device.

## Definition of Done (evaluation criteria)

The skill is NOT complete until every item holds. Check them yourself before you claim done;
if the report is missing, you are not done - go write it. The report is YOUR synthesis, not a
template: reason over the extracted material and explain the systems.

1. **Bundle exists.** `manifest.json` plus the stage outputs are present: `engine.json`,
   `il2cpp/dump/dump.cs` (for IL2CPP targets), `textassets/`, `assets_full/`, `endpoints.csv`.
2. **Synthesis report written.** You have written `REPORT.md` at the bundle root that explains
   HOW THE APP WORKS, at the depth of a thorough reverse-engineering writeup. It must cover:
   engine/architecture, backend and endpoints, monetization, and the
   ECONOMY and game mechanics. For each economy system, state what the current extraction
   proves and what still needs Tier 1 (runtime Lua/memory capture). Do not just list counts -
   explain the systems and cite the files/classes you drew from.
   - Large files: `dump.cs` can be 20MB+. Do NOT read it whole. `grep` it for game namespaces
     and class names (e.g. economy/manager/config classes) and read only those spans.
     Sample the config JSON; most are localization, so filter for real config.
3. **Reported back.** You have posted the `REPORT.md` summary and the bundle path to the
   requester.

If the target is Lua-driven (tolua/xlua) and the economy is not in the static bundles, say so
explicitly in the report and mark the economy section as "requires Tier 1" rather than guessing.

## Design

See the repository [`README.md`](../../README.md) and [`docs/architecture.md`](../../docs/architecture.md)
for the tier model and component map.
