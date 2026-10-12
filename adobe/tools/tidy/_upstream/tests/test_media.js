// run from tidy/: jsc tests/test_media.js
var window = this;
load('js/media.js');
var M = window.TidyMedia, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }

// byte strings as the panel reads them (latin1 text of the first and last 2 MB)
var DJI = '\u0000\u0000ftypisom....©too\u0000\u0000DJI OsmoPocket3\u0000..DJI meta..DJI dbgi';
var IPHONE = 'ftypqt  ..com.apple.quicktime.software..iPhone OSV26.3.1..com.apple.quicktime.make..Apple..com.apple.quicktime.model..iPhone 16 Pro Max..Core Media Video';
var AE = 'ftypmp42..Mainconcept Video Media Handler..<x:xmpmeta xmp:CreatorTool="Adobe After Effects 2026 (Windows)"/>..Apple..DJI';
var COMPOSE = 'ftypqt  ..Core Media Video..Core Media Audio..Core Media Data Handler';
var LAVF = 'ftypisom....Lavf61.7.100';

ok(M.videoKind(DJI, 'Script 1 - 2.mp4') === 'camera', 'renamed DJI Pocket file is camera');
ok(M.videoKind(IPHONE, 'IMG_3886.MOV.mov') === 'camera', 'iPhone file is camera');
ok(M.videoKind(AE, 'Script 4.mp4') === 'render', 'After Effects render with source tags is render');
ok(M.videoKind(COMPOSE, 'dji_export_20261010_234451_0.f_compose_0.mov') === 'render', 'DJI app compose export is render');
ok(M.videoKind(LAVF, 'clip.mp4') === 'render', 'ffmpeg output is render');
ok(M.videoKind('', 'C0890.MP4') === 'camera', 'unreadable file with a camera name is camera');
ok(M.videoKind('', 'A001C002_220101_R1AB.mov') === 'camera', 'cinema camera name is camera');
ok(M.videoKind('', 'clip.mp4') === 'render', 'unreadable file without camera evidence is render');
ok(M.videoKind('...NonRealTimeMeta...Sony...', 'Interview.MP4') === 'camera', 'Sony XML is camera');
ok(M.videoKind(DJI, 'Interview final.mp4') === 'camera' && M.videoKind(DJI, 'Ahmed edit.mp4') === 'camera', 'camera tags beat render words in a renamed file');
ok(M.videoKind('', 'Interview final.mp4') === 'render', 'without tags, a render word in the name means render');
ok(M.videoKind('', '00001.MTS') === 'camera', 'AVCHD file names are camera');

ok(M.cameraId(DJI, 'a.mp4', '/RAW/A') === 'DJI OsmoPocket3 | /RAW/A', 'DJI camera id from model and folder: ' + M.cameraId(DJI, 'a.mp4', '/RAW/A'));
ok(M.cameraModel(IPHONE) === 'iPhone 16 Pro Max', 'iPhone model: ' + M.cameraModel(IPHONE));
ok(M.cameraId('', 'C0001.MP4', '/x/Cam B') === 'folder:/x/Cam B', 'no model: folder is the id');
ok(M.cameraId(DJI, 'a.mp4', '/P/Cam A') !== M.cameraId(DJI, 'b.mp4', '/P/Cam B'), 'two identical cameras in different folders are two cameras');
ok(M.cameraId(DJI, 'a.mp4', '/P/Cam A') === M.cameraId(DJI, 'c.mp4', '/P/Cam A'), 'same model, same folder: one camera');

function bytes(arr) { var s = ''; for (var i = 0; i < arr.length; i++) { s += String.fromCharCode(arr[i]); } return s; }
var png64 = bytes([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 64, 0, 0, 0, 48]);
var sz = M.imageSize(png64, 'png');
ok(sz && sz.w === 64 && sz.h === 48, 'PNG size from IHDR');
var jpg = bytes([0xff, 0xd8, 0xff, 0xe0, 0, 16, 0x4a, 0x46, 0x49, 0x46, 0, 1, 1, 0, 0, 1, 0, 1, 0, 0,
                 0xff, 0xc0, 0, 17, 8, 0x04, 0x38, 0x07, 0x80, 3]);
sz = M.imageSize(jpg, 'jpg');
ok(sz && sz.w === 1920 && sz.h === 1080, 'JPEG size from SOF0: ' + (sz && sz.w + 'x' + sz.h));
ok(M.imageSize('', 'png') === null, 'unreadable image has no size');

ok(M.isIcon('a.png', 'png', { w: 64, h: 48 }) === true, 'small PNG is an icon');
ok(M.isIcon('bg.jpg', 'jpg', { w: 1920, h: 1080 }) === false, 'big JPG is not an icon');
ok(M.isIcon('Company Logo.png', 'png', { w: 2000, h: 2000 }) === true, 'logo by name is an icon');
ok(M.isIcon('x.svg', 'svg', null) === true, 'svg is an icon');
ok(M.isIcon('photo.png', 'png', null) === false, 'unknown size is not an icon');

var v = { name: 'Script 1 - 2.mp4', path: '/Volumes/X/RAW/Script 1/Script 1 - 2.mp4' };
M.describe(v, DJI);
ok(v.kind === 'camera' && v.camId === 'DJI OsmoPocket3 | /Volumes/X/RAW/Script 1', 'describe: video kind and camera: ' + v.camId);
var u = { name: 'C0001.MP4', path: '/x/Cam B/C0001.MP4' };
M.describe(u, null);
ok(u.kind === 'camera' && u.camId === 'folder:/x/Cam B', 'describe: unreadable video falls back to name and folder');
var im = { name: 'a.png', path: '/x/a.png' };
M.describe(im, png64);
ok(im.icon === true && im.imgW === 64, 'describe: image size and icon');
var doc = { name: 'notes.txt', path: '/x/notes.txt' };
M.describe(doc, 'abc');
ok(doc.kind === undefined && doc.icon === undefined, 'describe: other files untouched');
var raw = { name: 'A001_C002_0101AB.R3D', path: '/r/A001_C002_0101AB.R3D' }; M.describe(raw, null);
var br = { name: 'clip.braw', path: '/r/clip.braw' }; M.describe(br, null);
ok(raw.kind === 'camera' && br.kind === 'camera', 'camera RAW formats are camera footage');
ok(M.needsBytes({ path: '/a/b.MOV' }) === 'video' && M.needsBytes({ path: '/a/b.jpeg' }) === 'image' && M.needsBytes({ path: '/a/b.wav' }) === null && M.needsBytes({ path: '' }) === null, 'which files are read');
// text inside a graphic clip, as Premiere's "Source Text" property returns it
ok(M.textFromValue('{"mTextParam":{"mStyleSheet":{}},"textEditValue":"\u0627\u0644\u062a\u0631\u0642\u064a\u0629\nNow"}') === '\u0627\u0644\u062a\u0631\u0642\u064a\u0629 Now', 'text of a graphic, lines joined');
ok(M.textFromValue('xx{"textEditValue":"5"}') === '5' && M.textFromValue('{"fontSize":40}') === '' && M.textFromValue(null) === '', 'a number, no text, nothing');
print(fails ? fails + ' FAILED' : 'ALL PASS');
