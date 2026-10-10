/*  whynot-cut — Photoshop layered asset builder (ExtendScript).
    The generated script defines NH_PS before including this file.
    Each job -> one 1080x1920 RGB PSD with named, non-destructive layers:
      BG photo (smart-object-free placed copy, original untouched) / brand band / text layers / logo.
    Text layers stay editable. Arabic needs Photoshop's "Middle Eastern and South Asian"
    text engine (Preferences > Type) for correct shaping in the editable layer.
*/
#target photoshop
var NHPS = {};
NHPS.log = [];

NHPS.color = function (rgb) { var c = new SolidColor(); c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2]; return c; };

NHPS.placeImage = function (doc, path, name, fitW, fitH, cx, cy) {
    var f = new File(path);
    if (!f.exists) { NHPS.log.push("missing " + path); return null; }
    var src = app.open(f);
    if (src.mode !== DocumentMode.RGB) { src.changeMode(ChangeMode.RGB); }
    if (src.layers.length > 1) { src.mergeVisibleLayers(); }   // keep transparency (no flatten)
    var L = src.artLayers[0].duplicate(doc, ElementPlacement.PLACEATBEGINNING);
    src.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;
    L.name = name;
    var b = L.bounds, w = b[2].as("px") - b[0].as("px"), h = b[3].as("px") - b[1].as("px");
    var s = Math.max(fitW / w, fitH / h) * 100;
    L.resize(s, s, AnchorPosition.MIDDLECENTER);
    b = L.bounds;
    var lx = (b[0].as("px") + b[2].as("px")) / 2, ly = (b[1].as("px") + b[3].as("px")) / 2;
    L.translate(cx - lx, cy - ly);
    return L;
};

NHPS.rectLayer = function (doc, name, x0, y0, x1, y1, rgb, opacity) {
    var L = doc.artLayers.add();
    L.name = name;
    doc.selection.select([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]);
    doc.selection.fill(NHPS.color(rgb));
    doc.selection.deselect();
    L.opacity = opacity === undefined ? 100 : opacity;
    return L;
};

NHPS.gradientBand = function (doc, name, y0, y1, rgb) {
    // vertical fade band built from stacked strips (keeps it scriptable without ActionManager)
    var set = doc.layerSets.add(); set.name = name;
    var steps = 24, h = (y1 - y0) / steps;
    for (var i = 0; i < steps; i++) {
        var L = NHPS.rectLayer(doc, name + "_" + i, 0, y0 + i * h, doc.width.as("px"), y0 + (i + 1) * h + 1, rgb, Math.round(100 * i / (steps - 1)));
        L.move(set, ElementPlacement.INSIDE);
    }
    return set;
};

NHPS.text = function (doc, name, str, font, size, rgb, cx, cy) {
    var L = doc.artLayers.add();
    L.kind = LayerKind.TEXT;
    L.name = name;
    var t = L.textItem;
    t.contents = str;
    try { t.font = font; } catch (e) { NHPS.log.push("font " + font + " not set"); }
    t.size = new UnitValue(size, "px");
    t.color = NHPS.color(rgb);
    t.justification = Justification.CENTER;
    t.position = [new UnitValue(cx, "px"), new UnitValue(cy, "px")];
    if (NHPS.isArabic(str)) { NHPS.setRTL(); }
    return L;
};

NHPS.isArabic = function (s) { return /[\u0600-\u06FF]/.test(s); };

/* Paragraph direction RTL + World-Ready (Middle Eastern) composer on the active text layer.
   The DOM has no API for this; ActionManager edits the layer's textKey paragraph styles. */
NHPS.setRTL = function () {
    try {
        var s2t = stringIDToTypeID, c2t = charIDToTypeID;
        var ref = new ActionReference();
        ref.putEnumerated(c2t("Lyr "), c2t("Ordn"), c2t("Trgt"));
        var textKey = executeActionGet(ref).getObjectValue(s2t("textKey"));
        var psr = textKey.getList(s2t("paragraphStyleRange"));
        var out = new ActionList();
        for (var i = 0; i < psr.count; i++) {
            var r = psr.getObjectValue(i);
            var ps = r.getObjectValue(s2t("paragraphStyle"));
            ps.putEnumerated(s2t("directionType"), s2t("directionType"), s2t("dirRightToLeft"));
            ps.putEnumerated(s2t("textComposerEngine"), s2t("textComposerEngine"), s2t("textOptycaComposer"));
            r.putObject(s2t("paragraphStyle"), s2t("paragraphStyle"), ps);
            out.putObject(s2t("paragraphStyleRange"), r);
        }
        textKey.putList(s2t("paragraphStyleRange"), out);
        var d = new ActionDescriptor();
        var r2 = new ActionReference();
        r2.putEnumerated(c2t("TxLr"), c2t("Ordn"), c2t("Trgt"));
        d.putReference(c2t("null"), r2);
        d.putObject(c2t("T   "), c2t("TxLr"), textKey);
        executeAction(c2t("setd"), d, DialogModes.NO);
    } catch (e) { NHPS.log.push("RTL not set: " + e); }
};

NHPS.build = function () {
    var made = [];
    var prevUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    app.displayDialogs = DialogModes.NO;
    for (var i = 0; i < NH_PS.jobs.length; i++) {
        var j = NH_PS.jobs[i];
        try {
            var doc = app.documents.add(1080, 1920, 72, j.id, NewDocumentMode.RGB, DocumentFill.WHITE);
            doc.artLayers[0].name = "Base (white)";
            if (j.background === "paper") { NHPS.rectLayer(doc, "Paper tint", 0, 0, 1080, 1920, NH_PS.brand.paper, 100); }
            if (j.image) { NHPS.placeImage(doc, j.image, "Client photo — " + j.image_name, j.image_fit_w || 1080, j.image_fit_h || 1920, 540, j.image_cy || 960); }
            if (j.band) { NHPS.gradientBand(doc, "Brand band", j.band[0], j.band[1], NH_PS.brand.teal); }
            if (j.headline) { NHPS.text(doc, "Headline (editable)", j.headline, NH_PS.fonts.headline, j.headline_size || 92, j.headline_color || NH_PS.brand.white, 540, j.headline_y || 1450); }
            if (j.subline) { NHPS.text(doc, "Subline (editable)", j.subline, NH_PS.fonts.body, j.subline_size || 46, j.subline_color || NH_PS.brand.white, 540, j.subline_y || 1600); }
            if (NH_PS.logo && j.logo !== false) {
                var lg = NHPS.placeImage(doc, NH_PS.logo, "Logo", j.logo_size || 200, j.logo_size || 200, 540, j.logo_y || 1780);
            }
            var psd = new File(NH_PS.out_dir + "/" + j.id + ".psd");
            var o = new PhotoshopSaveOptions(); o.layers = true; o.embedColorProfile = true;
            doc.saveAs(psd, o, true);
            var png = new File(NH_PS.out_dir + "/" + j.id + "_preview.png");
            var po = new PNGSaveOptions();
            doc.saveAs(png, po, true);
            doc.close(SaveOptions.DONOTSAVECHANGES);
            made.push(j.id);
        } catch (err) { NHPS.log.push("FAILED " + j.id + ": " + err + " line " + err.line); }
    }
    app.preferences.rulerUnits = prevUnits;
    return "NHPS_RESULT|made=" + made.length + "|" + made.join(",") + "|log=" + NHPS.log.join(" ; ");
};
