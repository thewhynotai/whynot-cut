// run: jsc tests/panel/test_html.js   (from kalam/)
// every element main.js wires by id must be in index.html BEFORE the scripts (wire() runs as soon as main.js loads)
var fails = 0;
function ok(c, m) { print((c ? 'PASS ' : 'FAIL ') + m); if (!c) { fails++; } }
var html = readFile('index.html'), js = readFile('js/main.js');
var scriptsAt = html.indexOf('<script'), ids = {}, re = /\$\('([\w-]+)'\)/g, m, missing = [], late = [];
while ((m = re.exec(js))) { ids[m[1]] = true; }
for (var id in ids) {
    var at = html.indexOf('id="' + id + '"');
    if (at < 0) { missing.push(id); } else if (at > scriptsAt) { late.push(id); }
}
ok(missing.length === 0, 'every id main.js uses exists: ' + missing.join(', '));
ok(late.length === 0, 'and comes before the scripts: ' + late.join(', '));
print(fails ? fails + ' FAILED' : 'ALL PASS');
