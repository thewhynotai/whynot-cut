/* Tidy - UI strings (Arabic / English) */
(function (root) {
    'use strict';
    var T = {
        ar: {
            openLogs: '\u0641\u062a\u062d \u0645\u062c\u0644\u062f \u0627\u0644\u0633\u062c\u0644\u0627\u062a', openFolder: '\u0641\u062a\u062d \u0645\u062c\u0644\u062f Tidy', project: '\u0627\u0644\u0645\u0634\u0631\u0648\u0639', scan: '\u0627\u0641\u062d\u0635 \u0627\u0644\u0645\u0634\u0631\u0648\u0639',
            stItems: '\u0639\u0646\u0635\u0631', stSize: '\u062d\u062c\u0645 \u0627\u0644\u0645\u0644\u0641\u0627\u062a', stRemove: '\u0647\u064a\u062a\u0634\u0627\u0644 \u0645\u0646 \u0627\u0644\u0645\u0634\u0631\u0648\u0639', stFree: '\u0645\u0646 \u062d\u062c\u0645 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0645\u0634 \u0645\u0633\u062a\u062e\u062f\u0645',
            optRemove: '\u0634\u064a\u0644 \u0627\u0644\u062d\u0627\u062c\u0627\u062a \u0627\u0644\u0644\u064a \u0639\u0644\u064a\u0647\u0627 \u0639\u0644\u0627\u0645\u0629', optOrganize: '\u0646\u0638\u0651\u0645 \u0641\u064a \u0641\u0648\u0644\u062f\u0631\u0627\u062a \u062d\u0633\u0628 \u0627\u0644\u0646\u0648\u0639', optColors: '\u0644\u0648\u0651\u0646 \u0643\u0644 \u0646\u0648\u0639 \u0628\u0644\u0648\u0646 \u062b\u0627\u0628\u062a',
            secRemove: '\u0647\u064a\u062a\u0634\u0627\u0644 \u0645\u0646 \u0627\u0644\u0645\u0634\u0631\u0648\u0639', secMove: '\u0647\u064a\u062a\u0646\u0642\u0644 \u0644\u0641\u0648\u0644\u062f\u0631\u0647', secBins: '\u0641\u0648\u0644\u062f\u0631\u0627\u062a \u0642\u062f\u064a\u0645\u0629 \u0647\u062a\u062a\u0634\u0627\u0644', secDup: '\u0645\u0644\u0641\u0627\u062a \u0645\u0643\u0631\u0631\u0629 \u0648\u0645\u0633\u062a\u062e\u062f\u0645\u0629 (\u0644\u0644\u0639\u0644\u0645)',
            secOffline: '\u0645\u0644\u0641\u0627\u062a \u0646\u0627\u0642\u0635\u0629 \u0639\u0644\u0649 \u0627\u0644\u0647\u0627\u0631\u062f (Offline)',
            rUnused: '\u0645\u0634 \u0645\u0633\u062a\u062e\u062f\u0645 \u0641\u064a \u0623\u064a \u0633\u064a\u0643\u0648\u0646\u0633', rDuplicate: '\u0646\u0633\u062e\u0629 \u0645\u0643\u0631\u0631\u0629 \u0645\u0634 \u0645\u0633\u062a\u062e\u062f\u0645\u0629', rBackup: '\u0646\u0633\u062e\u0629 \u0627\u062d\u062a\u064a\u0627\u0637\u064a\u0629 \u0642\u062f\u064a\u0645\u0629 \u0645\u0646 Hush/Kalam',
            rCaptions: '\u0645\u0644\u0641\u0627\u062a \u0643\u0627\u0628\u0634\u0646 (\u0627\u062e\u062a\u0627\u0631 \u0628\u0646\u0641\u0633\u0643: Premiere \u0645\u0627 \u0628\u064a\u0642\u0648\u0644\u0634 \u0645\u064a\u0646 \u0645\u0633\u062a\u062e\u062f\u0645\u0647\u0627)',
            apply: '\u0646\u0638\u0651\u0641 \u0648\u0646\u0638\u0651\u0645', confirmYes: '\u0623\u064a\u0648\u0647\u060c \u0643\u0645\u0651\u0644', confirmNo: '\u0625\u0644\u063a\u0627\u0621',
            confirmText: '\u0647\u064a\u062a\u062d\u0641\u0638 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0648\u0646\u0633\u062e\u0629 \u0627\u062d\u062a\u064a\u0627\u0637\u064a\u0629 \u0645\u0646\u0647 \u062c\u0646\u0628\u0647\u060c \u0648\u0628\u0639\u062f\u064a\u0646: {r} \u0639\u0646\u0635\u0631 \u0647\u064a\u062a\u0634\u0627\u0644\u0648\u0627 \u0645\u0646 \u0627\u0644\u0645\u0634\u0631\u0648\u0639\u060c {m} \u0647\u064a\u062a\u0646\u0642\u0644\u0648\u0627\u060c \u0648{b} \u0641\u0648\u0644\u062f\u0631 \u0641\u0627\u0636\u064a \u0647\u064a\u062a\u0634\u0627\u0644. \u0627\u0644\u0645\u0644\u0641\u0627\u062a \u0639\u0644\u0649 \u0627\u0644\u0647\u0627\u0631\u062f \u0645\u0634 \u0647\u062a\u062a\u0644\u0645\u0633.',
            undo: '\u0627\u0641\u062a\u062d \u0627\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0644\u064a \u0642\u0628\u0644 \u0627\u0644\u062a\u0646\u0638\u064a\u0641', scanning: '\u062c\u0627\u0631\u064a \u0627\u0644\u0641\u062d\u0635...', applying: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u0646\u0638\u064a\u0641...',
            done: '\u062a\u0645: \u0627\u062a\u0634\u0627\u0644 {r}\u060c \u0627\u062a\u0646\u0642\u0644 {m}\u060c \u0627\u062a\u0634\u0627\u0644 {b} \u0641\u0648\u0644\u062f\u0631\u060c \u0627\u062a\u0644\u0648\u0646 {c}.', skipped: '\u0627\u062a\u0633\u0627\u0628 {s} \u0644\u0623\u0646\u0647 \u0637\u0644\u0639 \u0645\u0633\u062a\u062e\u062f\u0645.',
            backupAt: '\u0627\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0627\u062d\u062a\u064a\u0627\u0637\u064a\u0629: {p}', noProject: '\u0627\u0641\u062a\u062d \u0645\u0634\u0631\u0648\u0639 \u0627\u0644\u0623\u0648\u0644', unsaved: '\u0627\u062d\u0641\u0638 \u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0645\u0631\u0629 \u0627\u0644\u0623\u0648\u0644 (File > Save) \u0639\u0634\u0627\u0646 \u0646\u0639\u0645\u0644 \u0645\u0646\u0647 \u0646\u0633\u062e\u0629 \u0627\u062d\u062a\u064a\u0627\u0637\u064a\u0629.',
            nothing: '\u0627\u0644\u0645\u0634\u0631\u0648\u0639 \u0646\u0636\u064a\u0641 \u0648\u0645\u062a\u0646\u0638\u0645\u060c \u0645\u0641\u064a\u0634 \u062d\u0627\u062c\u0629 \u062a\u062a\u0639\u0645\u0644.', opened: '\u0627\u062a\u0641\u062a\u062d\u062a \u0627\u0644\u0646\u0633\u062e\u0629 \u0627\u0644\u0644\u064a \u0642\u0628\u0644 \u0627\u0644\u062a\u0646\u0638\u064a\u0641.',
            problems: '{n} \u062d\u0627\u062c\u0629 \u0645\u0627 \u0627\u062a\u0639\u0645\u0644\u062a\u0634 (\u0627\u0644\u062a\u0641\u0627\u0635\u064a\u0644 \u0641\u064a \u0627\u0644\u0633\u062c\u0644).',
            syncNothing: '\u0645\u0627 \u0644\u0642\u064a\u062a\u0634 \u0623\u064a \u0635\u0648\u062a \u0645\u062a\u0637\u0627\u0628\u0642 \u0623\u062d\u0637 \u0639\u0644\u064a\u0647.', sync: '\u0632\u0627\u0645\u0646 \u0627\u0644\u0628\u0648\u062f\u0643\u0627\u0633\u062a \u0628\u0627\u0644\u0635\u0648\u062a', syncNeedTwo: '\u0645\u062d\u062a\u0627\u062c \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644 \u0643\u0627\u0645\u064a\u0631\u0627 \u0648\u0645\u0627\u064a\u0643 (\u0623\u0648 \u0643\u0627\u0645\u064a\u0631\u062a\u064a\u0646) \u0639\u0634\u0627\u0646 \u0623\u0632\u0627\u0645\u0646.', syncExport: '\u0628\u0637\u0644\u0639 \u0635\u0648\u062a {i}/{n}: {name}', syncMatch: '\u0628\u0642\u0627\u0631\u0646 \u0627\u0644\u0623\u0635\u0648\u0627\u062a...', syncDone: '\u0627\u062a\u0639\u0645\u0644 {seq} \u0648\u0641\u064a\u0647 {n} \u0643\u0644\u064a\u0628 \u0645\u062a\u0632\u0627\u0645\u0646.', syncSkipped: '\u0645\u0627 \u0644\u0642\u064a\u062a\u0644\u0647\u0645\u0634 \u0645\u0643\u0627\u0646 \u0628\u0627\u0644\u0635\u0648\u062a (\u0627\u062a\u0633\u0627\u0628\u0648\u0627 \u0628\u0631\u0627): {list}', modeReels: '\u0631\u064a\u0644\u0632', modePodcast: '\u0628\u0648\u062f\u0643\u0627\u0633\u062a', modeHint: '\u0628\u0648\u062f\u0643\u0627\u0633\u062a: \u0643\u0644 \u0643\u0627\u0645\u064a\u0631\u0627 \u0641\u064a \u0641\u0648\u0644\u062f\u0631 (Cam 1\u060c Cam 2\u2026) \u0648\u0627\u0644\u0645\u0627\u064a\u0643\u0627\u062a \u0644\u0648\u062d\u062f\u0647\u0627.',
            secRename: '\u0623\u0633\u0645\u0627\u0621 \u0627\u0644\u0646\u0633\u062a\u0627\u062a (\u0639\u0644\u0649 \u062d\u0633\u0628 \u0627\u0644\u0644\u064a \u062c\u0648\u0627\u0647\u0627)', renamed: '\u0648\u0627\u062a\u063a\u064a\u0631 \u0627\u0633\u0645 {n} \u0646\u0633\u062a.',
            used: '\u0645\u0633\u062a\u062e\u062f\u0645', notUsed: '\u0645\u0634 \u0645\u0633\u062a\u062e\u062f\u0645', copies: '{n} \u0646\u0633\u062e'
        },
        en: {
            openLogs: 'Open logs folder', openFolder: 'Open Tidy folder', project: 'Project', scan: 'SCAN PROJECT',
            stItems: 'items', stSize: 'media size', stRemove: 'to remove from the project', stFree: 'of the project size is unused',
            optRemove: 'Remove the ticked items', optOrganize: 'Organize into type bins', optColors: 'Give each type a fixed colour',
            secRemove: 'Remove from the project', secMove: 'Move to its bin', secBins: 'Old bins to remove', secDup: 'Duplicates in use (info)',
            secOffline: 'Missing on disk (offline)',
            rUnused: 'Not used in any sequence', rDuplicate: 'Unused duplicate copy', rBackup: 'Old Hush/Kalam backup',
            rCaptions: 'Caption files (your choice: Premiere does not say which are in use)',
            apply: 'CLEAN & ORGANIZE', confirmYes: 'Yes, go', confirmNo: 'Cancel',
            confirmText: 'The project is saved and a backup copy is made next to it. Then {r} items are removed from the project, {m} are moved and {b} empty bins are removed. Files on disk are not touched.',
            undo: 'Open the pre-clean copy', scanning: 'Scanning...', applying: 'Cleaning...',
            done: 'Done: removed {r}, moved {m}, removed {b} bins, coloured {c}.', skipped: '{s} kept because they turned out to be in use.',
            backupAt: 'Backup: {p}', noProject: 'Open a project first', unsaved: 'Save the project once first (File > Save) so a backup can be made.',
            nothing: 'The project is clean and organized. Nothing to do.', opened: 'Opened the pre-clean copy.',
            problems: '{n} could not be done (details in the log).',
            syncNothing: 'No sound match to build on.', sync: 'SYNC THE PODCAST BY SOUND', syncNeedTwo: 'Needs at least a camera and a mic (or two cameras) to sync.', syncExport: 'Reading sound {i}/{n}: {name}', syncMatch: 'Matching the sound...', syncDone: 'Made {seq} with {n} synced clips.', syncSkipped: 'No sound match (left out): {list}',
            modeReels: 'Reels', modePodcast: 'Podcast', modeHint: 'Podcast: one bin per camera (Cam 1, Cam 2...) and the mics apart.',
            secRename: 'Nest names (from what they hold)', renamed: 'Renamed {n} nests.',
            used: 'used', notUsed: 'unused', copies: '{n} copies'
        }
    };
    var I = { lang: 'ar' };
    I.t = function (key, vars) {
        var s = (T[I.lang] && T[I.lang][key]) || T.en[key] || key, k;
        for (k in vars || {}) { if (vars.hasOwnProperty(k)) { s = s.split('{' + k + '}').join(vars[k]); } }
        return s;
    };
    I.apply = function (lang) {
        I.lang = lang === 'en' ? 'en' : 'ar';
        document.documentElement.lang = I.lang;
        document.documentElement.dir = I.lang === 'ar' ? 'rtl' : 'ltr';
        var els = document.querySelectorAll('[data-i18n]'), i;
        for (i = 0; i < els.length; i++) { els[i].textContent = I.t(els[i].getAttribute('data-i18n')); }
    };
    root.TidyI18n = I;
})(window);
