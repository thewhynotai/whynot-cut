// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
//
// js_runner.js - run the pure browser-style modules of a tool (Hush, later Tidy/Kalam) under plain node, the way the
// jsc test harnesses of the upstream panels load them (`window` is the global object, files are evaluated in order).
//
//   node js_runner.js <tool_root> <request.json>
//
// <tool_root>   a directory holding js/<file>.js (upstream: adobe/tools/hush/_upstream, the port: adobe/tools/hush/src)
// request.json  {"load": ["js/wav.js", ...],
//                "calls": [{"fn": "HushDetect.silences", "args": [...], "typed": {"0": "Float32Array"},
//                           "bytes_file": "<path>"}]}
//   load        files read relative to <tool_root>, evaluated in order with vm.runInThisContext (global scope).
//   fn          dotted path from the global object. A function is called with its parent as `this`; a non-function
//               (a constant such as HushFillers.DEFAULT_STRONG) is returned as it is.
//   typed       {"<arg index>": "<TypedArray name>"}: that argument (a JSON array) becomes `new <name>(array)`.
//   $file       an argument written {"$file": "<path>"} becomes a Uint8Array with that file's bytes.
//   $dataview   an argument written {"$dataview": <index>} becomes a DataView over the bytes of argument <index>
//               (HushWav.header takes (bytes, dataView)).
//   bytes_file  shorthand: argument 0 becomes the Uint8Array of that file (args[0] is replaced, or inserted when args
//               is empty).
// Output: ONE json line {"results": [...]} on stdout, one slot per call. Typed arrays become plain arrays; Infinity,
// -Infinity and NaN become the strings "Infinity", "-Infinity", "NaN" (undefined object fields are dropped by JSON).
// A call that throws gives {"error": "<message>"} in its slot and the run continues.
// A result that cannot be turned into JSON (a BigInt, a cycle) is that slot's {"error": ...}, not a crash.
// Exit code: 0; 2 when the request or the tool root is unreadable; 3 when a file named in "load" fails to evaluate
// (the message goes to stderr, nothing to stdout). The process ends on its own with process.exitCode set.
'use strict';
var fs = require('fs');
var path = require('path');
var vm = require('vm');

function Fatal(code, msg) { this.code = code; this.msg = msg; }

function bytesOf(file) {
    var b = fs.readFileSync(file);
    var u = new Uint8Array(b.length); // own buffer: byteOffset 0, like a file read in the panel
    u.set(b);
    return u;
}

function prepareArgs(call) {
    var args = (call.args || []).slice(0);
    if (call.bytes_file) { if (args.length) { args[0] = bytesOf(call.bytes_file); } else { args.push(bytesOf(call.bytes_file)); } }
    args = args.map(function (a) {
        return (a && typeof a === 'object' && !Array.isArray(a) && typeof a.$file === 'string') ? bytesOf(a.$file) : a;
    });
    args = args.map(function (a) {
        if (a && typeof a === 'object' && !Array.isArray(a) && typeof a.$dataview === 'number') {
            var b = args[a.$dataview];
            return new DataView(b.buffer, b.byteOffset, b.byteLength);
        }
        return a;
    });
    var typed = call.typed || {};
    Object.keys(typed).forEach(function (k) {
        var Ctor = globalThis[typed[k]];
        if (typeof Ctor !== 'function') { throw new Error('unknown typed array ' + typed[k]); }
        args[Number(k)] = new Ctor(args[Number(k)]);
    });
    return args;
}

function plain(v) {
    if (typeof v === 'number') {
        if (v === Infinity) { return 'Infinity'; }
        if (v === -Infinity) { return '-Infinity'; }
        if (v !== v) { return 'NaN'; }
        return v;
    }
    if (v === null || typeof v !== 'object') { return v; }
    if (ArrayBuffer.isView(v)) { return Array.prototype.map.call(v, plain); }
    if (Array.isArray(v)) { return v.map(plain); }
    var o = {};
    Object.keys(v).forEach(function (k) { o[k] = plain(v[k]); });
    return o;
}

function resolve(fn) {
    var parts = String(fn).split('.'), parent = globalThis, i;
    for (i = 0; i < parts.length - 1; i++) {
        parent = parent == null ? undefined : parent[parts[i]];
    }
    if (parent == null) { throw new Error('not found: ' + fn); }
    var name = parts[parts.length - 1];
    if (!(name in Object(parent))) { throw new Error('not found: ' + fn); }
    return { parent: parent, value: parent[name] };
}

function run(call) {
    var r = resolve(call.fn);
    return plain(typeof r.value !== 'function' ? r.value : r.value.apply(r.parent, prepareArgs(call)));
}

function main() {
    if (process.argv.length < 4) { throw new Fatal(2, 'usage: node js_runner.js <tool_root> <request.json>'); }
    var root = path.resolve(process.argv[2]);
    var req;
    try {
        if (!fs.statSync(root).isDirectory()) { throw new Error('tool root is not a directory: ' + root); }
        req = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
    } catch (e) { throw new Fatal(2, 'cannot read request or tool root: ' + e.message); }

    globalThis.window = globalThis;
    (req.load || []).forEach(function (rel) {
        var file = path.join(root, rel);
        try { vm.runInThisContext(fs.readFileSync(file, 'utf8'), { filename: file }); }
        catch (e) { throw new Fatal(3, 'cannot load ' + file + ': ' + e.message); }
    });

    // each result is serialised inside its own try: one unserialisable value only spoils its own slot
    var slots = (req.calls || []).map(function (call) {
        var j;
        try { j = JSON.stringify(run(call)); }
        catch (e) { j = JSON.stringify({ error: String(e && e.message !== undefined ? e.message : e) }); }
        return j === undefined ? 'null' : j;
    });
    process.stdout.write('{"results":[' + slots.join(',') + ']}\n');
}

try { main(); }
catch (e) {
    if (!(e instanceof Fatal)) { e = new Fatal(2, String(e && e.message !== undefined ? e.message : e)); }
    process.stderr.write(e.msg + '\n');
    process.exitCode = e.code; // no process.exit(): stderr is flushed before the process ends
}
