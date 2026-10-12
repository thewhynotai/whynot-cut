// run: jsc tests/panel/test_mogrt.js   (from kalam/)
var window = this;
load('js/mogrt.js');
var G = window.KalamMogrt, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
var bytes = readFile('tests/panel/fixtures/tiny.mogrt', 'binary');
var es = G.zipEntries(bytes);
var names = es.map(function (e) { return e.name; });
ok(names.join(',') === 'definition.json,project.aegraphic,thumb.png', 'zip entries from the central directory: ' + names);
var def = es[0], start = G.dataStart(bytes, def);
var txt = ''; for (var i = 0; i < def.compSize; i++) { txt += String.fromCharCode(bytes[start + i]); }
ok(def.method === 0 && JSON.parse(txt).capsuleName.indexOf('Test Subtitles') > 0, 'stored entry data starts after its local header');
var info = G.definitionInfo(JSON.parse(txt));
ok(info.name === '9•9 Test Subtitles' && info.textFields.join('|') === 'Text|Speaker', 'name and text fields: ' + JSON.stringify(info));
ok(G.definitionInfo({ capsuleName: 'Basic', clientControls: [] }).textFields.length === 0, 'no text fields');
ok(G.folderOf('/T/Captioneer/Portrait/a.mogrt', '/T') === 'Captioneer/Portrait' && G.folderOf('/T/Basic Title.mogrt', '/T') === '', 'folder relative to the templates root');
var list = [{ name: '9•16 Comic Subtitles', folder: 'Captioneer/Portrait' }, { name: 'Basic Title', folder: '' }, { name: 'Bold Web Caption', folder: 'Captions and Subtitles' }];
ok(G.filter(list, 'comic', '').length === 1 && G.filter(list, '', 'Captioneer').length === 1 && G.filter(list, 'CAPTION', '').length === 1, 'search by name, filter by top folder');
ok(G.topFolders(list).join('|') === 'Captioneer|Captions and Subtitles', 'top folders for the filter: ' + G.topFolders(list));
print(fails ? fails + ' FAILED' : 'ALL PASS');
