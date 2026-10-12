/* Premiere test for tidy_buildSynced: 3 cameras + 2 mics at known starts (more tracks than a new sequence has).
   Runs only when the open projects are test projects. Prints PASS/FAIL lines. */
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/tidy/jsx/host.jsx'));
var DIR = Folder('~/Library/Application Support/Tidy/test').fsName;

function __probe() {
    var i, out = [];
    for (i = 0; i < app.projects.numProjects; i++) {
        var pp = app.projects[i].path;
        if (pp.indexOf('/Tidy/test/') < 0 && pp.indexOf('/Kalam/test/') < 0) { return 'ABORT: a non-test project is open: ' + pp; }
    }
    while (app.projects.numProjects) { app.projects[0].closeDocument(0, 0); }
    app.newProject(DIR + '/TidySync ' + new Date().getTime() + '.prproj');
    var p = app.project, P = DIR + '/podcast/';
    function check(c, m) { out.push((c ? 'PASS ' : 'FAIL ') + m); }
    p.importFiles([P + 'CamA/C0101.MP4', P + 'CamB/IMG_0201.MOV', P + 'CamC/A001C003.MP4', P + 'ZOOM0001.WAV', P + 'ZOOM0002.WAV'], true, p.rootItem, false);
    var id = {};
    for (i = 0; i < p.rootItem.children.numItems; i++) { id[p.rootItem.children[i].name] = p.rootItem.children[i].nodeId; }
    var r = TIDY.parse(tidy_buildSynced(TIDY.str({
        name: 'Sync Test - Synced', first: id['C0101.MP4'], bin: '06 Sequences',
        cams: [{ nodeId: id['C0101.MP4'], start: 3.217, track: 0 }, { nodeId: id['IMG_0201.MOV'], start: 20, track: 1 }, { nodeId: id['A001C003.MP4'], start: 7.5, track: 2 }],
        mics: [{ nodeId: id['ZOOM0001.WAV'], start: 0 }, { nodeId: id['ZOOM0002.WAV'], start: 10 }]
    })));
    check(r.ok && r.placed === 5, 'five clips placed: ' + TIDY.str(r));
    check(r.ok && r.problems.length === 0, 'every clip read back where it was asked to be');
    var s = p.activeSequence, where = {}, t, c;
    for (t = 0; t < s.videoTracks.numTracks; t++) { for (c = 0; c < s.videoTracks[t].clips.numItems; c++) { where['V' + (t + 1) + ' ' + s.videoTracks[t].clips[c].name] = s.videoTracks[t].clips[c].start.seconds; } }
    for (t = 0; t < s.audioTracks.numTracks; t++) { for (c = 0; c < s.audioTracks[t].clips.numItems; c++) { where['A' + (t + 1) + ' ' + s.audioTracks[t].clips[c].name] = s.audioTracks[t].clips[c].start.seconds; } }
    check(Math.abs(where['V3 A001C003.MP4'] - 7.5) < 0.034 && Math.abs(where['V2 IMG_0201.MOV'] - 20) < 0.034, 'Cam 3 on V3 at 7.5 s, Cam 2 on V2 at 20 s: ' + TIDY.str(where));
    var micA = -1, micB = -1, camAudio = -1;
    for (var k in where) { if (where.hasOwnProperty(k)) {
        var tr = parseInt(k.slice(1), 10);
        if (k.charAt(0) === 'A' && /ZOOM0001/.test(k)) { micA = tr; }
        if (k.charAt(0) === 'A' && /ZOOM0002/.test(k)) { micB = tr; }
        if (k.charAt(0) === 'A' && !/ZOOM/.test(k) && tr > camAudio) { camAudio = tr; }
    } }
    check(micA > camAudio && micB === micA + 1, 'mics on their own tracks after the camera sound: cams up to A' + camAudio + ', mics A' + micA + ', A' + micB);
    p.save();
    return out.join('\n');
}
