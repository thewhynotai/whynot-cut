// SPDX-License-Identifier: GPL-3.0-or-later
// © 2026 The Why Not AI (thewhynot.ai)
// Extracted unchanged from the owner's Hush main.js:166-180 and :198 (currentSettings, syncAdvFromSimple, readout); see adobe/tools/README.md.
/* Hush - which detection settings are in force (pure). The panel keeps cfg = {tab, intensity, tight, adv} and the clip
   stats {floor, speech}; these functions are the panel's own rules, moved out of the UI file so they can be tested. */
(function (root) {
    'use strict';
    var S = {};

    function detect() { return root.HushDetect || require('./detect.js'); }

    /* Simple tab with clip stats: the intensity mapped to settings; Tight (default on) cuts right up to speech, pads 0.
       Anything else (Advanced tab, or no stats yet): the Advanced settings as they are. */
    S.current = function (cfg, stats) {
        if (cfg.tab === 'simple' && stats) {
            var st = detect().fromIntensity(cfg.intensity, stats);
            if (cfg.tight) { st.padBefore = 0; st.padAfter = 0; }
            return st;
        }
        return cfg.adv;
    };

    /* the Advanced fields as Simple would set them (same Tight rule); null when there are no stats to sync from */
    S.advFromSimple = function (cfg, stats) {
        if (!stats) { return null; }
        var s = detect().fromIntensity(cfg.intensity, stats);
        if (cfg.tight) { s.padBefore = 0; s.padAfter = 0; }
        return { threshold: s.threshold, minSilence: s.minSilence, padBefore: s.padBefore, padAfter: s.padAfter };
    };

    /* the one-line summary under the Simple controls */
    S.readout = function (st) {
        return st.threshold + ' dB  |  ' + Math.round(st.minSilence * 1000) + ' ms min  |  ' +
            Math.round(st.padBefore * 1000) + '/' + Math.round(st.padAfter * 1000) + ' ms pad';
    };

    root.HushSettings = S;
    if (typeof module === 'object' && module.exports) { module.exports = S; }
})(typeof window !== 'undefined' ? window : this);
