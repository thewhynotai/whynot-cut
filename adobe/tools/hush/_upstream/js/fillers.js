/* Hush - filler-word matching (pure). Words come from Whisper: [{w, s, e, p}] in range seconds. */
(function (root) {
    'use strict';
    var F = {};

    // "strong" fillers are ticked by default; "soft" ones are listed but left unticked (they are often real words)
    F.DEFAULT_STRONG = 'um, umm, uh, uhh, uhm, erm, er, ah, ahh, hmm, hm, mm, mmm, mhm, ' +
        '\u0627\u0645\u0645, \u0627\u0645\u0645\u0645, \u0645\u0645\u0645, \u0645\u0645, \u0622\u0647, \u0627\u0627\u0647, \u0627\u0627\u0627\u0647, \u0647\u0645\u0645\u0645, \u0647\u0645\u0645, \u0627\u0648\u0647';
    F.DEFAULT_SOFT = 'like, you know, basically, actually, i mean, \u064a\u0639\u0646\u064a, \u0637\u064a\u0628, \u0627\u0635\u0644\u0627, \u0628\u0642\u0649, \u0627\u0645, \u0627\u064a\u0647';

    /* lower-case, strip punctuation, Arabic diacritics/tatweel, unify alef/yeh/heh forms */
    F.norm = function (w) {
        return String(w).toLowerCase()
            .replace(/[\u064b-\u065f\u0670\u0640]/g, '')          // harakat, dagger alef, tatweel
            .replace(/[\u0622\u0623\u0625\u0671]/g, '\u0627')     // alef forms -> bare alef
            .replace(/\u0649/g, '\u064a')                          // alef maqsura -> yeh
            .replace(/[.,!?;:"'`\u2019\u201c\u201d()\[\]\u060c\u061b\u061f\u2026\---]/g, '')
            .replace(/\s+/g, ' ').trim();
    };

    F.parseList = function (text) {
        var out = [], parts = String(text || '').split(/[,\n\u060c]+/), i, n;
        for (i = 0; i < parts.length; i++) { n = F.norm(parts[i]); if (n) { out.push(n); } }
        return out;
    };

    /* elongated hesitations whatever their length: ummmm, hmmmm, aaah, \u0627\u0645\u0645\u0645\u0645\u0645, \u0622\u0622\u0622\u0647 */
    F.isHesitation = function (n) {
        return /^(u+h*m+|u+h+|e+r+m*|a+h+|h+m+|m{2,}|m+h+m+)$/.test(n) ||
               /^(\u0627+\u0645{2,}|\u0645{2,}|\u0627{2,}\u0647+|\u0627*\u0647+\u0645{2,}|\u0627+\u0648+\u0647+)$/.test(n);
    };

    /* match single words and two-word phrases ("you know", "i mean") against the lists */
    F.find = function (words, strongText, softText) {
        var strong = F.parseList(strongText), soft = F.parseList(softText), out = [], i, n, n2, hit;
        function has(list, x) { for (var k = 0; k < list.length; k++) { if (list[k] === x) { return true; } } return false; }
        for (i = 0; i < words.length; i++) {
            n = F.norm(words[i].w);
            if (!n) { continue; }
            n2 = i + 1 < words.length ? n + ' ' + F.norm(words[i + 1].w) : null;
            hit = null;
            if (n2 && has(strong, n2)) { hit = { strong: true, n: 2 }; }
            else if (n2 && has(soft, n2)) { hit = { strong: false, n: 2 }; }
            else if (has(strong, n) || F.isHesitation(n)) { hit = { strong: true, n: 1 }; }
            else if (has(soft, n)) { hit = { strong: false, n: 1 }; }
            if (hit) {
                var last = words[i + hit.n - 1];
                out.push({ s: words[i].s, e: last.e, label: hit.n === 2 ? words[i].w + ' ' + last.w : words[i].w,
                           kind: 'filler', on: hit.strong, source: 'word' });
                i += hit.n - 1;
            }
        }
        return out;
    };

    /* sound Whisper did not turn into words (often a filler it skipped): loud runs >= minLen with no word on them */
    F.untranscribed = function (env, hop, threshold, words, minLen, maxLen) {
        var out = [], i, start = -1, covered = new Uint8Array(env.length), k, a, b;
        for (k = 0; k < words.length; k++) {
            a = Math.max(0, Math.floor(words[k].s / hop) - 15); b = Math.min(env.length, Math.ceil(words[k].e / hop) + 15);
            for (i = a; i < b; i++) { covered[i] = 1; }
        }
        for (i = 0; i <= env.length; i++) {
            var loud = i < env.length && env[i] >= threshold && !covered[i];
            if (loud && start < 0) { start = i; }
            if (!loud && start >= 0) {
                var len = (i - start) * hop;
                if (len >= minLen && len <= maxLen) {
                    out.push({ s: start * hop, e: i * hop, label: '(sound)', kind: 'filler', on: false, source: 'sound' });
                }
                start = -1;
            }
        }
        return out;
    };

    root.HushFillers = F;
})(typeof window !== 'undefined' ? window : this);
