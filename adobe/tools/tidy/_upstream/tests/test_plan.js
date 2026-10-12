// run from tidy/: jsc tests/test_plan.js
var window = this;
load('js/classify.js'); load('js/plan.js');
var P = window.TidyPlan, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
function I(id, name, path, extra) {
    var it = { nodeId: id, name: name, path: path, isSequence: false, duration: 10, bin: '', exists: true, offline: false, size: 1000, color: 0 };
    for (var k in (extra || {})) { it[k] = extra[k]; }
    return it;
}
var scan = {
    items: [
        I('c1', 'clip.mp4', '/m/clip.mp4', { size: 5000, kind: 'camera', camId: 'DJI OsmoPocket3', duration: 600 }),
        I('c2', 'clip.mp4', '/m/clip.mp4', { size: 5000, kind: 'camera', camId: 'DJI OsmoPocket3' }),                  // duplicate, unused
        I('v1', 'voice.wav', '/m/voice.wav', { duration: 200 }),             // unused
        I('x1', 'onlyInBackup.mp4', '/m/onlyInBackup.mp4'),                  // used only in the backup
        I('l1', 'logo.png', '/m/logo.png'),                                  // used only inside the nest
        I('s1', 'whoosh_sfx.wav', '/m/whoosh_sfx.wav', { duration: 0.8, bin: '03 Audio/SFX', color: 7 }),  // already in place
        I('d1', 'both.mp4', '/m/both.mp4', { kind: 'camera', camId: 'iPhone 16 Pro Max', duration: 100 }), I('d2', 'both.mp4', '/m/both.mp4', { kind: 'camera', camId: 'iPhone 16 Pro Max', duration: 100 }),   // duplicates, both used
        I('o1', 'gone.mp4', '/m/gone.mp4', { exists: false }),               // missing on disk, used
        I('t1', 'subs.srt', '/m/subs.srt', { bin: 'Kalam Captions' }),       // caption, usage unknown
        I('q1', 'Main', '', { isSequence: true, size: 0 }),
        I('q2', 'Logo Nest', '', { isSequence: true, size: 0 }),
        I('q3', 'Main (Hush backup 10:00:00)', '', { isSequence: true, size: 0 }),
        I('q4', 'Old Edit', '', { isSequence: true, size: 0 })                        // a kept sequence used nowhere
    ],
    bins: [{ nodeId: 'b1', path: 'Empty Bin' }, { nodeId: 'b2', path: 'Kalam Captions' }, { nodeId: 'b3', path: '03 Audio' }, { nodeId: 'b4', path: '03 Audio/SFX' },
           { nodeId: 'b5', path: 'Assets' }, { nodeId: 'b6', path: 'Assets/Assets' }, { nodeId: 'b7', path: 'Assets/Assets' }, { nodeId: 'b8', path: 'Recovered Clips' },
           { nodeId: 'b9', path: '04 Images/Other' }],
    usage: { q1: ['c1', 'q2', 's1', 'd1', 'o1'], q2: ['l1'], q3: ['c1', 'x1'], q4: ['d2'] }
};
var plan = P.build(scan, {});
function removal(id) { for (var i = 0; i < plan.removals.length; i++) { if (plan.removals[i].nodeId === id) { return plan.removals[i]; } } return null; }
function move(id) { for (var i = 0; i < plan.moves.length; i++) { if (plan.moves[i].nodeId === id) { return plan.moves[i]; } } return null; }

ok(removal('x1') && removal('x1').checked, 'media used only inside a Hush backup being removed is unused');
ok(!removal('l1') && move('l1') && move('l1').to === '04 Images/PNG', 'media used only inside a kept nest is used');
ok(!removal('d1') && !removal('d2') && plan.duplicates.length === 1 && plan.duplicates[0].used === 2, 'duplicates that are both used are only reported');
ok(removal('c2') && removal('c2').reason === 'duplicate' && removal('c2').checked, 'an unused copy of a used file is removed as a duplicate');
ok(plan.offline.length === 1 && plan.offline[0].nodeId === 'o1' && !removal('o1'), 'missing on disk is listed as offline (and kept when used)');
ok(!move('s1'), 'an item already in its bin is not moved');
ok(removal('v1') && removal('v1').checked && removal('v1').reason === 'unused', 'unused media is removed');
ok(removal('t1') && removal('t1').checked === false, 'caption files are listed but unticked');
ok(removal('q3') && removal('q3').checked && removal('q3').reason === 'backup', 'Hush backup sequence removed');
ok(!removal('q1') && !removal('q4'), 'other sequences are never removed, even unused ones');
ok(move('q2') && move('q2').to === '07 Nests' && move('q4') && move('q4').to === '06 Sequences', 'nests and sequences go to their bins');
ok(move('c1') && move('c1').to === '01 Footage', 'footage moves to 01 Footage');
var eb = plan.emptyBins.map(function (b) { return b.path; }).join(',');
ok(eb.indexOf('Empty Bin') >= 0 && eb.indexOf('03 Audio') < 0, 'old bins are removed, type bins in use kept: ' + eb);
ok(/Kalam Captions/.test(eb) && /Recovered Clips/.test(eb) && plan.emptyBins.filter(function (b) { return b.path === 'Assets/Assets'; }).length === 2 && /(^|,)Assets(,|$)/.test(eb),
   'Assets (and both same-name sub-bins), Kalam Captions and Recovered Clips go');
ok(plan.emptyBins[0].path.split('/').length >= plan.emptyBins[plan.emptyBins.length - 1].path.split('/').length, 'deepest bins first');
ok(/04 Images\/Other/.test(eb), 'an empty type bin that nothing goes into is removed too');
ok(plan.colors.filter(function (c) { return c.nodeId === 's1'; }).length === 0 && plan.colors.filter(function (c) { return c.nodeId === 'c1'; }).length === 1, 'colours only change when different');
ok(plan.stats.removeCount === 4 && plan.stats.removeSize === 5000 + 1000 + 1000, 'stats count ticked removals and their size: ' + JSON.stringify(plan.stats));
var plan2 = P.build(scan, { unchecked: { v1: true } });
ok(plan2.stats.removeCount === 3, 'the user can untick a removal');
var plan3 = P.build(scan, { checked: { t1: true } });
ok(plan3.removals.filter(function (r) { return r.nodeId === 't1'; })[0].checked && plan3.stats.removeCount === 5, 'the user can tick a caption file to remove it, and it counts');
var pod = P.build(scan, { mode: 'podcast' });
function pmove(id) { for (var i = 0; i < pod.moves.length; i++) { if (pod.moves[i].nodeId === id) { return pod.moves[i]; } } return null; }
ok(pmove('c1') && pmove('c1').to === '01 Footage/Cam 1' && pmove('d1') && pmove('d1').to === '01 Footage/Cam 2', 'podcast: each camera gets its Cam bin, most footage first');
var peb = pod.emptyBins.map(function (b) { return b.path; }).join(',');
ok(peb.indexOf('01 Footage') < 0, 'podcast: the parent footage bin is kept');
var raw = { items: [I('k1', 'C0001.MP4', '/r/C0001.MP4', { kind: 'camera', camId: 'A', duration: 3000 }), I('m1', 'ZOOM0001.WAV', '/r/ZOOM0001.WAV', { duration: 3600 }),
                    I('u1', 'stock.mp4', '/r/stock.mp4', { kind: 'render' })], bins: [], usage: {} };
var rp = P.build(raw, { mode: 'podcast' }), rr = {};
for (i = 0; i < rp.removals.length; i++) { rr[rp.removals[i].nodeId] = rp.removals[i].checked; }
ok(rr.k1 === false && rr.m1 === false && rr.u1 === true, 'podcast: unused camera footage and mics start unticked (raw material for the sync): ' + JSON.stringify(rr));
var rq = P.build(raw, { mode: 'podcast', checked: { k1: true } });
ok(rq.removals.filter(function (r) { return r.nodeId === 'k1'; })[0].checked === true, 'podcast: the user can still tick them');
var raw2 = { items: [I('k2', 'Interview final.mp4', '/r/Interview final.mp4', { kind: 'render', duration: 2400 }), I('k3', 'Intro.mp4', '/r/Intro.mp4', { kind: 'render', duration: 12 })], bins: [], usage: {} };
var rp2 = P.build(raw2, { mode: 'podcast' }), rr2 = {};
for (i = 0; i < rp2.removals.length; i++) { rr2[rp2.removals[i].nodeId] = rp2.removals[i].checked; }
ok(rr2.k2 === false && rr2.k3 === true, 'podcast: any long unused recording starts unticked, short leftovers stay ticked: ' + JSON.stringify(rr2));
// nests are named after what they hold: text, else image, else the clip
var ns = { items: [I('main', 'Main', '', { isSequence: true, size: 0 }),
                   I('n1', 'Nested Sequence 01', '', { isSequence: true, size: 0 }), I('n2', 'Nested Sequence 02', '', { isSequence: true, size: 0 }),
                   I('n3', 'Nested Sequence 03', '', { isSequence: true, size: 0 }), I('n4', 'Nested Sequence 04', '', { isSequence: true, size: 0 }),
                   I('n5', 'Nested Sequence 05', '', { isSequence: true, size: 0 }),
                   I('img', 'Corporate Success.png', '/a/Corporate Success.png'), I('cam', 'C0001.MP4', '/a/C0001.MP4', { kind: 'camera' })],
           bins: [], usage: { main: ['n1', 'n2', 'n3', 'n4', 'n5'], n1: ['img'], n2: [], n3: [], n4: ['cam'], n5: ['img'] },
           texts: { n2: ['  \u0647\u064a\u0631\u0642\u064a\u0643   \u0644\u0648  '], n3: ['3'] } };
var np = P.build(ns, {}), ren = {};
for (i = 0; i < np.renames.length; i++) { ren[np.renames[i].nodeId] = np.renames[i]; }
ok(ren.n2 && ren.n2.to === '\u0647\u064a\u0631\u0642\u064a\u0643 \u0644\u0648' && ren.n2.checked, 'a text nest is named after its text: ' + (ren.n2 && ren.n2.to));
ok(ren.n3 && ren.n3.to === '3', 'a number nest is named by the number');
ok(ren.n1 && ren.n1.to === 'Corporate Success' && ren.n5 && ren.n5.to === 'Corporate Success 2', 'an image nest is named after the image, repeats get a number: ' + (ren.n5 && ren.n5.to));
ok(ren.n4 && ren.n4.to === 'C0001', 'otherwise after the clip inside');
ok(!ren.main, 'sequences that are not nests keep their names');
var np2 = P.build(ns, { noRename: { n1: true } });
ok(np2.renames.filter(function (r) { return r.nodeId === 'n1'; })[0].checked === false, 'the user can untick a rename');
ok(np.moves.filter(function (m) { return m.nodeId === 'n2'; })[0].to === '07 Nests', 'nests have their own bin');
print(fails ? fails + ' FAILED' : 'ALL PASS');
