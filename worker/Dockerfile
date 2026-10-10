# app-cracker-worker - pinned Android RE toolchain that Hermes drives per job.
#
# Python-first base (the pipeline is Python + UnityPy + androguard). A JRE is added for
# jadx/apktool; .NET for Il2CppDumper. Versions pinned deliberately (no rolling tags).
#
#   docker run --rm \
#     -v <apk>:/in/app.apk:ro -v <outdir>:/out \
#     [-e ADB_SERVER_SOCKET=tcp:host.docker.internal:5037] \
#     app-cracker-worker:<tag> extract /in/app.apk --out /out

FROM python:3.12-slim-bookworm

ARG APKTOOL_VERSION=2.10.0
ARG JADX_VERSION=1.5.1
ARG PLATFORM_TOOLS=35.0.2
ARG IL2CPPDUMPER_VERSION=6.7.46

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      default-jre-headless curl unzip git sqlcipher sqlite3 file ca-certificates \
      libicu72 \
    && rm -rf /var/lib/apt/lists/*

# --- Python extraction deps (pinned; need Python >= 3.11, hence the 3.12 base) ---
# UnityPy + androguard are imported by the pipeline; frida-tools is a CLI. androguard needs
# cryptography>=46, which conflicts with mitmproxy's pin, so mitmproxy lives in its own venv
# below (it is a Tier-1 CLI run as a subprocess, never imported alongside androguard).
RUN pip install --no-cache-dir \
      "UnityPy==1.25.3" \
      "androguard==4.1.4" \
      "frida-tools==13.7.1"
RUN python -m venv /opt/mitmproxy-venv \
    && /opt/mitmproxy-venv/bin/pip install --no-cache-dir "mitmproxy==11.1.3" \
    && ln -s /opt/mitmproxy-venv/bin/mitmdump /usr/local/bin/mitmdump

# --- .NET runtime + Il2CppDumper (pinned) - the C# class/method dump ---
RUN curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh \
    && bash /tmp/dotnet-install.sh --channel 6.0 --runtime dotnet --install-dir /usr/share/dotnet \
    && ln -s /usr/share/dotnet/dotnet /usr/local/bin/dotnet && rm /tmp/dotnet-install.sh
RUN mkdir -p /tools/Il2CppDumper \
    && curl -fsSL -o /tmp/ilcpp.zip \
      https://github.com/Perfare/Il2CppDumper/releases/download/v${IL2CPPDUMPER_VERSION}/Il2CppDumper-net6-v${IL2CPPDUMPER_VERSION}.zip \
    && unzip -q /tmp/ilcpp.zip -d /tools/Il2CppDumper && rm /tmp/ilcpp.zip
ENV IL2CPPDUMPER=/tools/Il2CppDumper/Il2CppDumper.dll

# --- apktool (pinned) ---
RUN curl -fsSL -o /usr/local/bin/apktool.jar \
      https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VERSION}/apktool_${APKTOOL_VERSION}.jar \
    && printf '#!/bin/sh\nexec java -jar /usr/local/bin/apktool.jar "$@"\n' > /usr/local/bin/apktool \
    && chmod +x /usr/local/bin/apktool

# --- jadx (pinned) ---
RUN curl -fsSL -o /tmp/jadx.zip \
      https://github.com/skylot/jadx/releases/download/v${JADX_VERSION}/jadx-${JADX_VERSION}.zip \
    && unzip -q /tmp/jadx.zip -d /opt/jadx && rm /tmp/jadx.zip \
    && ln -s /opt/jadx/bin/jadx /usr/local/bin/jadx

# --- Android platform-tools (adb, aapt2) (pinned) ---
RUN curl -fsSL -o /tmp/pt.zip \
      https://dl.google.com/android/repository/platform-tools_r${PLATFORM_TOOLS}-linux.zip \
    && unzip -q /tmp/pt.zip -d /opt && rm /tmp/pt.zip \
    && ln -s /opt/platform-tools/adb /usr/local/bin/adb

# --- unluac - decompiles standard Lua 5.x bytecode captured at runtime ---
# unluac is effectively frozen; the SourceForge "latest" is the maintained build.
RUN mkdir -p /tools \
    && curl -fsSL -o /tools/unluac.jar \
      "https://sourceforge.net/projects/unluac/files/latest/download"
ENV UNLUAC=/tools/unluac.jar

# --- Non-root instrumentation toolchain (pinned) - gadget injection + repack/sign ---
# objection injects a Frida gadget and re-signs; needs zipalign+apksigner (build-tools).
ARG APKEDITOR_VERSION=1.4.1
ARG UBERSIGNER_VERSION=1.3.0
ARG BUILDTOOLS_VERSION=34.0.0
RUN pip install --no-cache-dir "objection==1.11.0" "setuptools<81"
RUN curl -fsSL -o /tools/APKEditor.jar \
      https://github.com/REAndroid/APKEditor/releases/download/V${APKEDITOR_VERSION}/APKEditor-${APKEDITOR_VERSION}.jar \
    && curl -fsSL -o /tools/uber-apk-signer.jar \
      https://github.com/patrickfav/uber-apk-signer/releases/download/v${UBERSIGNER_VERSION}/uber-apk-signer-${UBERSIGNER_VERSION}.jar
ENV APKEDITOR=/tools/APKEditor.jar
RUN mkdir -p /opt/android-sdk/cmdline-tools && cd /opt/android-sdk/cmdline-tools \
    && curl -fsSL -o cli.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
    && unzip -q cli.zip && mv cmdline-tools latest && rm cli.zip \
    && yes | /opt/android-sdk/cmdline-tools/latest/bin/sdkmanager --sdk_root=/opt/android-sdk "build-tools;${BUILDTOOLS_VERSION}" >/dev/null \
    && ln -sf /opt/android-sdk/build-tools/${BUILDTOOLS_VERSION}/zipalign /usr/local/bin/zipalign \
    && ln -sf /opt/android-sdk/build-tools/${BUILDTOOLS_VERSION}/apksigner /usr/local/bin/apksigner \
    && ln -sf /opt/android-sdk/build-tools/${BUILDTOOLS_VERSION}/aapt /usr/local/bin/aapt \
    && ln -sf /opt/android-sdk/build-tools/${BUILDTOOLS_VERSION}/aapt2 /usr/local/bin/aapt2

# Tier-1 runtime crack is wired in pipeline/stages/{frida_lua_dump.js, frida_mem_carve.js,
# tier1.py, patch_apk.py} (crack.py `tier1` + `patch` subcommands). Device-adaptive:
#   rooted   -> frida-server, no repack (reliable);
#   non-root -> `patch` injects a gadget (objection) then `tier1` attaches and sweeps RAM.
# frida hooks the standard Lua loaders AND carves Lua/JSON/config out of live memory;
# unluac decompiles. Engine-agnostic. Anti-tamper (libsigner) may block the repacked build;
# a rooted/dev device is the fallback. Validate on first device run.

COPY pipeline /opt/pipeline
WORKDIR /work
ENTRYPOINT ["python3", "/opt/pipeline/crack.py"]
CMD ["--help"]
