# worker/ - pinned app-cracker toolchain image

`app-cracker-worker` is the reproducible container that Hermes drives per job. It carries
the heavy tools the pipeline hands off to; the Python + UnityPy Tier-0 stages in
`../pipeline/` run inside it too.

## Build

```
docker build -t app-cracker-worker:0.1.0 -f worker/Dockerfile .
```

(Build context is the repo root so `pipeline/` is copied in.)

## Run (Tier 0, static)

```
docker run --rm \
  -v /path/to/base.apk:/in/app.apk:ro \
  -v /path/to/outdir:/out \
  app-cracker-worker:0.1.0 extract /in/app.apk --out /out
```

## Run (Tier 1, dynamic - needs the host adb bridge)

Start the adb server on the Windows host so the container can reach USB devices, then:

```
docker run --rm \
  -e ADB_SERVER_SOCKET=tcp:host.docker.internal:5037 \
  -v /path/to/outdir:/out \
  app-cracker-worker:0.1.0 <dynamic-subcommand>
```

## Pinned versions

apktool 2.10.0, jadx 1.5.1, platform-tools r35.0.2, UnityPy 1.25.3, frida-tools 13.7.1,
mitmproxy 11.1.3. No rolling tags. Bump deliberately.

## TODO before production

- Il2CppDumper (needs dotnet runtime) wired as a stage pairing `libil2cpp.so` + `global-metadata.dat`.
- frida-server push/attach flow for Tier-1 memory + IO-hook stages.
- AXML/manifest decode via aapt2 for the real permission/component list.
