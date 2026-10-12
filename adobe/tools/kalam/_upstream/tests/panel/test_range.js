// run: jsc tests/panel/test_range.js   (from kalam/)
var window = this;
load('js/range.js');
var R = window.KalamRange, fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
var seq = { end: 88.6, inPoint: 10, outPoint: 60, playhead: 25.5,
            selection: [{ name: 'a', start: 12, end: 20 }, { name: 'b', start: 18, end: 30 }] };

var r = R.rangeFor(seq, 'inout');      ok(r.ok && r.start === 10 && r.end === 60 && r.label === 'inOut', 'In/Out uses the in and out points');
r = R.rangeFor(seq, 'sequence');       ok(r.ok && r.start === 0 && r.end === 88.6 && r.label === 'wholeSeq', 'whole sequence is 0 to end');
r = R.rangeFor(seq, 'playhead');       ok(r.ok && r.start === 25.5 && r.end === 88.6 && r.label === 'fromPlayhead', 'from playhead to the end');
r = R.rangeFor(seq, 'selection');      ok(r.ok && r.start === 12 && r.end === 30 && r.count === 2, 'selected clips span');
r = R.rangeFor({ end: 50, inPoint: -400000, outPoint: -400000, playhead: 0, selection: [] }, 'inout');
ok(!r.ok && r.error === 'noInOut', 'In/Out not set gives a clear error');
r = R.rangeFor({ end: 50, inPoint: 0, outPoint: 0, playhead: 0, selection: [] }, 'selection');
ok(!r.ok && r.error === 'noSelection', 'nothing selected gives a clear error');
r = R.rangeFor({ end: 50, inPoint: 0, outPoint: 0, playhead: 49.95, selection: [] }, 'playhead');
ok(!r.ok && r.error === 'playheadAtEnd', 'playhead at the very end gives a clear error');

var srt = '1\n00:00:00,500 --> 00:00:02,000\nواحد\n\n2\n00:00:02,000 --> 00:00:03,250\nاتنين\n';
var shifted = R.shiftSrt(srt, 125.5);
ok(shifted === '1\n00:02:06,000 --> 00:02:07,500\nواحد\n\n2\n00:02:07,500 --> 00:02:08,750\nاتنين\n', 'SRT shifted to sequence time: ' + JSON.stringify(shifted));
ok(R.shiftSrt(srt, 0) === srt, 'zero offset leaves the SRT unchanged');
ok(R.shiftSrt('1\n00:59:59,900 --> 01:00:00,100\nx\n', 0.2).indexOf('01:00:00,100 --> 01:00:00,300') > 0, 'hour rollover');
print(fails ? fails + ' FAILED' : 'ALL PASS');
