// run from tidy/: jsc tests/test_lint.js
// ExtendScript (Premiere's engine, where host.jsx runs and where the Premiere tests run these modules) evaluates
// "a ? x : b ? y : z" wrongly (it returned y with a true). Every nested conditional must be parenthesized.
var fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
['js/media.js', 'js/classify.js', 'js/plan.js', 'jsx/host.jsx'].forEach(function (f) {
    var bad = [];
    readFile(f).split('\n').forEach(function (line, i) {
        var code = line.replace(/'(?:\\.|[^'])*'|"(?:\\.|[^"])*"/g, 'S').replace(/\/(?:\\.|[^\/\n*])(?:\\.|[^\/\n])*\/[gimsuy]*/g, 'R')
                       .replace(/\(\?[:=!]/g, '(');
        // a ':' followed (at the same paren depth) by another '?' = an unparenthesized nested conditional
        var depth = 0, seenQ = [], j, c;
        for (j = 0; j < code.length; j++) {
            c = code[j];
            if (c === '(' || c === '[' || c === '{') { depth++; } else if (c === ')' || c === ']' || c === '}') { depth--; }
            else if (c === '?' && code[j + 1] !== '.') {
                if (seenQ[depth] === 'colon') { bad.push(i + 1); break; }
                seenQ[depth] = 'q';
            } else if (c === ':' && seenQ[depth] === 'q') { seenQ[depth] = 'colon'; }
            else if (c === ';' || c === ',') { seenQ[depth] = null; }
        }
    });
    ok(bad.length === 0, f + ' has no unparenthesized nested ?: ' + (bad.length ? '(lines ' + bad.join(', ') + ')' : ''));
});
print(fails ? fails + ' FAILED' : 'ALL PASS');
