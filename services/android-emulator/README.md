# android-emulator service — rooted, KVM-accelerated Tier-1 target

A containerized Android emulator for reverse-engineering apps you control. It is the reliable
way to instrument hardened titles that block instrumentation on a non-rooted physical device:
the emulator is **rooted**, so you can push frida-server, read `/data/data`, and carve
Lua/config from RAM.

## Why this exists

Some titles ship client-side integrity checks that detect an active instrumentation runtime
on a non-rooted device and exit before anything useful loads. A rooted device under your own
control sidesteps that, and this emulator is a rooted device you fully control, as a
container service. Use it only on apps you have the right to analyze.

## The /dev/kvm unlock (important)

Container Android emulators need `/dev/kvm`. Under Docker Desktop's WSL2 backend it is not
exposed by default, but the WSL2 kernel ships the kvm modules and nested virtualization is
already enabled on this AMD host. Loading the module creates `/dev/kvm` — **no custom kernel,
no restart**:

```
wsl -e sh -c "modprobe kvm_amd"        # or the kvm-loader container below
docker run --rm --device /dev/kvm alpine ls -l /dev/kvm   # verify
```

The `kvm-loader` service in the compose file does this automatically (privileged, mounts the
VM's `/lib/modules`). It is a one-shot the emulator `depends_on`.

## Capabilities verified

- Boots Android 14 (API 34) under KVM in ~15s.
- ABI list `x86_64,arm64-v8a` → runs an arm64-only title via arm64 translation.
- `adb root` works (uid 0), so: read `/data/data`, push frida-server, `pm grant` all perms.
- Runs an arm64 Unity title through its launch-time integrity checks to the engine's
  MainActivity on a device you control.

## Known limitation

Heavy Unity IL2CPP titles under software GPU + arm64 translation can crash the emulator during
engine init (no GPU passthrough under WSL2 for `-gpu host`). Mitigations: more RAM/cores (set
in the compose), retry, or carve during the Unity-init window before the render load peaks.

## Use

```
docker compose -f docker-compose.yml up -d
adb connect localhost:5555 && adb root
# then drive the crack from the worker / pipeline tier1 (root path)
```
