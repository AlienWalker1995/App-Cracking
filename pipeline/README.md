# pipeline/ - engine-agnostic static extraction (Tier 0)

The generalized, package-parameterized core of the app-cracker service. Nothing here is
target-specific; per-target keys and decoders belong in `../targets/<package>/`.

## Entry point

```
python crack.py acquire <package> --out <dir>/_input   # fetch FULL split set (XAPK)
python crack.py extract <base.apk> --out <dir>         # run all static stages + manifest
```

## Stages

| Stage | What it does | Output |
|---|---|---|
| `acquire` | Fetch the XAPK (base + arch + dpi splits) so native libs are present | `_input/*.apk` |
| `engine_detect` | Unity/IL2CPP vs Mono vs Flutter vs RN; Unity version; Lua (tolua/xlua) | `engine.json` |
| `il2cpp_strings` | Extract the C# string-literal pool from `global-metadata.dat` | `il2cpp/*.txt` |
| `endpoint_scan` | URLs/hosts from DEX + JSON assets | `endpoints.csv` |
| `rip_textassets` | TextAssets from every AssetBundle, classified json/lua/luac/txt | `textassets/**` |
| `stages/rip_assets.py` | Textures, sprites, meshes (OBJ), audio, fonts | `assets_full/**` |

## Status

Validated on the host (Python 3 + `UnityPy==1.25.3`) against a reference Unity IL2CPP
title (2022.3.x): engine/version detection, thousands of config JSON, plus
textures/sprites/meshes/audio.

TODO (need the pinned worker image in `../worker/`): jadx decompile, Il2CppDumper
(needs dotnet), AXML/manifest decode, and the Tier-1 dynamic stages (Frida, mitmproxy,
device DB pull). See the design spec under `../docs/superpowers/specs/`.
