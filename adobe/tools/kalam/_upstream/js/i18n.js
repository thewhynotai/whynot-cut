/* Kalam - UI strings (English / Arabic) */
(function (root) {
    'use strict';
    var T = {
        en: {
            saveReport: 'Save a report for the developer', reportSaving: 'Preparing the report...', reportSaved: 'Report saved: {p}', openLogs: 'Open logs folder', openFolder: 'Open Kalam folder', resetSettings: 'Reset settings',
            mode: 'Language mode', modeAr: 'Arabic', modeEn: 'English', modeOther: 'Other',
            modelAr: 'Egyptian-Arabic Whisper Turbo + word alignment', modelEn: 'NVIDIA Parakeet v2 + word alignment',
            modelOther: 'Whisper Large V3 Turbo (auto language) + word alignment',
            rangeLabel: 'Work on', rInOut: 'In/Out', rSequence: 'Sequence', rPlayhead: 'From playhead', rSelection: 'Selected clips', fromPlayhead: 'From playhead', noInOut: 'Set In and Out points on the sequence first', noSelection: 'Select clips in the timeline first', playheadAtEnd: 'Move the playhead before the end of the sequence', target: 'Target:', wholeSeq: 'Whole sequence', inOut: 'In/Out', clips: '{n} selected clip(s)',
            output: 'Create captions as', outTrack: 'Captions track', outMogrt: 'MOGRT', outSrt: 'SRT only',
            pickMogrt: 'Click to choose a template', videoTrack: 'Track', textField: 'Text', gSearch: 'Search templates', gAll: 'All folders', gFromFile: 'From a file...', gCount: '{n} templates', gLoading: 'Reading your templates...', gAuto: 'First text field', gNone: 'No template chosen',
            srtAlways: 'An SRT file is always saved next to the project.',
            captionSettings: 'Caption settings', maxLine: 'Characters per line', maxLines: 'Lines per caption',
            maxDur: 'Max seconds per caption', minPause: 'Pause that splits a phrase (s)',
            correctOn: 'Correct the text with Claude (your rules)', backendSub: 'My Claude subscription', backendApi: 'API key', backendSubHelp: 'Uses Claude Code with your Claude plan. No API key and no extra cost.', backendApiHelp: 'Paid per use from console.anthropic.com.', ccMissing: 'Claude Code is not installed or not logged in: captions were made without correction.', apiKey: 'Anthropic API key',
            rules: 'Correction rules', rulesReset: 'Reset to default rules', glossary: 'Glossary (your terms)',
            glossaryHelp: 'One term per line: Correct = wrong variant, other variant',
            go: 'MAKE CAPTIONS', stop: 'Stop', undo: 'Undo', reveal: 'Show SRT in Finder',
            exporting: 'Exporting audio...', loading: 'Loading...', transcribing: 'Transcribing...',
            aligning: 'Aligning every word to the voice...', correcting: 'Correcting with your rules...',
            captions: 'Building captions...', placing: 'Placing captions in Premiere...',
            done: '{n} captions', corrected: 'corrected by your rules', notCorrected: 'not corrected',
            noKey: 'No API key: captions were made without correction.', offline: 'Correction failed ({e}); captions were made without it.',
            needAudio: 'Tick at least one audio track', needMogrt: 'Choose a .mogrt first', noSequence: 'Open a sequence in the timeline first',
            setupMissing: 'Kalam engine is not installed. Run install_kalam.sh.', cancelled: 'Stopped',
            undoTrack: 'To remove the captions track use Edit > Undo in Premiere.', undone: 'Removed {n} caption clips',
            settingsReset: 'Settings reset'
        },
        ar: {
            saveReport: '\u062d\u0641\u0638 \u062a\u0642\u0631\u064a\u0631 \u0644\u0644\u0645\u0637\u0648\u0631', reportSaving: '\u062c\u0627\u0631\u064a \u062a\u062c\u0647\u064a\u0632 \u0627\u0644\u062a\u0642\u0631\u064a\u0631...', reportSaved: '\u0627\u0644\u062a\u0642\u0631\u064a\u0631 \u0627\u062a\u062d\u0641\u0638: {p}', openLogs: '\u0641\u062a\u062d \u0645\u062c\u0644\u062f \u0627\u0644\u0633\u062c\u0644\u0627\u062a', openFolder: '\u0641\u062a\u062d \u0645\u062c\u0644\u062f Kalam', resetSettings: '\u0625\u0639\u0627\u062f\u0629 \u0636\u0628\u0637 \u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a',
            mode: '\u0627\u0644\u0644\u063a\u0629', modeAr: '\u0639\u0631\u0628\u064a', modeEn: '\u0625\u0646\u062c\u0644\u064a\u0632\u064a', modeOther: '\u0644\u063a\u0629 \u0623\u062e\u0631\u0649',
            modelAr: 'Whisper Turbo \u0627\u0644\u0645\u0635\u0631\u064a + \u0645\u062d\u0627\u0630\u0627\u0629 \u0643\u0644 \u0643\u0644\u0645\u0629', modelEn: 'Parakeet v2 \u0645\u0646 NVIDIA + \u0645\u062d\u0627\u0630\u0627\u0629 \u0643\u0644 \u0643\u0644\u0645\u0629',
            modelOther: 'Whisper Large V3 Turbo (\u064a\u062a\u0639\u0631\u0641 \u0639\u0644\u0649 \u0627\u0644\u0644\u063a\u0629) + \u0645\u062d\u0627\u0630\u0627\u0629 \u0643\u0644 \u0643\u0644\u0645\u0629',
            rangeLabel: '\u064a\u0634\u062a\u063a\u0644 \u0639\u0644\u0649', rInOut: 'In/Out', rSequence: '\u0627\u0644\u0633\u064a\u0643\u0648\u0646\u0633 \u0643\u0644\u0647', rPlayhead: '\u0645\u0646 \u0627\u0644\u0640 Playhead', rSelection: '\u0627\u0644\u0643\u0644\u064a\u0628\u0627\u062a \u0627\u0644\u0645\u062d\u062f\u062f\u0629', fromPlayhead: '\u0645\u0646 \u0627\u0644\u0640 Playhead', noInOut: '\u062d\u0637 In \u0648 Out \u0639\u0644\u0649 \u0627\u0644\u0633\u064a\u0643\u0648\u0646\u0633 \u0627\u0644\u0623\u0648\u0644', noSelection: '\u062d\u062f\u062f \u0643\u0644\u064a\u0628\u0627\u062a \u0641\u064a \u0627\u0644\u062a\u0627\u064a\u0645\u0644\u0627\u064a\u0646 \u0627\u0644\u0623\u0648\u0644', playheadAtEnd: '\u0631\u062c\u0651\u0639 \u0627\u0644\u0640 Playhead \u0642\u0628\u0644 \u0622\u062e\u0631 \u0627\u0644\u0633\u064a\u0643\u0648\u0646\u0633', target: '\u0627\u0644\u0647\u062f\u0641:', wholeSeq: '\u0627\u0644\u062a\u0633\u0644\u0633\u0644 \u0643\u0644\u0647', inOut: '\u0645\u0646 In \u0625\u0644\u0649 Out', clips: '{n} \u0645\u0642\u0637\u0639 \u0645\u062d\u062f\u062f',
            output: '\u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u064a\u0646\u0632\u0644 \u0643\u0640', outTrack: '\u062a\u0631\u0627\u0643 \u0643\u0627\u0628\u0634\u0646', outMogrt: 'MOGRT', outSrt: 'SRT \u0628\u0633',
            pickMogrt: '\u062f\u0648\u0633 \u0647\u0646\u0627 \u0648\u0627\u062e\u062a\u0627\u0631 \u0627\u0644\u0645\u0648\u062c\u0631\u062f', videoTrack: '\u0627\u0644\u062a\u0631\u0627\u0643', textField: '\u0627\u0644\u0643\u0644\u0627\u0645', gSearch: '\u062f\u0648\u0651\u0631 \u0639\u0644\u0649 \u0645\u0648\u062c\u0631\u062f', gAll: '\u0643\u0644 \u0627\u0644\u0641\u0648\u0644\u062f\u0631\u0627\u062a', gFromFile: '\u0645\u0646 \u0645\u0644\u0641...', gCount: '{n} \u0645\u0648\u062c\u0631\u062f', gLoading: '\u0628\u0642\u0631\u0627 \u0627\u0644\u0645\u0648\u062c\u0631\u062f\u0627\u062a \u0628\u062a\u0627\u0639\u062a\u0643...', gAuto: '\u0623\u0648\u0644 \u062e\u0627\u0646\u0629 \u0643\u0644\u0627\u0645', gNone: '\u0644\u0633\u0647 \u0645\u0627 \u0627\u062e\u062a\u0631\u062a\u0634 \u0645\u0648\u062c\u0631\u062f',
            srtAlways: '\u0645\u0644\u0641 SRT \u0628\u064a\u062a\u062d\u0641\u0638 \u062f\u0627\u064a\u0645\u064b\u0627 \u062c\u0646\u0628 \u0627\u0644\u0645\u0634\u0631\u0648\u0639.',
            captionSettings: '\u0625\u0639\u062f\u0627\u062f\u0627\u062a \u0627\u0644\u0643\u0627\u0628\u0634\u0646', maxLine: '\u0639\u062f\u062f \u0627\u0644\u062d\u0631\u0648\u0641 \u0641\u064a \u0627\u0644\u0633\u0637\u0631', maxLines: '\u0639\u062f\u062f \u0627\u0644\u0633\u0637\u0648\u0631',
            maxDur: '\u0623\u0642\u0635\u0649 \u0645\u062f\u0629 \u0644\u0644\u0643\u0627\u0628\u0634\u0646 (\u062b\u0627\u0646\u064a\u0629)', minPause: '\u0627\u0644\u0648\u0642\u0641\u0629 \u0627\u0644\u0644\u064a \u0628\u062a\u0641\u0635\u0644 \u0627\u0644\u062c\u0645\u0644\u0629 (\u062b\u0627\u0646\u064a\u0629)',
            backendSub: '\u0627\u0634\u062a\u0631\u0627\u0643 Claude \u0628\u062a\u0627\u0639\u064a', backendApi: '\u0645\u0641\u062a\u0627\u062d API', backendSubHelp: '\u0628\u064a\u0633\u062a\u062e\u062f\u0645 Claude Code \u0628\u0627\u0634\u062a\u0631\u0627\u0643\u0643 \u0641\u064a Claude. \u0645\u0646 \u063a\u064a\u0631 \u0645\u0641\u062a\u0627\u062d \u0648\u0645\u0646 \u063a\u064a\u0631 \u0641\u0644\u0648\u0633 \u0632\u064a\u0627\u062f\u0629.', backendApiHelp: '\u0628\u0627\u0644\u062f\u0641\u0639 \u062d\u0633\u0628 \u0627\u0644\u0627\u0633\u062a\u062e\u062f\u0627\u0645 \u0645\u0646 console.anthropic.com.', ccMissing: 'Claude Code \u0645\u0634 \u0645\u062a\u0633\u0637\u0628 \u0623\u0648 \u0645\u0634 \u0639\u0627\u0645\u0644 \u062a\u0633\u062c\u064a\u0644 \u062f\u062e\u0648\u0644: \u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u0627\u062a\u0639\u0645\u0644 \u0645\u0646 \u063a\u064a\u0631 \u062a\u0635\u062d\u064a\u062d.', correctOn: '\u0635\u062d\u062d \u0627\u0644\u0646\u0635 \u0628\u0640 Claude (\u0628\u0642\u0648\u0627\u0639\u062f\u0643)', apiKey: '\u0645\u0641\u062a\u0627\u062d Anthropic API',
            rules: '\u0642\u0648\u0627\u0639\u062f \u0627\u0644\u062a\u0635\u062d\u064a\u062d', rulesReset: '\u0631\u062c\u0651\u0639 \u0627\u0644\u0642\u0648\u0627\u0639\u062f \u0627\u0644\u0623\u0635\u0644\u064a\u0629', glossary: '\u0627\u0644\u0645\u0635\u0637\u0644\u062d\u0627\u062a (\u0642\u0627\u0645\u0648\u0633\u0643)',
            glossaryHelp: '\u0643\u0644 \u0645\u0635\u0637\u0644\u062d \u0641\u064a \u0633\u0637\u0631: \u0627\u0644\u0635\u062d = \u0627\u0644\u0634\u0643\u0644 \u0627\u0644\u063a\u0644\u0637\u060c \u0634\u0643\u0644 \u062a\u0627\u0646\u064a',
            go: '\u0627\u0639\u0645\u0644 \u0627\u0644\u0643\u0627\u0628\u0634\u0646', stop: '\u0625\u064a\u0642\u0627\u0641', undo: '\u062a\u0631\u0627\u062c\u0639', reveal: '\u0627\u0641\u062a\u062d \u0645\u0644\u0641 SRT',
            exporting: '\u062c\u0627\u0631\u064a \u062a\u0635\u062f\u064a\u0631 \u0627\u0644\u0635\u0648\u062a...', loading: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u062d\u0645\u064a\u0644...', transcribing: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u0641\u0631\u064a\u063a...',
            aligning: '\u062c\u0627\u0631\u064a \u0636\u0628\u0637 \u0643\u0644 \u0643\u0644\u0645\u0629 \u0639\u0644\u0649 \u0627\u0644\u0635\u0648\u062a...', correcting: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u0635\u062d\u064a\u062d \u0628\u0642\u0648\u0627\u0639\u062f\u0643...',
            captions: '\u062c\u0627\u0631\u064a \u062a\u0642\u0633\u064a\u0645 \u0627\u0644\u0643\u0627\u0628\u0634\u0646...', placing: '\u062c\u0627\u0631\u064a \u0625\u0646\u0632\u0627\u0644 \u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u0641\u064a Premiere...',
            done: '{n} \u0643\u0627\u0628\u0634\u0646', corrected: '\u0645\u062a\u0635\u062d\u062d \u0628\u0642\u0648\u0627\u0639\u062f\u0643', notCorrected: '\u0645\u0646 \u063a\u064a\u0631 \u062a\u0635\u062d\u064a\u062d',
            noKey: '\u0645\u0641\u064a\u0634 \u0645\u0641\u062a\u0627\u062d API: \u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u0627\u062a\u0639\u0645\u0644 \u0645\u0646 \u063a\u064a\u0631 \u062a\u0635\u062d\u064a\u062d.', offline: '\u0627\u0644\u062a\u0635\u062d\u064a\u062d \u0641\u0634\u0644 ({e})\u060c \u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u0627\u062a\u0639\u0645\u0644 \u0645\u0646 \u063a\u064a\u0631\u0647.',
            needAudio: '\u0627\u062e\u062a\u0627\u0631 \u062a\u0631\u0627\u0643 \u0635\u0648\u062a \u0648\u0627\u062d\u062f \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644', needMogrt: '\u0627\u062e\u062a\u0627\u0631 \u0645\u0644\u0641 .mogrt \u0627\u0644\u0623\u0648\u0644', noSequence: '\u0627\u0641\u062a\u062d \u062a\u0633\u0644\u0633\u0644 \u0641\u064a \u0627\u0644\u062a\u0627\u064a\u0645\u0644\u0627\u064a\u0646 \u0627\u0644\u0623\u0648\u0644',
            setupMissing: '\u0645\u062d\u0631\u0643 Kalam \u0645\u0634 \u0645\u062a\u0633\u0637\u0628. \u0634\u063a\u0651\u0644 install_kalam.sh', cancelled: '\u0627\u062a\u0648\u0642\u0641',
            undoTrack: '\u0639\u0634\u0627\u0646 \u062a\u0634\u064a\u0644 \u062a\u0631\u0627\u0643 \u0627\u0644\u0643\u0627\u0628\u0634\u0646 \u0627\u0633\u062a\u062e\u062f\u0645 Edit > Undo \u0641\u064a Premiere.', undone: '\u0627\u062a\u0634\u0627\u0644 {n} \u0643\u0627\u0628\u0634\u0646',
            settingsReset: '\u062a\u0645\u062a \u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0636\u0628\u0637'
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
    root.KalamI18n = I;
})(window);
