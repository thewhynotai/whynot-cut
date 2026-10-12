/* Tidy - what a media file is, from its own bytes (read only): camera original or render, which camera,
   image size, icon or not. Pure: the panel passes the latin1 text of the first and last 2 MB of a file. */
(function (root) {
    'use strict';
    var M = {};

    // render evidence beats camera evidence: exports keep the tags of their sources
    var RENDER_TAGS = /(CreatorTool|Mainconcept|MainConcept|Lavf\d|HandBrake|CapCut|Adobe Media Encoder|DaVinci Resolve)/;
    var RENDER_NAME = /(render|export|final|compose|_edit|\bedit\b)/i;
    var CAMERA_TAGS = /(DJI (Osmo|Pocket|Action|Mini|Mavic|Air|Avata|Neo|Mimo)|com\.apple\.quicktime\.model|NonRealTimeMeta|GoPro|Insta360|Canon|Panasonic|Blackmagic|FUJIFILM|NIKON|com\.android\.manufacturer|samsung)/;
    var CAMERA_NAME = /^(C\d{4}|IMG_\d+|DJI_\d+|GX\d{6}|GH\d{6}|GOPR\d+|MVI_\d+|DSC_?\d+|A\d{3}C\d{3}|PXL_\d+|VID_\d+|MAH\d+|P\d{7}|\d{5}\.MTS$)/i;
    var CAMERA_RAW = /\.(r3d|braw|crm|ari|insv)$/i;   // camera originals only

    /* the file's own tags first (users rename camera files), then its name */
    M.videoKind = function (text, name) {
        text = text || ''; name = name || '';
        if (RENDER_TAGS.test(text)) { return 'render'; }
        if (CAMERA_TAGS.test(text)) { return 'camera'; }
        if (RENDER_NAME.test(name)) { return 'render'; }
        return CAMERA_NAME.test(name) ? 'camera' : 'render';
    };

    M.cameraModel = function (text) {
        var m = /DJI ((Osmo|Pocket|Action|Mini|Mavic|Air|Avata|Neo)[A-Za-z0-9 ]{0,20}?)(?=[^A-Za-z0-9 ]|$)/.exec(text || '');
        if (m) { return 'DJI ' + m[1].replace(/\s+$/, ''); }
        m = /(iPhone \d{1,2}(?: (?:Pro|Plus|Max|mini|SE|e))*)/.exec(text || '');
        if (m) { return m[1].replace(/\s+$/, ''); }
        m = /(ILCE-\w+|ZV-\w+|FX\d+|DC-\w+|EOS[ \w-]{1,12}|HERO\d+[ \w]{0,10}|Insta360 [\w ]{1,12}|BMPCC\w*)/.exec(text || '');
        return m ? m[1].replace(/\s+$/, '') : '';
    };
    /* which camera made it: model + folder (identical cameras are usually kept in their own folders), else folder */
    M.cameraId = function (text, name, dir) {
        var model = M.cameraModel(text);
        return model ? model + ' | ' + (dir || '') : 'folder:' + (dir || '');
    };

    function u16be(s, i) { return (s.charCodeAt(i) << 8) | s.charCodeAt(i + 1); }
    function u32be(s, i) { return ((s.charCodeAt(i) << 24) >>> 0) + (s.charCodeAt(i + 1) << 16) + (s.charCodeAt(i + 2) << 8) + s.charCodeAt(i + 3); }
    function u16le(s, i) { return s.charCodeAt(i) | (s.charCodeAt(i + 1) << 8); }

    /* {w, h} from the image header, or null */
    M.imageSize = function (s, ext) {
        if (!s || s.length < 24) { return null; }
        if (s.slice(1, 4) === 'PNG' && s.slice(12, 16) === 'IHDR') { return { w: u32be(s, 16), h: u32be(s, 20) }; }
        if (s.charCodeAt(0) === 0xff && s.charCodeAt(1) === 0xd8) {
            var i = 2;
            while (i + 9 < s.length) {
                if (s.charCodeAt(i) !== 0xff) { i++; continue; }
                var mk = s.charCodeAt(i + 1);
                if (mk >= 0xc0 && mk <= 0xcf && mk !== 0xc4 && mk !== 0xc8 && mk !== 0xcc) {
                    return { w: u16be(s, i + 7), h: u16be(s, i + 5) };
                }
                if (mk === 0xd8 || mk === 0x01 || (mk >= 0xd0 && mk <= 0xd7) || mk === 0xff) { i += 2; continue; }
                i += 2 + u16be(s, i + 2);
            }
            return null;
        }
        if (s.slice(0, 3) === 'GIF') { return { w: u16le(s, 6), h: u16le(s, 8) }; }
        if (s.slice(0, 4) === 'RIFF' && s.slice(8, 12) === 'WEBP') {
            var kind = s.slice(12, 16);
            if (kind === 'VP8X') { return { w: 1 + (s.charCodeAt(24) | (s.charCodeAt(25) << 8) | (s.charCodeAt(26) << 16)),
                                            h: 1 + (s.charCodeAt(27) | (s.charCodeAt(28) << 8) | (s.charCodeAt(29) << 16)) }; }
            if (kind === 'VP8 ') { return { w: u16le(s, 26) & 0x3fff, h: u16le(s, 28) & 0x3fff }; }
            if (kind === 'VP8L') {
                var b = s.charCodeAt(21) | (s.charCodeAt(22) << 8) | (s.charCodeAt(23) << 16) | (s.charCodeAt(24) << 24);
                return { w: (b & 0x3fff) + 1, h: ((b >>> 14) & 0x3fff) + 1 };
            }
        }
        return null;
    };

    M.ICON_MAX = 512;
    M.isIcon = function (name, ext, size) {
        if (ext === 'svg' || ext === 'ico' || ext === 'icns') { return true; }
        if (/(icon|logo|emoji)/i.test(name || '')) { return true; }
        return !!size && Math.max(size.w, size.h) <= M.ICON_MAX;
    };

    var VIDEO_EXT = /\.(mp4|mov|m4v|mxf|avi|mts|m2ts|mkv|insv|3gp)$/i, IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|ico|icns)$/i;
    /* what the panel must read for an item: 'video' (first + last 2 MB), 'image' (first 64 KB) or null */
    M.needsBytes = function (item) {
        var p = item.path || '';
        return VIDEO_EXT.test(p) ? 'video' : (IMAGE_EXT.test(p) ? 'image' : null);
    };
    function dirOf(p) { var i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\')); return i > 0 ? p.slice(0, i) : ''; }

    /* fill item.kind / camId (videos) or icon / imgW / imgH (images) from the bytes read (null if unreadable) */
    M.describe = function (item, text) {
        var need = M.needsBytes(item), ext = (/\.([A-Za-z0-9]+)$/.exec(item.path || '') || ['', ''])[1].toLowerCase();
        if (CAMERA_RAW.test(item.path || '')) {
            item.kind = 'camera';
            item.camId = M.cameraId('', item.name, dirOf(item.path));
        } else if (need === 'video') {
            item.kind = M.videoKind(text || '', item.name);
            item.camId = M.cameraId(text || '', item.name, dirOf(item.path));
        } else if (need === 'image') {
            var size = M.imageSize(text || '', ext);
            if (size) { item.imgW = size.w; item.imgH = size.h; }
            item.icon = M.isIcon(item.name, ext, size);
        }
        return item;
    };

    /* the words of a graphic clip, from the JSON text Premiere returns for "Source Text" (no JSON object in ExtendScript) */
    M.textFromValue = function (v) {
        var m = /"textEditValue"\s*:\s*"((?:\\.|[^"\\])*)"/.exec(v ? String(v) : '');
        if (!m) { return ''; }
        var t = m[1].replace(/\\u([0-9a-fA-F]{4})/g, function (a, h) { return String.fromCharCode(parseInt(h, 16)); })
                    .replace(/\\[nr]/g, ' ').replace(/\\(.)/g, '$1');
        return t.replace(/[\s\u00a0]+/g, ' ').replace(/^ | $/g, '');
    };

    root.TidyMedia = M;
})(typeof window !== 'undefined' ? window : this);
