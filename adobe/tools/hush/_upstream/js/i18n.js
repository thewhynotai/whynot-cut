/* Hush - UI strings (English / Arabic) */
(function (root) {
    'use strict';
    var T = {
        en: {
            clearMarkers: 'Remove all Hush markers', openLogs: 'Open logs folder', resetSettings: 'Reset settings',
            ripple: 'Close gaps after cut', tight: 'Tight cut (no margin around speech)', link: 'Keep audio linked to video', backup: 'Keep a backup copy of the sequence',
            target: 'Target:', scan: 'SCAN', simple: 'Simple', advanced: 'Advanced',
            soft: 'Soft', medium: 'Medium', strong: 'Strong',
            threshold: 'Silence below', minSilence: 'Min. silence', padBefore: 'Keep before speech', padAfter: 'Keep after speech',
            linkPads: 'Link before/after', presetName: 'Preset name', save: 'Save', presetDefault: '- presets -',
            fillersOn: 'Remove filler words (um, uh, \u0627\u0645\u0645\u0645...)', speechLang: 'Speech', auto: 'Auto detect',
            sounds: 'Unclear sounds', editLists: 'Edit filler lists',
            strongList: 'Cut by default (ticked)', softList: 'Ask first (unticked)',
            wavePlaceholder: 'Select clips (or nothing = whole sequence), then Scan',
            before: 'Before', after: 'After', saved: 'Removed',
            modeCut: 'Cut', modeMarkers: 'Markers only', goCut: 'CUT', goMarkers: 'ADD MARKERS',
            stop: 'Stop', undo: 'Undo (restore backup)',
            wholeSeq: 'Whole sequence', inOut: 'In/Out', clips: '{n} selected clip(s)',
            exporting: 'Exporting audio from Premiere...', analyzing: 'Analysing...', loadingModel: 'Loading Whisper...',
            transcribing: 'Finding filler words...', ready: 'Ready: {n} cuts', cutting: 'Cutting {n} pieces...',
            cutDone: 'Done: {n} cuts, {t} removed', markersDone: '{n} markers added', markersCleared: '{n} Hush markers removed',
            noScan: 'Scan first', needAudio: 'Tick at least one audio track', cancelled: 'Stopped',
            undone: 'Restored "{name}" (the cut version was kept and renamed)', noBackup: 'No backup for this cut - use Edit > Undo in Premiere',
            whisperMissing: 'Whisper is not installed. Run install.sh again.', rescan: 'Timeline changed - scan again to continue',
            trackWarn: 'Not ticked, will not move: {t}', noFillers: 'No filler words found',
            cutsN: '{s} silences + {f} fillers', presetSaved: 'Preset saved', settingsReset: 'Settings reset',
            noSequence: 'Open a sequence in the timeline first'
        },
        ar: {
            clearMarkers: '\u062d\u0630\u0641 \u0643\u0644 \u0639\u0644\u0627\u0645\u0627\u062a Hush', openLogs: '\u0641\u062a\u062d \u0645\u062c\u0644\u062f \u0627\u0644\u0633\u062c\u0644\u0627\u062a', resetSettings: '\u0625\u0639\u0627\u062f\u0629 \u0636\u0628\u0637 \u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a',
            ripple: '\u0625\u063a\u0644\u0627\u0642 \u0627\u0644\u0641\u0631\u0627\u063a\u0627\u062a \u0628\u0639\u062f \u0627\u0644\u0642\u0635', link: '\u0625\u0628\u0642\u0627\u0621 \u0627\u0644\u0635\u0648\u062a \u0645\u0631\u0628\u0648\u0637\u064b\u0627 \u0628\u0627\u0644\u0635\u0648\u0631\u0629', tight: '\u0642\u0635 \u0644\u0627\u0632\u0642 (\u0628\u062f\u0648\u0646 \u0647\u0627\u0645\u0634 \u062d\u0648\u0627\u0644\u064a\u0646 \u0627\u0644\u0643\u0644\u0627\u0645)', backup: '\u0627\u0644\u0627\u062d\u062a\u0641\u0627\u0638 \u0628\u0646\u0633\u062e\u0629 \u0627\u062d\u062a\u064a\u0627\u0637\u064a\u0629 \u0645\u0646 \u0627\u0644\u062a\u0633\u0644\u0633\u0644',
            target: '\u0627\u0644\u0647\u062f\u0641:', scan: '\u0641\u062d\u0635', simple: '\u0628\u0633\u064a\u0637', advanced: '\u0645\u062a\u0642\u062f\u0645',
            soft: '\u062e\u0641\u064a\u0641', medium: '\u0645\u062a\u0648\u0633\u0637', strong: '\u0642\u0648\u064a',
            threshold: '\u0627\u0644\u0635\u0645\u062a \u0623\u0642\u0644 \u0645\u0646', minSilence: '\u0623\u0642\u0644 \u0645\u062f\u0629 \u0635\u0645\u062a', padBefore: '\u0647\u0627\u0645\u0634 \u0642\u0628\u0644 \u0627\u0644\u0643\u0644\u0627\u0645', padAfter: '\u0647\u0627\u0645\u0634 \u0628\u0639\u062f \u0627\u0644\u0643\u0644\u0627\u0645',
            linkPads: '\u0631\u0628\u0637 \u0642\u0628\u0644/\u0628\u0639\u062f', presetName: '\u0627\u0633\u0645 \u0627\u0644\u0625\u0639\u062f\u0627\u062f', save: '\u062d\u0641\u0638', presetDefault: '- \u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0645\u062d\u0641\u0648\u0638\u0629 -',
            fillersOn: '\u062d\u0630\u0641 \u0643\u0644\u0645\u0627\u062a \u0627\u0644\u062d\u0634\u0648 (\u0627\u0645\u0645\u0645\u060c \u0622\u0647\u060c um...)', speechLang: '\u0627\u0644\u0644\u063a\u0629', auto: '\u062a\u0644\u0642\u0627\u0626\u064a',
            sounds: '\u0623\u0635\u0648\u0627\u062a \u063a\u064a\u0631 \u0648\u0627\u0636\u062d\u0629', editLists: '\u062a\u0639\u062f\u064a\u0644 \u0642\u0648\u0627\u0626\u0645 \u0627\u0644\u062d\u0634\u0648',
            strongList: '\u062a\u064f\u062d\u0630\u0641 \u062a\u0644\u0642\u0627\u0626\u064a\u064b\u0627', softList: '\u062a\u064f\u0639\u0631\u0636 \u0623\u0648\u0644\u064b\u0627 (\u063a\u064a\u0631 \u0645\u062d\u062f\u062f\u0629)',
            wavePlaceholder: '\u062d\u062f\u0651\u062f \u0627\u0644\u0645\u0642\u0627\u0637\u0639 (\u0623\u0648 \u0644\u0627 \u0634\u064a\u0621 = \u0627\u0644\u062a\u0633\u0644\u0633\u0644 \u0643\u0644\u0647) \u062b\u0645 \u0627\u0636\u063a\u0637 \u0641\u062d\u0635',
            before: '\u0642\u0628\u0644', after: '\u0628\u0639\u062f', saved: '\u0627\u0644\u0645\u062d\u0630\u0648\u0641',
            modeCut: '\u0642\u0635', modeMarkers: '\u0639\u0644\u0627\u0645\u0627\u062a \u0641\u0642\u0637', goCut: '\u0642\u0635', goMarkers: '\u0625\u0636\u0627\u0641\u0629 \u0639\u0644\u0627\u0645\u0627\u062a',
            stop: '\u0625\u064a\u0642\u0627\u0641', undo: '\u062a\u0631\u0627\u062c\u0639 (\u0627\u0633\u062a\u0639\u0627\u062f\u0629 \u0627\u0644\u0646\u0633\u062e\u0629)',
            wholeSeq: '\u0627\u0644\u062a\u0633\u0644\u0633\u0644 \u0643\u0644\u0647', inOut: '\u0645\u0646 In \u0625\u0644\u0649 Out', clips: '{n} \u0645\u0642\u0637\u0639 \u0645\u062d\u062f\u062f',
            exporting: '\u062c\u0627\u0631\u064d \u062a\u0635\u062f\u064a\u0631 \u0627\u0644\u0635\u0648\u062a...', analyzing: '\u062c\u0627\u0631\u064d \u0627\u0644\u062a\u062d\u0644\u064a\u0644...', loadingModel: '\u062a\u062d\u0645\u064a\u0644 Whisper...',
            transcribing: '\u0627\u0644\u0628\u062d\u062b \u0639\u0646 \u0643\u0644\u0645\u0627\u062a \u0627\u0644\u062d\u0634\u0648...', ready: '\u062c\u0627\u0647\u0632: {n} \u0642\u0635\u0629', cutting: '\u062c\u0627\u0631\u064d \u0642\u0635 {n} \u062c\u0632\u0621...',
            cutDone: '\u062a\u0645: {n} \u0642\u0635\u0629\u060c \u062d\u064f\u0630\u0641 {t}', markersDone: '\u0623\u064f\u0636\u064a\u0641\u062a {n} \u0639\u0644\u0627\u0645\u0629', markersCleared: '\u062d\u064f\u0630\u0641\u062a {n} \u0639\u0644\u0627\u0645\u0629',
            noScan: '\u0627\u0636\u063a\u0637 \u0641\u062d\u0635 \u0623\u0648\u0644\u064b\u0627', needAudio: '\u0627\u062e\u062a\u0631 \u0645\u0633\u0627\u0631 \u0635\u0648\u062a \u0648\u0627\u062d\u062f\u064b\u0627 \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644', cancelled: '\u062a\u0645 \u0627\u0644\u0625\u064a\u0642\u0627\u0641',
            undone: '\u062a\u0645\u062a \u0627\u0633\u062a\u0639\u0627\u062f\u0629 "{name}" (\u0627\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0645\u0642\u0635\u0648\u0635\u0629 \u0645\u062d\u0641\u0648\u0638\u0629 \u0628\u0627\u0633\u0645 \u062c\u062f\u064a\u062f)', noBackup: '\u0644\u0627 \u062a\u0648\u062c\u062f \u0646\u0633\u062e\u0629 - \u0627\u0633\u062a\u062e\u062f\u0645 Edit > Undo',
            whisperMissing: 'Whisper \u063a\u064a\u0631 \u0645\u062b\u0628\u062a. \u0634\u063a\u0651\u0644 install.sh \u0645\u0631\u0629 \u0623\u062e\u0631\u0649.', rescan: '\u062a\u063a\u064a\u0651\u0631 \u0627\u0644\u062a\u0633\u0644\u0633\u0644 - \u0627\u0641\u062d\u0635 \u0645\u0646 \u062c\u062f\u064a\u062f',
            trackWarn: '\u063a\u064a\u0631 \u0645\u062d\u062f\u062f\u0629 \u0648\u0644\u0646 \u062a\u062a\u062d\u0631\u0643: {t}', noFillers: '\u0644\u0627 \u062a\u0648\u062c\u062f \u0643\u0644\u0645\u0627\u062a \u062d\u0634\u0648',
            cutsN: '{s} \u0635\u0645\u062a + {f} \u062d\u0634\u0648', presetSaved: '\u062a\u0645 \u062d\u0641\u0638 \u0627\u0644\u0625\u0639\u062f\u0627\u062f', settingsReset: '\u062a\u0645\u062a \u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0636\u0628\u0637',
            noSequence: '\u0627\u0641\u062a\u062d \u062a\u0633\u0644\u0633\u0644\u064b\u0627 \u0641\u064a \u0627\u0644\u062e\u0637 \u0627\u0644\u0632\u0645\u0646\u064a \u0623\u0648\u0644\u064b\u0627'
        }
    };
    var I = { lang: 'en' };
    I.t = function (key, vars) {
        var s = (T[I.lang] && T[I.lang][key]) || T.en[key] || key, k;
        for (k in vars || {}) { if (vars.hasOwnProperty(k)) { s = s.split('{' + k + '}').join(vars[k]); } }
        return s;
    };
    I.apply = function (lang) {
        I.lang = lang === 'ar' ? 'ar' : 'en';
        document.documentElement.lang = I.lang;
        document.documentElement.dir = I.lang === 'ar' ? 'rtl' : 'ltr';
        var els = document.querySelectorAll('[data-i18n]'), i;
        for (i = 0; i < els.length; i++) { els[i].textContent = I.t(els[i].getAttribute('data-i18n')); }
        els = document.querySelectorAll('[data-i18n-ph]');
        for (i = 0; i < els.length; i++) { els[i].placeholder = I.t(els[i].getAttribute('data-i18n-ph')); }
    };
    root.HushI18n = I;
})(window);
