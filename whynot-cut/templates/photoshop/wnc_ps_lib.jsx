/*  whynot-cut - Photoshop layered asset builder (ExtendScript).
    The generated script defines WNC_PS before including this file.
    Each job -> one RGB PSD of the profile's frame size (WNC_PS.w x WNC_PS.h, 1080x1920 by default) with named,
    non-destructive layers (every default position and size scales with that frame):
      BG photo (smart-object-free placed copy, original untouched) / brand band / text layers / logo.
    Text layers stay editable. Arabic needs Photoshop's "Middle Eastern and South Asian"
    text engine (Preferences > Type) for correct shaping in the editable layer.
*/
#target photoshop
var WNCPS = {};
WNCPS.log = [];

/* The document size is the client's sequence size, written into WNC_PS.w / WNC_PS.h by the generator: a 4:5 profile
   gets 1080x1350 documents. 1080x1920 when the data carries none (or a size that is not positive). The layout below
   was drawn on 1080x1920: x and sizes scale with the width, y with the height. */
WNCPS.W = 1080; WNCPS.H = 1920;   // defaults only: WNCPS.applyFrameSize() takes WNC_PS.w / WNC_PS.h
WNCPS.applyFrameSize = function () {
    var d = (typeof WNC_PS !== "undefined" && WNC_PS) ? WNC_PS : {};
    var ok = typeof d.w === "number" && typeof d.h === "number" && d.w > 0 && d.h > 0;
    WNCPS.W = ok ? d.w : 1080;
    WNCPS.H = ok ? d.h : 1920;
};
WNCPS.sx = function (v) { return v * WNCPS.W / 1080; };   // a 1080-wide x or size on this frame
WNCPS.sy = function (v) { return v * WNCPS.H / 1920; };   // a 1920-high y on this frame

WNCPS.color = function (rgb) { var c = new SolidColor(); c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2]; return c; };

WNCPS.placeImage = function (doc, path, name, fitW, fitH, cx, cy) {
    var f = new File(path);
    if (!f.exists) { WNCPS.log.push("missing " + path); return null; }
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

WNCPS.rectLayer = function (doc, name, x0, y0, x1, y1, rgb, opacity) {
    var L = doc.artLayers.add();
    L.name = name;
    doc.selection.select([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]);
    doc.selection.fill(WNCPS.color(rgb));
    doc.selection.deselect();
    L.opacity = opacity === undefined ? 100 : opacity;
    return L;
};

WNCPS.gradientBand = function (doc, name, y0, y1, rgb) {
    // vertical fade band built from stacked strips (keeps it scriptable without ActionManager)
    var set = doc.layerSets.add(); set.name = name;
    var steps = 24, h = (y1 - y0) / steps;
    for (var i = 0; i < steps; i++) {
        var L = WNCPS.rectLayer(doc, name + "_" + i, 0, y0 + i * h, doc.width.as("px"), y0 + (i + 1) * h + 1, rgb, Math.round(100 * i / (steps - 1)));
        L.move(set, ElementPlacement.INSIDE);
    }
    return set;
};

WNCPS.text = function (doc, name, str, font, size, rgb, cx, cy) {
    var L = doc.artLayers.add();
    L.kind = LayerKind.TEXT;
    L.name = name;
    var t = L.textItem;
    t.contents = str;
    try { t.font = font; } catch (e) { WNCPS.log.push("font " + font + " not set"); }
    t.size = new UnitValue(size, "px");
    t.color = WNCPS.color(rgb);
    t.justification = Justification.CENTER;
    t.position = [new UnitValue(cx, "px"), new UnitValue(cy, "px")];
    if (WNCPS.isArabic(str)) { WNCPS.setRTL(); }
    return L;
};

WNCPS.isArabic = function (s) { return /[\u0600-\u06FF]/.test(s); };

/* Paragraph direction RTL + World-Ready (Middle Eastern) composer on the active text layer.
   The DOM has no API for this; ActionManager edits the layer's textKey paragraph styles. */
WNCPS.setRTL = function () {
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
    } catch (e) { WNCPS.log.push("RTL not set: " + e); }
};

WNCPS.build = function () {
    var made = [];
    var prevUnits = app.preferences.rulerUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    app.displayDialogs = DialogModes.NO;
    WNCPS.applyFrameSize();
    var W = WNCPS.W, H = WNCPS.H, sx = WNCPS.sx, sy = WNCPS.sy;
    for (var i = 0; i < WNC_PS.jobs.length; i++) {
        var j = WNC_PS.jobs[i];
        try {
            var doc = app.documents.add(W, H, 72, j.id, NewDocumentMode.RGB, DocumentFill.WHITE);
            doc.artLayers[0].name = "Base (white)";
            if (j.background === "paper") { WNCPS.rectLayer(doc, "Paper tint", 0, 0, W, H, WNC_PS.brand.paper, 100); }
            if (j.image) { WNCPS.placeImage(doc, j.image, "Client photo \u2014 " + j.image_name, j.image_fit_w || W, j.image_fit_h || H, W / 2, j.image_cy || H / 2); }
            if (j.band) { WNCPS.gradientBand(doc, "Brand band", j.band[0], j.band[1], WNC_PS.brand.teal); }
            if (j.headline) { WNCPS.text(doc, "Headline (editable)", j.headline, WNC_PS.fonts.headline, j.headline_size || sx(92), j.headline_color || WNC_PS.brand.white, W / 2, j.headline_y || sy(1450)); }
            if (j.subline) { WNCPS.text(doc, "Subline (editable)", j.subline, WNC_PS.fonts.body, j.subline_size || sx(46), j.subline_color || WNC_PS.brand.white, W / 2, j.subline_y || sy(1600)); }
            if (WNC_PS.logo && j.logo !== false) {
                var lg = WNCPS.placeImage(doc, WNC_PS.logo, "Logo", j.logo_size || sx(200), j.logo_size || sx(200), W / 2, j.logo_y || sy(1780));
            }
            var psd = new File(WNC_PS.out_dir + "/" + j.id + ".psd");
            var o = new PhotoshopSaveOptions(); o.layers = true; o.embedColorProfile = true;
            doc.saveAs(psd, o, true);
            var png = new File(WNC_PS.out_dir + "/" + j.id + "_preview.png");
            var po = new PNGSaveOptions();
            doc.saveAs(png, po, true);
            doc.close(SaveOptions.DONOTSAVECHANGES);
            made.push(j.id);
        } catch (err) { WNCPS.log.push("FAILED " + j.id + ": " + err + " line " + err.line); }
    }
    app.preferences.rulerUnits = prevUnits;
    return "NHPS_RESULT|made=" + made.length + "|" + made.join(",") + "|log=" + WNCPS.log.join(" ; ");
};
