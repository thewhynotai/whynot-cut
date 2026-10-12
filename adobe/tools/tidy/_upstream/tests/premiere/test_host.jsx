/* Premiere test for tidy/jsx/host.jsx. Runs only when the open projects are Tidy test projects.
   Builds a fresh project with known contents, then scans, plans and applies. Prints PASS/FAIL lines. */
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/tidy/jsx/host.jsx'));
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/tidy/js/media.js'));
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/tidy/js/classify.js'));
$.evalFile(new File('/Users/macstoreeg/Metrial/shhh Hoka/tidy/js/plan.js'));
var DIR = Folder('~/Library/Application Support/Tidy/test').fsName;

function __probe() {
    var i, out = [];
    for (i = 0; i < app.projects.numProjects; i++) {
        if (app.projects[i].path.indexOf('/Tidy/test/') < 0) { return 'ABORT: a non-test project is open: ' + app.projects[i].path; }
    }
    while (app.projects.numProjects) { app.projects[0].closeDocument(1, 0); }
    app.newProject(DIR + '/TidyRun ' + new Date().getTime() + '.prproj');
    var p = app.project, root = p.rootItem;
    function check(c, m) { out.push((c ? 'PASS ' : 'FAIL ') + m); }
    function imp(f, bin) { var n = (bin || root).children.numItems; p.importFiles([DIR + '/' + f], true, bin || root, false); return (bin || root).children[(bin || root).children.numItems - 1]; }
    var old = root.createBin('My Old Bin');
    var dupA = old.createBin('Assets'), dupB = old.createBin('Assets');   // two sibling bins with one name (as in real projects)
    dupB.createBin('Assets');
    var cam = imp('C0001.MP4'), clip = imp('clip.mp4'), clip2 = imp('clip.mp4', dupA), voice = imp('voice.wav', dupB), sfx = imp('whoosh_sfx.wav'), logo = imp('logo.png'), music = imp('music.wav');
    var main = p.createNewSequenceFromClips('Main', [clip, cam], root);
    p.createNewSequenceFromClips('Logo Nest', [logo], root);
    p.openSequence(main.sequenceID);
    main.audioTracks[1].insertClip(sfx, 2.0);
    var nestItem = null;
    for (i = 0; i < root.children.numItems; i++) { if (root.children[i].name === 'Logo Nest') { nestItem = root.children[i]; } }
    main.videoTracks[1].overwriteClip(nestItem, 1.0);
    var bk = p.createNewSequenceFromClips('Main (Hush backup 10:00:00)', [music], root);   // music used only in a backup
    p.openSequence(main.sequenceID);

    var scan = TIDY.parse(tidy_scan('{}'));
    check(scan.ok && scan.items.length === 10, 'scan sees 10 items (7 files, 3 sequences): ' + (scan.items ? scan.items.length : scan.error));
    for (i = 0; i < scan.items.length; i++) { scan.items[i].exists = true; scan.items[i].size = 1; TidyMedia.describe(scan.items[i], null); }   // as the panel does when bytes are unreadable
    var plan = TidyPlan.build(scan, {});
    var names = {}; for (i = 0; i < plan.removals.length; i++) { names[plan.removals[i].name + ':' + plan.removals[i].reason] = plan.removals[i].checked; }
    check(names['voice.wav:unused'] === true && names['music.wav:unused'] === true && names['clip.mp4:duplicate'] === true && names['Main (Hush backup 10:00:00):backup'] === true,
          'plan removes voice, music (only in backup), the duplicate clip and the backup: ' + TIDY.str(names));
    check(plan.renames.length === 1 && plan.renames[0].from === 'Logo Nest' && plan.renames[0].to === 'logo', 'the nest is named after the image it holds: ' + TIDY.str(plan.renames));
    var res = TIDY.parse(tidy_apply(TIDY.str({ moves: plan.moves, removals: plan.removals, emptyBins: plan.emptyBins, colors: plan.colors, renames: plan.renames })));
    check(res.ok, 'apply ok ' + (res.error || TIDY.str(res)));

    var after = TIDY.parse(tidy_scan('{}')), where = {}, left = [];
    for (i = 0; i < after.items.length; i++) { where[after.items[i].name] = after.items[i].bin; left.push(after.items[i].name); }
    check(left.length === 6 && res.renamed === 1, 'six items left, one nest renamed: ' + left.join(', '));
    check(where['C0001.MP4'] === '01 Footage' && where['clip.mp4'] === '02 Renders & Stock' && where['whoosh_sfx.wav'] === '03 Audio/SFX' &&
          where['logo.png'] === '04 Images/Icons' && where['Main'] === '06 Sequences' && where['logo'] === '07 Nests',
          'camera footage, renders, sub-bins: ' + TIDY.str(where));
    var binPaths = []; for (i = 0; i < after.bins.length; i++) { binPaths.push(after.bins[i].path); }
    check(TIDY.str(binPaths).indexOf('My Old Bin') < 0, 'the emptied old bin and its same-name sub-bins are gone: ' + binPaths.join(', '));
    check(res.binsRemoved === 4 && res.problems.length === 0, 'four old bins removed, no problems: ' + TIDY.str(res));
    var camItem = TIDY.byId(after.items, 'C0001.MP4');
    check(camItem && camItem.color === TidyClassify.COLORS.footage, 'footage got its colour');
    check(main.videoTracks[0].clips.numItems === 2 && main.videoTracks[1].clips.numItems === 1, 'the edit is untouched');
    var guard = TIDY.parse(tidy_apply(TIDY.str({ moves: [], removals: [{ nodeId: TIDY.byId(after.items, 'clip.mp4').nodeId, name: 'clip.mp4', checked: true }], emptyBins: [], colors: [] })));
    check(guard.ok && guard.skipped === 1 && guard.removed === 0, 'host refuses to remove a used item even if asked');
    p.save();
    return out.join('\n');
}
