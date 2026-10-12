/* Premiere test for kalam/jsx/host.jsx - run ONLY with the KalamTest project open (run_premiere_test.sh).
   Prints PASS/FAIL lines. */
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/kalam/jsx/host.jsx'));
var TEST_PROJECT = '/Kalam/test/KalamTest.prproj';
var DIR = Folder('~/Library/Application Support/Kalam/test').fsName;

function __probe() {
    if (app.projects.numProjects !== 1 || app.project.path.indexOf(TEST_PROJECT) < 0) { return 'ABORT: only KalamTest.prproj may be open'; }
    var out = [], p = app.project, item = null, j;
    function check(cond, msg) { out.push((cond ? 'PASS ' : 'FAIL ') + msg); }
    for (j = 0; j < p.rootItem.children.numItems; j++) { if (p.rootItem.children[j].name === 'hush_test.mp4') { item = p.rootItem.children[j]; } }
    if (!item) { p.importFiles([DIR + '/hush_test.mp4'], true, p.rootItem, false); item = p.rootItem.children[p.rootItem.children.numItems - 1]; }
    var seq = p.createNewSequenceFromClips('Kalam Test ' + p.sequences.numSequences, [item], p.rootItem);
    check(p.activeSequence && p.activeSequence.sequenceID === seq.sequenceID, 'fresh test sequence is active');

    var info = KALAM.parse(kalam_info('{}'));
    check(info.ok && info.sequence.audio.length >= 1 && info.sequence.fps === 25, 'info: tracks + fps 25');
    seq.setPlayerPosition(KALAM.ticksStr(4.0));
    var info2 = KALAM.parse(kalam_info('{}'));
    check(Math.abs(info2.sequence.playhead - 4.0) < 0.05, 'info reports the playhead: ' + info2.sequence.playhead);

    var ex = KALAM.parse(kalam_exportAudio(KALAM.str({ outPath: DIR + '/export.wav', start: 0, end: 15, audioTracks: [0] })));
    check(ex.ok && new File(ex.path).exists, 'exportAudio wrote ' + ex.path);

    var cap = KALAM.parse(kalam_captionsTrack(KALAM.str({ srtPath: DIR + '/test.srt', start: 2.0, name: 'Kalam test.srt' })));
    check(cap.ok, 'captions track created ' + (cap.error || ''));

    var caps = [{ s: 1.2, e: 3.0, text: 'Hello welcome' }, { s: 3.0, e: 4.6, text: 'second caption' }, { s: 4.6, e: 6.0, text: '\u0623\u0646\u0627 \u062f\u0643\u062a\u0648\u0631' }];
    var EG = Folder.appPackage.fsName + '/Contents/Essential Graphics/';
    var bad = KALAM.parse(kalam_mogrt(KALAM.str({ mogrtPath: EG + 'Basic Title.mogrt', videoTrack: 1, captions: caps.slice(0, 1), start: 2.0 })));
    check(!bad.ok && /editable text/.test(bad.error) && seq.videoTracks[1].clips.numItems === 0, 'MOGRT without editable text: clear error, nothing left behind: ' + bad.error);
    var mg = KALAM.parse(kalam_mogrt(KALAM.str({ mogrtPath: EG + '[AE] Video Gaming Package/Gaming Lower Third Left.mogrt',
                                                 videoTrack: 1, captions: caps, start: 2.0 })));
    check(mg.ok && mg.added === 3, 'mogrt added ' + (mg.added || mg.error));
    var v2 = seq.videoTracks[1].clips;
    check(v2.numItems === 3, 'V2 has 3 clips');
    if (v2.numItems === 3) {
        check(Math.abs(KALAM.sec(v2[0].start) - 3.2) < 0.05 && Math.abs(KALAM.sec(v2[0].end) - 5.0) < 0.05, 'first clip at 3.2-5.0 (start offset applied): ' + KALAM.sec(v2[0].start) + '-' + KALAM.sec(v2[0].end));
        check(KALAM.sec(v2[0].end) === KALAM.sec(v2[1].start), 'no gap between MOGRT clips');
        var props = v2[2].getMGTComponent().properties, val = '';
        for (j = 0; j < props.numItems; j++) { if (props[j].displayName === 'Title') { val = KALAM.parse(props[j].getValue()).textEditValue; } }
        check(val === caps[2].text, 'Arabic text set in the Title field of clip 3: ' + val);
        check(mg.field === 'Title', 'text went to the first real text field: ' + mg.field);
    }
    var rm = KALAM.parse(kalam_removeClips(KALAM.str({ videoTrack: 1, from: 0, to: 100 })));
    check(rm.ok && rm.removed === 3 && seq.videoTracks[1].clips.numItems === 0, 'removeClips removed 3');
    p.save();
    return out.join('\n');
}
