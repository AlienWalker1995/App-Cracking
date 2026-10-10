// frida_mem_carve.js - pull ALL logic out of a running process's RAM.
//
// Complements the load-time hook (frida_lua_dump.js). Where that catches Lua at the
// exact moment it is handed to the VM, this sweeps live memory for anything the app
// decrypted and left resident: Lua bytecode chunks, JSON/config blobs, and (on request)
// whole readable regions for offline hex/binary carving. Engine-agnostic.
//
// Signatures scanned:
//   - Lua bytecode header  1B 4C 75 61 ("\x1bLua") + version byte (0x51..0x54)
//   - Large printable JSON  '{' ... or '[' ...  (economy/config tables)
// Findings stream to the host runner as messages with the raw bytes as payload.

'use strict';

var LUA_SIG = [0x1b, 0x4c, 0x75, 0x61];           // \x1bLua
var LUA_VERSIONS = [0x51, 0x52, 0x53, 0x54];       // 5.1 .. 5.4
var MAX_CHUNK = 1 << 22;                            // 4MB carve window per Lua hit
var MAX_JSON = 1 << 20;                             // 1MB per JSON blob

function scanRange(range) {
    var base = range.base, size = range.size;
    // Lua bytecode headers
    Memory.scan(base, size, '1b 4c 75 61', {
        onMatch: function (addr) {
            try {
                var ver = addr.add(4).readU8();
                if (LUA_VERSIONS.indexOf(ver) < 0) return;
                // carve a window; the runner trims/validates via unluac
                var end = Math.min(MAX_CHUNK, base.add(size).sub(addr).toInt32());
                if (end <= 8) return;
                send({ t: 'mem_lua', addr: addr.toString(), size: end }, addr.readByteArray(end));
            } catch (e) {}
        },
        onError: function () {}, onComplete: function () {}
    });
}

function scanJson(range) {
    // cheap printable-JSON heuristic: read the region, find {"..."} / [...] runs
    try {
        var bytes = new Uint8Array(range.base.readByteArray(Math.min(range.size, 1 << 24)));
        var i = 0, n = bytes.length;
        while (i < n) {
            var c = bytes[i];
            if (c === 0x7b || c === 0x5b) { // { or [
                var j = i + 1, depth = 1, printable = 0;
                while (j < n && j - i < MAX_JSON && depth > 0) {
                    var d = bytes[j];
                    if (d === 0x7b || d === 0x5b) depth++;
                    else if (d === 0x7d || d === 0x5d) depth--;
                    if (d >= 9 && d < 127) printable++;
                    j++;
                }
                var len = j - i;
                if (depth === 0 && len > 64 && (printable / len) > 0.9) {
                    send({ t: 'mem_json', addr: range.base.add(i).toString(), size: len },
                         range.base.add(i).readByteArray(len));
                    i = j; continue;
                }
            }
            i++;
        }
    } catch (e) {}
}

function sweep(opts) {
    var ranges = Process.enumerateRanges('r--');
    var scanned = 0;
    ranges.forEach(function (r) {
        // skip file-backed images for the JSON pass (configs live in anon/heap); scan all for Lua
        try { scanRange(r); if (opts.json && (!r.file)) scanJson(r); scanned++; } catch (e) {}
    });
    send({ t: 'mem_done', ranges: scanned });
}

recv('carve', function (msg) { sweep(msg.opts || { json: true }); });
// auto-sweep once after the app has booted and loaded/decrypted its content
setTimeout(function () { sweep({ json: true }); }, 12000);
