// frida_lua_dump.js - GENERIC runtime Lua bytecode dumper.
//
// Engine-agnostic: hooks the standard Lua load entrypoints wherever they are
// exported (tolua, XLua, vanilla Lua, LuaJIT-compat, or a game's own .so). The
// game decrypts/unpacks each chunk BEFORE calling these, so this captures the
// plaintext bytecode even when Lua ships encrypted. Works for any Lua-scripted
// game (merge, RPG, casino, ...), not one title.
//
// Each captured chunk is streamed to the host runner (tier1_lua.py) via send()
// with the raw bytes as the message payload. The runner dedups and decompiles.

'use strict';

// Standard Lua loaders. buf/size/name are ARG INDEXES after the lua_State (arg 0).
// size = -1 means the buffer is NUL-terminated (loadstring).
var LOADERS = [
  { sym: 'luaL_loadbufferx', buf: 1, size: 2, name: 3 }, // Lua 5.2+/tolua
  { sym: 'luaL_loadbuffer',  buf: 1, size: 2, name: 3 }, // Lua 5.1/tolua
  { sym: 'xluaL_loadbuffer', buf: 1, size: 2, name: 3 }, // XLua (Gossip-Harbor family)
  { sym: 'tolua_loadbuffer', buf: 1, size: 2, name: 3 }, // tolua# wrapper
  { sym: 'luaL_loadstring',  buf: 1, size: -1, name: -1 } // NUL-terminated source
];

function readChunkName(arg) {
  try { return arg.readCString() || ''; } catch (e) { return ''; }
}

function hookOne(addr, spec) {
  Interceptor.attach(addr, {
    onEnter: function (args) {
      try {
        var buf = args[spec.buf];
        var size = spec.size >= 0 ? args[spec.size].toInt32() : -1;
        if (size < 0) { // NUL-terminated: measure it, capped
          size = 0;
          while (size < (1 << 24) && buf.add(size).readU8() !== 0) size++;
        }
        if (size <= 0 || size > (1 << 25)) return; // sanity cap 32MB
        var bytes = buf.readByteArray(size);
        var name = spec.name >= 0 ? readChunkName(args[spec.name]) : '';
        send({ t: 'lua', sym: spec.sym, name: name, size: size }, bytes);
      } catch (e) {
        send({ t: 'err', where: spec.sym, msg: '' + e });
      }
    }
  });
}

function findExports(sym) {
  // Frida 17 removed Module.findExportByName(null|name, sym); use per-Module lookup.
  var out = {};
  Process.enumerateModules().forEach(function (m) {
    try {
      var e = null;
      if (typeof m.findExportByName === 'function') e = m.findExportByName(sym);
      else if (typeof Module.findExportByName === 'function') e = Module.findExportByName(m.name, sym);
      if (e) out[e.toString()] = true;
    } catch (err) {}
  });
  return out;
}

function installHooks() {
  var installed = 0;
  LOADERS.forEach(function (spec) {
    var addrs = findExports(spec.sym);
    Object.keys(addrs).forEach(function (a) {
      try { hookOne(ptr(a), spec); installed++; send({ t: 'hooked', sym: spec.sym, at: a }); }
      catch (e) { send({ t: 'err', where: 'attach:' + spec.sym, msg: '' + e }); }
    });
  });
  send({ t: 'ready', hooks: installed });
}

// Give the target a beat to map its native libs, then hook.
setTimeout(installHooks, 200);
