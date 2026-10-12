// run: jsc tests/panel/test_platform.js   (from kalam/)
var window = this;
load('js/platform.js');
load('js/cep.js');
var P = window.KalamPlatform, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }

var w = P.paths('win32', { LOCALAPPDATA: 'C:\\Users\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\AppData\\Local' }, 'C:\\Users\\x', '\\');
ok(w.home === 'C:\\Users\\\u0645\u062d\u0645\u062f \u0639\u0644\u064a\\AppData\\Local\\Kalam', 'win home under LOCALAPPDATA: ' + w.home);
ok(w.py === w.home + '\\python\\python.exe', 'win python.exe: ' + w.py);
ok(w.models === w.home + '\\models' && w.hf === w.home + '\\hf' && w.logs === w.home + '\\logs' && w.cache === w.home + '\\cache', 'win folders');

var wn = P.paths('win32', {}, 'C:\\Users\\x', '\\');
ok(wn.home === 'C:\\Users\\x\\AppData\\Local\\Kalam', 'win home without LOCALAPPDATA: ' + wn.home);

var m = P.paths('darwin', {}, '/Users/x', '/');
ok(m.home === '/Users/x/Library/Application Support/Kalam' && m.py === m.home + '/venv/bin/python', 'mac paths unchanged: ' + m.py);
ok(m.models === m.home + '/models' && m.hf === m.home + '/hf', 'mac models/hf');

var e = P.childEnv('win32', { PATH: 'C:\\Windows' });
ok(e.PYTHONUTF8 === '1' && e.PYTHONIOENCODING === 'utf-8' && e.PATH === 'C:\\Windows', 'child env forces UTF-8 and keeps PATH');

var r = P.revealCmd('win32', 'C:\\a b\\captions.srt');
ok(r[0] === 'explorer' && r[1][0] === '/select,C:\\a b\\captions.srt', 'win reveal: ' + r[1]);
var o = P.openCmd('win32', 'C:\\x');
ok(o[0] === 'explorer' && o[1][0] === 'C:\\x', 'win open');
ok(P.revealCmd('darwin', '/a.srt')[0] === 'open' && P.revealCmd('darwin', '/a.srt')[1][0] === '-R', 'mac reveal');

ok(P.templatesDir('darwin', {}, '/Users/x', '/') === '/Users/x/Library/Application Support/Adobe/Common/Motion Graphics Templates', 'Mac Local Templates folder');
ok(P.templatesDir('win32', { APPDATA: 'C:\\Users\\x\\AppData\\Roaming' }, 'C:\\Users\\x', '\\') === 'C:\\Users\\x\\AppData\\Roaming\\Adobe\\Common\\Motion Graphics Templates', 'Windows Local Templates folder');
var X = window.KalamCEP;
ok(X.cleanPath('file:///C:/Users/%D9%85%D8%AD%D9%85%D8%AF/AppData/Roaming/Adobe/CEP/extensions/com.hoka.kalam') === 'C:/Users/\u0645\u062d\u0645\u062f/AppData/Roaming/Adobe/CEP/extensions/com.hoka.kalam',
   'Windows extension path: no leading slash before the drive, Arabic decoded: ' + X.cleanPath('file:///C:/Users/%D9%85%D8%AD%D9%85%D8%AF/x'));
ok(X.cleanPath('file:///Users/x/Library/Application%20Support/Adobe/CEP/extensions/com.hoka.kalam') === '/Users/x/Library/Application Support/Adobe/CEP/extensions/com.hoka.kalam', 'Mac extension path unchanged');
ok(X.cleanPath('C:\\a\\b') === 'C:\\a\\b' && X.cleanPath('') === '', 'plain paths pass through');
ok(P.safeName('Rog 2: "final" <v2>?|*\\x/y') === 'Rog 2- -final- -v2-----x-y', 'file names safe on Windows: ' + P.safeName('Rog 2: "final" <v2>?|*\\x/y'));
print(fails ? fails + ' FAILED' : 'ALL PASS');
