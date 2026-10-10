// frida_gadget_script.js - READ-ONLY in-process RAM carver for SCRIPT-mode gadget.
//
// Tuned for anti-tamper titles (libsigner/libAntiSpam) that clean-exit when they detect
// inline hooks. This installs NO Interceptor hooks - it only READS memory (Memory.scan),
// which patches no code, so the integrity check has nothing to trip on (the gadget's mere
// presence is tolerated; only code patches are detected). It sweeps repeatedly so Lua the
// app decrypts into RAM over the boot sequence is captured, and writes chunks to the app's
// own external files dir for adb to pull.
//
// For a rooted device where anti-tamper can be neutralized first, use the hook-based
// frida_lua_dump.js (exact bytecode). Here, read-only is the survivable path.

'use strict';

function pkgName() {
    try { return new File('/proc/self/cmdline', 'r').readText().split('\x00')[0].trim(); }
    catch (e) { return 'unknown.pkg'; }
}

var PKG = pkgName();
var DIR = '/sdcard/Android/data/' + PKG + '/files/_fdump';
try {
    var mkdir = new NativeFunction(Module.getExportByName(null, 'mkdir'), 'int', ['pointer', 'int']);
    mkdir(Memory.allocUtf8String(DIR), 0x1ff);
} catch (e) {}

var N = 0, seen = {};
function dump(prefix, addr, bytes) {
    try {
        // cheap dedup by first 32 bytes hex
        var head = new Uint8Array(bytes.slice(0, 32)).join(',');
        if (seen[head]) return; seen[head] = 1;
        var f = new File(DIR + '/' + prefix + '_' + (N++) + '.luac', 'wb');
        f.write(bytes); f.close();
    } catch (e) {}
}

function sweep(tag) {
    var hits = 0;
    Process.enumerateRanges('r--').forEach(function (r) {
        try {
            Memory.scan(r.base, r.size, '1b 4c 75 61', {   // \x1bLua
                onMatch: function (addr) {
                    try {
                        var ver = addr.add(4).readU8();
                        if (ver < 0x51 || ver > 0x54) return;
                        var end = Math.min(1 << 22, r.base.add(r.size).sub(addr).toInt32());
                        if (end > 8) { dump('mem', addr, addr.readByteArray(end)); hits++; }
                    } catch (e) {}
                },
                onError: function () {}, onComplete: function () {}
            });
        } catch (e) {}
    });
    try { var f = new File(DIR + '/_sweep_' + tag + '.txt', 'w'); f.write('' + hits); f.close(); } catch (e) {}
}

// repeated sweeps: Lua is decrypted into RAM as the app boots and enters the game.
[8000, 20000, 35000, 55000, 80000].forEach(function (t, i) {
    setTimeout(function () { sweep(i); if (i === 4) { try { new File(DIR + '/_done.txt', 'w').close(); } catch (e) {} } }, t);
});
