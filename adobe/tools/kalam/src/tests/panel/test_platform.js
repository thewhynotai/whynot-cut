// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// R3 copy of kalam/_upstream/tests/panel/test_platform.js, run with cwd = adobe/tools/kalam/src:
//   node adobe/tools/_harness/jsc_shim.js adobe/tools/kalam/src tests/panel/test_platform.js
// The owner's checks stay as they are except for these differences (A6b names and layout, audit 3.1):
//  1. P.paths(platform, engineHome, sep) replaces P.paths(platform, env, homedir, sep): every folder is under the engine
//     home, <engineHome>/tools/kalam, on both OS (no LOCALAPPDATA / Library/Application Support, no "Kalam" folder), and
//     there is no `py` (the engine runtime runs Kalam). The six paths checks (win home, win python.exe, win folders,
//     win home without LOCALAPPDATA, mac paths, mac models/hf) become six: win home, no py, win folders, an Arabic user
//     folder, mac paths, mac folders.
//  2. The three KalamCEP.cleanPath checks and `load('js/cep.js')` are dropped: cep.js is not ported (the bridge replaces it).
//  3. safeName: the owner's file-name check uses a fictional name (no client name) and gets the same expected value; new
//     checks for the Windows reserved device names (also with an extension), trailing dots and spaces, and the empty result.
//  4. New checks for P.fileUrl: drive path, POSIX path, encoding of spaces, '#', '?', '%' and Arabic, UNC path.
// childEnv, revealCmd, openCmd and templatesDir checks are the owner's lines, unchanged.
var window = this;
load('js/platform.js');
var P = window.KalamPlatform, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }

var h = 'C:\\Users\\x\\.whynot-cut\\tools\\kalam';
var w = P.paths('win32', 'C:\\Users\\x\\.whynot-cut', '\\');
ok(w.home === h, 'win home under the engine home: ' + w.home);
ok(!('py' in w), 'no python path: the engine runtime runs Kalam');
ok(w.models === h + '\\models' && w.hf === h + '\\hf' && w.logs === h + '\\logs' && w.cache === h + '\\cache', 'win folders');
var wa = P.paths('win32', 'D:\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\.whynot-cut', '\\');
ok(wa.home === 'D:\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\.whynot-cut\\tools\\kalam', 'Arabic user folder: ' + wa.home);

var m = P.paths('darwin', '/Users/x/.whynot-cut', '/');
ok(m.home === '/Users/x/.whynot-cut/tools/kalam' && !('py' in m), 'mac paths under the engine home: ' + m.home);
ok(m.models === m.home + '/models' && m.hf === m.home + '/hf' && m.logs === m.home + '/logs' && m.cache === m.home + '/cache', 'mac folders');

var e = P.childEnv('win32', { PATH: 'C:\\Windows' });
ok(e.PYTHONUTF8 === '1' && e.PYTHONIOENCODING === 'utf-8' && e.PATH === 'C:\\Windows', 'child env forces UTF-8 and keeps PATH');

var r = P.revealCmd('win32', 'C:\\a b\\captions.srt');
ok(r[0] === 'explorer' && r[1][0] === '/select,C:\\a b\\captions.srt', 'win reveal: ' + r[1]);
var o = P.openCmd('win32', 'C:\\x');
ok(o[0] === 'explorer' && o[1][0] === 'C:\\x', 'win open');
ok(P.revealCmd('darwin', '/a.srt')[0] === 'open' && P.revealCmd('darwin', '/a.srt')[1][0] === '-R', 'mac reveal');

ok(P.templatesDir('darwin', {}, '/Users/x', '/') === '/Users/x/Library/Application Support/Adobe/Common/Motion Graphics Templates', 'Mac Local Templates folder');
ok(P.templatesDir('win32', { APPDATA: 'C:\\Users\\x\\AppData\\Roaming' }, 'C:\\Users\\x', '\\') === 'C:\\Users\\x\\AppData\\Roaming\\Adobe\\Common\\Motion Graphics Templates', 'Windows Local Templates folder');
ok(P.safeName('Episode 2: "final" <v2>?|*\\x/y') === 'Episode 2- -final- -v2-----x-y', 'file names safe on Windows: ' + P.safeName('Episode 2: "final" <v2>?|*\\x/y'));
ok(P.safeName('nul') === 'nul_' && P.safeName('NUL.srt') === 'NUL_.srt' && P.safeName('Com1') === 'Com1_' && P.safeName('lpt9.tar.gz') === 'lpt9_.tar.gz',
   'Windows device names get an underscore, also with an extension');
ok(P.safeName('console') === 'console' && P.safeName('nullable.srt') === 'nullable.srt' && P.safeName('COM10') === 'COM10' && P.safeName('my.nul') === 'my.nul',
   'names that only start like a device name stay');
ok(P.safeName('name. . ') === 'name' && P.safeName('con.') === 'con_' && P.safeName('aux ') === 'aux_', 'trailing dots and spaces are stripped first');
ok(P.safeName('') === '_' && P.safeName('...') === '_' && P.safeName('   ') === '_', 'an empty result becomes an underscore');
ok(P.fileUrl('C:\\Users\\x\\a b\\t#1?.png') === 'file:///C:/Users/x/a%20b/t%231%3F.png', 'file URL of a drive path: ' + P.fileUrl('C:\\Users\\x\\a b\\t#1?.png'));
ok(P.fileUrl('/Users/x/a b.png') === 'file:///Users/x/a%20b.png' && P.fileUrl('/Users/\u0645/a%b.png') === 'file:///Users/%D9%85/a%25b.png', 'file URL of a POSIX path, Arabic and % encoded');
ok(P.fileUrl('\\\\srv\\share\\a b.png') === 'file://srv/share/a%20b.png', 'file URL of a UNC path');
print(fails ? fails + ' FAILED' : 'ALL PASS');
