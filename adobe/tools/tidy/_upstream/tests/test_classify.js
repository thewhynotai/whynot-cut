// run from tidy/: jsc tests/test_classify.js
var window = this;
load('js/classify.js');
var C = window.TidyClassify, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
function item(name, path, extra) {
    var it = { name: name, path: path, isSequence: false, duration: 10, nodeId: 'x' };
    for (var k in (extra || {})) { it[k] = extra[k]; }
    return it;
}
var REELS = { nestIds: { n1: true }, mode: 'reels' };
function cat(name, path, extra) { return C.category(item(name, path, extra), REELS); }
function bin(name, path, extra, ctx) { var it = item(name, path, extra), c = ctx || REELS; return C.binFor(C.category(it, c), it, c); }

ok(cat('Script 1 - 2.mp4', '/a/Script 1 - 2.mp4', { kind: 'camera' }) === 'footage', 'a renamed camera file is footage');
ok(cat('Render 2.mp4', '/a/Render 2.mp4', { kind: 'render' }) === 'renders', 'a render is not footage');
ok(cat('BLADE WHOOSH SFX.mp4', '/a/BLADE WHOOSH SFX.mp4', { kind: 'render', duration: 2 }) === 'sfx', 'a sound effect saved as video is SFX');
ok(cat('clip.mp4', '/a/clip.mp4') === 'renders', 'a video with no camera evidence is not footage');
ok(cat('White smoke.mov', '/a/White smoke.mov', { kind: 'render' }) === 'renders' && cat('Architecture B-roll.mp4', '/a/Architecture B-roll.mp4', { kind: 'render' }) === 'renders', 'SFX words only as whole words for videos');
ok(C.category(item('Host.wav', '/a/Host.wav', { duration: 3600 }), { mode: 'podcast' }) === 'mics' && C.category(item('Guest Track.wav', '/a/Guest Track.wav', { duration: 3600 }), { mode: 'podcast' }) === 'mics', 'podcast: long recorder files are mics even when a word looks like music');
ok(cat('bg.png', '/a/bg.png') === 'png' && cat('photo.JPG', '/a/photo.JPG') === 'jpg' && cat('p.jpeg', '/a/p.jpeg') === 'jpg', 'PNG and JPG');
ok(cat('logo.png', '/a/logo.png', { icon: true }) === 'icons', 'an icon goes to Icons whatever its format');
ok(cat('art.webp', '/a/art.webp') === 'images', 'other image formats');
ok(cat('title.mogrt', '/a/title.mogrt') === 'graphics' && cat('Graphic', '') === 'graphics', 'graphics');
ok(cat('subs.srt', '/a/subs.srt') === 'captions', 'captions');
ok(cat('whoosh.wav', '/a/whoosh.wav', { duration: 0.8 }) === 'sfx' && cat('music.wav', '/a/music.wav', { duration: 60 }) === 'music', 'sfx and music');
ok(cat('interview.wav', '/a/interview.wav', { duration: 300 }) === 'voice', 'reels: a long recording is voice');
ok(C.category(item('ZOOM0001.WAV', '/a/ZOOM0001.WAV', { duration: 3600 }), { mode: 'podcast' }) === 'mics', 'podcast: a long recorder file is a mic');
ok(C.category(item('song.wav', '/a/song.wav', { duration: 240 }), { mode: 'podcast' }) === 'music', 'podcast: music stays music');
ok(cat('Main', '', { isSequence: true, nodeId: 's1' }) === 'sequences' && cat('Nest', '', { isSequence: true, nodeId: 'n1' }) === 'nests', 'sequences and nests');
ok(cat('data.xyz', '/a/data.xyz') === 'other', 'other');

ok(bin('a.mp4', '/a/a.mp4', { kind: 'camera' }) === '01 Footage', 'reels footage bin');
ok(bin('r.mp4', '/a/r.mp4', { kind: 'render' }) === '02 Renders & Stock', 'renders bin');
ok(bin('bg.png', '/a/bg.png') === '04 Images/PNG' && bin('i.png', '/a/i.png', { icon: true }) === '04 Images/Icons' && bin('x.webp', '/a/x.webp') === '04 Images/Other', 'image sub-bins');
ok(bin('s.wav', '/a/s.wav', { duration: 1 }) === '03 Audio/SFX', 'audio bins');
var cams = C.cameraNumbers([
    item('a1', '/A/a1.mp4', { kind: 'camera', camId: 'DJI OsmoPocket3', duration: 600 }),
    item('b1', '/B/b1.mov', { kind: 'camera', camId: 'iPhone 16 Pro Max', duration: 900 }),
    item('a2', '/A/a2.mp4', { kind: 'camera', camId: 'DJI OsmoPocket3', duration: 500 }),
    item('r', '/r.mp4', { kind: 'render', camId: 'x', duration: 5000 })
]);
ok(cams['DJI OsmoPocket3'] === 1 && cams['iPhone 16 Pro Max'] === 2 && !cams.x, 'cameras numbered by total footage: ' + JSON.stringify(cams));
var POD = { mode: 'podcast', camNumbers: cams };
ok(bin('b1', '/B/b1.mov', { kind: 'camera', camId: 'iPhone 16 Pro Max' }, POD) === '01 Footage/Cam 2', 'podcast footage goes to its camera bin');
ok(bin('ZOOM0001.WAV', '/a/ZOOM0001.WAV', { duration: 3600 }, POD) === '03 Audio/Mics', 'podcast mics bin');
ok(typeof C.COLORS.footage === 'number' && C.COLORS.footage !== C.COLORS.renders && C.COLORS.png === C.COLORS.jpg, 'colours: footage and renders differ, images share one');
print(fails ? fails + ' FAILED' : 'ALL PASS');
