# Architecture

App-Cracker is three tiers over one shared output bundle. Each tier runs independently, so you go only as deep as the question needs, and every tier writes into the same `out/<package>/<run>/` directory.

<div align="center">
<img src="assets/architecture.svg" alt="App-Cracker architecture across three tiers" width="900" />
</div>

## Layers

| Layer | Directory | Responsibility |
|---|---|---|
| **Acquire** | `pipeline/crack.py acquire` | Fetch the full split set (XAPK: base + arch + dpi) so native libraries are present. A base-only download omits `libil2cpp.so` and blocks the IL2CPP dump. |
| **Tier 0 — static** | `pipeline/` | Engine and version detection, IL2CPP class/method dump, asset rip with a type catalog, endpoint and manifest scan. No device. |
| **Worker** | `worker/` | A single pinned Docker image holding jadx, Il2CppDumper (.NET), apktool, androguard, UnityPy, frida-tools, and mitmproxy. Hermes drives it per job with `docker run`; the host installs none of it. |
| **Tier 1 — dynamic** | `services/android-emulator/`, `pipeline/stages/` | A rooted KVM emulator (or a device you own) runs the app. Frida hooks the Lua loader, a RAM carve sweeps for bytecode and JSON, the live SQLCipher DB is pulled and decrypted, and mitmproxy captures traffic. |
| **Tier 2 — synthesis** | `_digest/` + the Hermes skill | An LLM reads a small digest (manifest, hosts, curated class list) and writes a sourced economy and "how it works" report. It never reads the raw multi-GB dump. |
| **Operator service** | `hermes-skill/app-cracker/` | The Discord-facing contract: the operator attaches an APK or names a package, Hermes runs the pipeline to completion and returns the report plus the bundle. |

## Data flow

1. `acquire` produces the full APK split set in `_input/`.
2. Tier 0 runs every static stage, each writing its own JSON/CSV plus a composed `manifest.json`.
3. Tier 1, when a device is connected and explicitly requested, adds `dynamic/` (carved Lua, pulled DB, captured flows).
4. The synthesis step reads the bounded `_digest/`, not the raw artifacts, and emits `REPORT.md`.

## Design rules

- **Engine-agnostic core.** `pipeline/` takes any APK. Per-target keys and decoders live in `targets/<package>/`, applied only when present.
- **Evidence over assertion.** Outputs separate observed facts from inferences and name residual unknowns. The digest exists so synthesis claims trace back to a source artifact.
- **Pin, do not float.** The worker toolchain is one pinned image with no rolling tags, so a run reproduces months later.
- **Host stays clean.** Extraction tools live in the worker container, never in Hermes or on the host.
