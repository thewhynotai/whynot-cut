// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
//
// jsc_shim.js - run one of the owner's JavaScriptCore (macOS `jsc`) test files under plain node, unchanged.
//
//   node jsc_shim.js <tool_root> <test_file>
//
// <tool_root>  the tool's root (upstream: adobe/tools/<tool>/_upstream, the port: adobe/tools/<tool>/src). It becomes
//              the working directory, because the tests name their files relative to it (`load('js/range.js')`,
//              `readFile('tests/panel/fixtures/tiny.mogrt', 'binary')`).
// <test_file>  the test, relative to <tool_root>; evaluated as a script in the global scope.
//
// jsc globals provided:
//   print(...)               console.log
//   readFile(path)           the file as a UTF-8 string (relative paths resolve against <tool_root>)
//   readFile(path, 'binary') a Uint8Array copy of the bytes (indexable, .length, .slice and .subarray as jsc's)
//   load(path)               evaluates the file in the global scope (vm.runInThisContext)
//   this                     at the top level of a test is the global object, so `var window = this;` works; `window`
//                            is deliberately NOT predefined, as in jsc (the modules end with `})(window)`)
// Nothing is written to disk. The exit code is 0 when the test script ran to its end; 2 on a usage or an unreadable
// root or test file; 1 when the test script (or a file it loads) throws, with the error on stderr. Whether the checks
// passed is read from the test's own output (`FAIL ` lines, final `ALL PASS`). The code is set through
// process.exitCode and the process ends by itself, so everything printed has been flushed (a pipe write is not
// synchronous on every platform).
'use strict';
var fs = require('fs');
var path = require('path');
var vm = require('vm');

function main(argv) {
    if (argv.length < 4) { return fail(2, 'usage: node jsc_shim.js <tool_root> <test_file>'); }
    var root = path.resolve(argv[2]);
    var testFile = argv[3];
    try {
        if (!fs.statSync(root).isDirectory()) { return fail(2, 'tool root is not a directory: ' + root); }
        process.chdir(root);
    } catch (e) { return fail(2, 'cannot use tool root ' + root + ': ' + e.message); }

    function resolve(p) { return path.resolve(root, String(p)); }

    globalThis.print = function () {
        var parts = [], i;
        for (i = 0; i < arguments.length; i++) { parts.push(String(arguments[i])); }
        process.stdout.write(parts.join(' ') + '\n');
    };
    globalThis.readFile = function (p, mode) {
        var buf = fs.readFileSync(resolve(p));
        if (mode === 'binary') { return new Uint8Array(buf); }
        return buf.toString('utf8');
    };
    globalThis.load = function (p) {
        var file = resolve(p);
        return vm.runInThisContext(fs.readFileSync(file, 'utf8'), { filename: file });
    };

    var testPath;
    try { testPath = resolve(testFile); fs.accessSync(testPath, fs.constants.R_OK); }
    catch (e) { return fail(2, 'cannot read test file ' + testFile + ': ' + e.message); }
    try {
        vm.runInThisContext(fs.readFileSync(testPath, 'utf8'), { filename: testPath });
    } catch (e) {
        return fail(1, 'test script failed: ' + (e && e.stack ? e.stack : e));
    }
    return 0;
}

function fail(code, msg) { process.stderr.write(msg + '\n'); return code; }

process.exitCode = main(process.argv);
