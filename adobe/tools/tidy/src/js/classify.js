// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// Ported from the owner's Tidy classify.js; logic unchanged; see adobe/tools/tidy/src/README.md.
/* Tidy - which bin a project item belongs in (pure; used by the panel and the tests).
   item: {name, path, isSequence, duration (s), nodeId, kind ('camera'|'render', videos), icon (bool, images), camId}
   ctx:  {nestIds: {nodeId: true}, mode: 'reels'|'podcast', camNumbers: {camId: n}} */
(function (root) {
    'use strict';
    var C = {};
    C.BINS = {
        footage: '01 Footage', renders: '02 Renders & Stock',
        voice: '03 Audio/Voice', music: '03 Audio/Music', sfx: '03 Audio/SFX', mics: '03 Audio/Mics',
        png: '04 Images/PNG', jpg: '04 Images/JPG', icons: '04 Images/Icons', images: '04 Images/Other',
        graphics: '05 Graphics', sequences: '06 Sequences', nests: '07 Nests', captions: '08 Captions', other: '09 Other'
    };
    // Premiere label colour indexes (0 violet, 1 iris, 2 caribbean, 3 lavender, 4 cerulean, 5 forest,
    // 6 rose, 7 mango, 8 purple, 9 blue, 10 teal, 11 magenta, 12 tan, 13 green, 14 brown, 15 yellow)
    C.COLORS = { footage: 9, renders: 4, voice: 2, music: 8, sfx: 7, mics: 10, png: 3, jpg: 3, icons: 3, images: 3,
                 graphics: 11, sequences: 5, nests: 13, captions: 15, other: 12 };
    C.MIC_MIN = 180;   // podcast: a recorder file at least this long (s) is a mic track

    var VIDEO = 'mp4 mov m4v mxf avi mts m2ts mkv wmv webm r3d braw crm ari mpg mpeg 3gp dv insv',
        AUDIO = 'wav mp3 aif aiff m4a aac flac ogg wma caf bwf',
        IMAGE = 'png jpg jpeg tif tiff psd ai gif heic heif webp exr dpx tga bmp svg eps ico icns',
        CAPTION = 'srt vtt scc stl sbv mcc dfxp ttml',
        GRAPHIC = 'mogrt aegraphic prgraphic aep',
        RECORDER = 'wav bwf aif aiff';
    function has(list, ext) { return (' ' + list + ' ').indexOf(' ' + ext + ' ') >= 0; }
    var SFX_WORDS = /(sfx|fx_|whoosh|swoosh|swish|riser|hit|impact|boom|click|ding|pop|transition|glitch|beep|foley|ambience|ambient)/i;
    // videos: whole words only ("White smoke", "Architecture" are not sound effects)
    var SFX_VIDEO = /(^|[^a-z])(sfx|whoosh|swoosh|swish|riser|hit|impact|boom|click|ding|transition|glitch|beep|foley)([^a-z]|$)/i;
    var MUSIC_STRICT = /(^|[^a-z])(music|bgm|song)([^a-z]|$)/i;
    var MUSIC_WORDS = /(music|bgm|song|track|beat|score|ost|instrumental|melody|loop)/i;

    C.ext = function (path) {
        var m = /\.([A-Za-z0-9]+)$/.exec(String(path || ''));
        return m ? m[1].toLowerCase() : '';
    };

    C.category = function (item, ctx) {
        ctx = ctx || {};
        if (item.isSequence) { return ctx.nestIds && ctx.nestIds[item.nodeId] ? 'nests' : 'sequences'; }
        if (!item.path) { return 'graphics'; }
        var e = C.ext(item.path), name = item.name || '';
        if (has(VIDEO, e)) {
            if (item.kind === 'camera') { return 'footage'; }
            return SFX_VIDEO.test(name) ? 'sfx' : 'renders';
        }
        if (has(IMAGE, e)) {
            if (item.icon) { return 'icons'; }
            return e === 'png' ? 'png' : ((e === 'jpg' || e === 'jpeg') ? 'jpg' : 'images');
        }
        if (has(CAPTION, e)) { return 'captions'; }
        if (has(GRAPHIC, e)) { return 'graphics'; }
        if (has(AUDIO, e)) {
            // podcast: a long recorder file is a mic, whatever its name looks like ("Host", "Guest Track")
            if (ctx.mode === 'podcast' && has(RECORDER, e) && item.duration >= C.MIC_MIN && !MUSIC_STRICT.test(name)) { return 'mics'; }
            if (SFX_WORDS.test(name)) { return 'sfx'; }
            if (MUSIC_WORDS.test(name)) { return 'music'; }
            return item.duration > 0 && item.duration <= 8 ? 'sfx' : 'voice';
        }
        return 'other';
    };

    /* the bin path for a category; podcast footage is split per camera */
    C.binFor = function (cat, item, ctx) {
        if (cat === 'footage' && ctx && ctx.mode === 'podcast' && ctx.camNumbers && ctx.camNumbers[item.camId]) {
            return C.BINS.footage + '/Cam ' + ctx.camNumbers[item.camId];
        }
        return C.BINS[cat];
    };

    /* {camId: 1..n}: the camera with the most footage is Cam 1 */
    C.cameraNumbers = function (items) {
        var total = {}, ids = [], i, it, out = {};
        for (i = 0; i < items.length; i++) {
            it = items[i];
            if (it.kind !== 'camera' || !it.camId) { continue; }
            if (!total.hasOwnProperty(it.camId)) { total[it.camId] = 0; ids.push(it.camId); }
            total[it.camId] += it.duration || 0;
        }
        ids.sort(function (a, b) { return total[b] - total[a] || (a < b ? -1 : (a > b ? 1 : 0)); });
        for (i = 0; i < ids.length; i++) { out[ids[i]] = i + 1; }
        return out;
    };

    root.TidyClassify = C;
    if (typeof module === 'object' && module.exports) { module.exports = C; }
})(typeof window !== 'undefined' ? window : this);
