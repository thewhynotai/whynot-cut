/*  whynot-cut - After Effects graphics library (ExtendScript, ES3).
    Loaded by the generated build script, which defines `WNC_DATA` before including this file.
    Builds editable, brand-linked comps (the profile's frame size WNC_DATA.w x WNC_DATA.h, 1080x1920 by default; square
    pixels; the profile's frame rate: WNC_DATA.fps):
      * BRAND_CONTROLS comp with a "BRAND" null holding Color Controls; every fill/stroke links to it.
      * One comp per timeline event (template driven) + an optional CAPTIONS comp.
      * Adds every comp to the Render Queue (ProRes 4444 + alpha template) and saves the .aep.
    Requires NO file-write permission (does not use File.write).
*/
var WNC = WNC || {};

WNC.W = 1080; WNC.H = 1920; WNC.FPS = 24;   // defaults only: WNC.applyFrameSize() / WNC.applyFps() take WNC_DATA.w/h/fps
WNC.log = [];

WNC.rgb = function (a) { return [a[0], a[1], a[2]]; };
WNC.f2t = function (f) { return f / WNC.FPS; };

/* The comps' frame rate is the client's sequence rate, written into WNC_DATA.fps by the generator (3.0 T2.18):
   a 25 or 29.97 fps profile gets 25 / 29.97 fps comps. 24 only when the data carries none. */
WNC.applyFps = function () {
    var f = (typeof WNC_DATA !== "undefined" && WNC_DATA) ? WNC_DATA.fps : 0;
    WNC.FPS = (f > 0) ? f : 24;
    return WNC.FPS;
};

/* The comps' frame size is the client's sequence size, written into WNC_DATA.w / WNC_DATA.h by the generator (Gate 2
   A1): a 4:5 profile gets 1080x1350 comps. 1080x1920 when the data carries none (or a size that is not positive). */
WNC.applyFrameSize = function () {
    var d = (typeof WNC_DATA !== "undefined" && WNC_DATA) ? WNC_DATA : {};
    var ok = d.w > 0 && d.h > 0;
    WNC.W = ok ? d.w : 1080;
    WNC.H = ok ? d.h : 1920;
    return [WNC.W, WNC.H];
};

WNC.folder = function (name) {
    for (var i = 1; i <= app.project.numItems; i++) {
        var it = app.project.item(i);
        if (it instanceof FolderItem && it.name === name) { return it; }
    }
    return app.project.items.addFolder(name);
};

WNC.findComp = function (name) {
    for (var i = 1; i <= app.project.numItems; i++) {
        var it = app.project.item(i);
        if (it instanceof CompItem && it.name === name) { return it; }
    }
    return null;
};

WNC.ease = function (prop, infl) {
    infl = infl || 75;
    for (var k = 1; k <= prop.numKeys; k++) {
        var dims = 1;
        try { var v = prop.keyValue(k); if (v instanceof Array) { dims = v.length; } } catch (e) {}
        if (prop.propertyValueType === PropertyValueType.TwoD_SPATIAL || prop.propertyValueType === PropertyValueType.ThreeD_SPATIAL) { dims = 1; }
        var e1 = [], e2 = [];
        for (var d = 0; d < dims; d++) { e1.push(new KeyframeEase(0, infl)); e2.push(new KeyframeEase(0, infl)); }
        try { prop.setTemporalEaseAtKey(k, e1, e2); } catch (err) {}
    }
};

WNC.keys = function (prop, frames, values, infl) {
    for (var i = 0; i < frames.length; i++) { prop.setValueAtTime(WNC.f2t(frames[i]), values[i]); }
    WNC.ease(prop, infl);
};

WNC.BRAND_SCOPE = "project";   // "project" -> BRAND_CONTROLS comp; "local" -> BRAND null inside each comp (MOGRTs)
WNC.brandExpr = function (ctrl) {
    if (WNC.BRAND_SCOPE === "local") { return 'thisComp.layer("BRAND").effect("' + ctrl + '")("Color")'; }
    return 'comp("BRAND_CONTROLS").layer("BRAND").effect("' + ctrl + '")("Color")';
};

/* ---------------------------------------------------------------- brand controls */
WNC.buildBrand = function () {
    var c = WNC.findComp("BRAND_CONTROLS");
    if (c) { return c; }
    c = app.project.items.addComp("BRAND_CONTROLS", 400, 400, 1, 1, WNC.FPS);
    c.parentFolder = WNC.folder("NH_BRAND");
    var n = c.layers.addNull();
    n.name = "BRAND";
    var cols = WNC_DATA.brand.controls;
    for (var i = 0; i < cols.length; i++) {
        var fx = n.property("ADBE Effect Parade").addProperty("ADBE Color Control");
        fx.name = cols[i].name;
        fx.property(1).setValue(cols[i].rgb);
    }
    c.comment = "Edit brand colors here; all NH comps follow via expressions. Official: " + WNC_DATA.brand.official;
    return c;
};

/* ---------------------------------------------------------------- text */
WNC.text = function (comp, name, str, o) {
    var L = comp.layers.addText(str);
    L.name = name;
    var sp = L.property("ADBE Text Properties").property("ADBE Text Document");
    var td = sp.value;
    try { td.resetCharStyle(); td.resetParagraphStyle(); } catch (e0) {}
    td.text = str;
    td.font = o.font || WNC_DATA.fonts.body;
    td.fontSize = o.size || 56;
    td.applyFill = true;
    td.fillColor = o.color || [1, 1, 1];
    td.applyStroke = false;
    td.justification = ParagraphJustification.CENTER_JUSTIFY;
    if (o.leading) { try { td.autoLeading = false; td.leading = o.leading; } catch (e1) {} }
    if (o.tracking !== undefined) { td.tracking = o.tracking; }
    // Arabic: Universal (Middle-Eastern) composer + RTL paragraph direction (AE 24.0+ scripting API)
    if (o.rtl !== false) {
        try { td.composerEngine = ComposerEngine.UNIVERSAL_TYPE_ENGINE; } catch (e2) { WNC.log.push("composerEngine not settable"); }
        try { td.direction = ParagraphDirection.DIRECTION_RIGHT_TO_LEFT; } catch (e3) { WNC.log.push("direction not settable"); }
    }
    if (o.boxW) {  // paragraph text for wrapping
        L.remove();
        L = comp.layers.addBoxText([o.boxW, o.boxH || 600], str);
        L.name = name;
        sp = L.property("ADBE Text Properties").property("ADBE Text Document");
        var td2 = sp.value;
        td2.text = str; td2.font = td.font; td2.fontSize = td.fontSize; td2.applyFill = true;
        td2.fillColor = td.fillColor; td2.justification = ParagraphJustification.CENTER_JUSTIFY;
        if (o.leading) { try { td2.autoLeading = false; td2.leading = o.leading; } catch (e4) {} }
        if (o.rtl !== false) {
            try { td2.composerEngine = ComposerEngine.UNIVERSAL_TYPE_ENGINE; } catch (e5) {}
            try { td2.direction = ParagraphDirection.DIRECTION_RIGHT_TO_LEFT; } catch (e6) {}
        }
        sp.setValue(td2);
    } else {
        sp.setValue(td);
    }
    if (o.colorCtrl) {
        try { sp.expression = 'text.sourceText.style.setFillColor(' + WNC.brandExpr(o.colorCtrl) + ')'; } catch (e7) {}
    }
    // anchor to visual centre so scale animations stay centred
    L.property("ADBE Transform Group").property("ADBE Anchor Point").expression =
        'var r=sourceRectAtTime(time,false);[r.left+r.width/2,r.top+r.height/2]';
    L.property("ADBE Transform Group").property("ADBE Position").setValue([o.x || WNC.W / 2, o.y || WNC.H / 2]);
    if (o.shadow !== false) { WNC.shadow(L, 0.35, 8, 18); }
    return L;
};

WNC.shadow = function (L, op, dist, soft) {
    try {
        var ds = L.property("ADBE Effect Parade").addProperty("ADBE Drop Shadow");
        ds.property("ADBE Drop Shadow-0002").setValue(op * 255);   // opacity (0-255)
        ds.property("ADBE Drop Shadow-0003").setValue(135);         // direction
        ds.property("ADBE Drop Shadow-0004").setValue(dist);        // distance
        ds.property("ADBE Drop Shadow-0005").setValue(soft);        // softness
    } catch (e) {}
};

/* ---------------------------------------------------------------- shapes */
WNC.rect = function (comp, name, size, pos, o) {
    var L = comp.layers.addShape();
    L.name = name;
    var g = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
    g.name = "Box";
    var v = g.property("ADBE Vectors Group");
    var r = v.addProperty("ADBE Vector Shape - Rect");
    r.property("ADBE Vector Rect Size").setValue(size);
    r.property("ADBE Vector Rect Roundness").setValue(o.radius || 0);
    if (o.sizeExpr) { r.property("ADBE Vector Rect Size").expression = o.sizeExpr; }
    if (o.fillCtrl || o.fill) {
        var f = v.addProperty("ADBE Vector Graphic - Fill");
        f.property("ADBE Vector Fill Color").setValue(o.fill || [1, 1, 1]);
        if (o.fillCtrl) { f.property("ADBE Vector Fill Color").expression = WNC.brandExpr(o.fillCtrl); }
        f.property("ADBE Vector Fill Opacity").setValue((o.fillOpacity === undefined ? 1 : o.fillOpacity) * 100);
    }
    if (o.strokeCtrl || o.stroke) {
        var s = v.addProperty("ADBE Vector Graphic - Stroke");
        s.property("ADBE Vector Stroke Color").setValue(o.stroke || [1, 1, 1]);
        if (o.strokeCtrl) { s.property("ADBE Vector Stroke Color").expression = WNC.brandExpr(o.strokeCtrl); }
        s.property("ADBE Vector Stroke Width").setValue(o.strokeWidth || 2);
        s.property("ADBE Vector Stroke Opacity").setValue((o.strokeOpacity === undefined ? 1 : o.strokeOpacity) * 100);
    }
    if (o.rtlSweep) {  // anchor group at its RIGHT edge so scaleX 0->100 grows right-to-left
        var gt = g.property("ADBE Vector Transform Group");
        var se = 'var s=content("Box").content("Rectangle Path 1").size;[s[0]/2,0]';
        gt.property("ADBE Vector Anchor").expression = se;
        gt.property("ADBE Vector Position").expression = se;
    }
    L.property("ADBE Transform Group").property("ADBE Position").setValue(pos);
    return L;
};

WNC.ellipse = function (comp, name, d, pos, ctrl, width) {
    var L = comp.layers.addShape();
    L.name = name;
    var g = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
    var v = g.property("ADBE Vectors Group");
    v.addProperty("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size").setValue([d, d]);
    var s = v.addProperty("ADBE Vector Graphic - Stroke");
    s.property("ADBE Vector Stroke Width").setValue(width || 3);
    s.property("ADBE Vector Stroke Color").expression = WNC.brandExpr(ctrl || "Brand White");
    L.property("ADBE Transform Group").property("ADBE Position").setValue(pos);
    return L;
};

WNC.glassIcon = function (comp, pos) {  // small glass cube seen in references
    var a = WNC.rect(comp, "GlassIcon_back", [44, 44], [pos[0] + 8, pos[1] - 8], {radius: 8, strokeCtrl: "Brand White", strokeWidth: 3, strokeOpacity: 0.8});
    var b = WNC.rect(comp, "GlassIcon_front", [44, 44], pos, {radius: 8, fillCtrl: "Brand White", fillOpacity: 0.25, strokeCtrl: "Brand White", strokeWidth: 3});
    a.property("ADBE Transform Group").property("ADBE Rotate Z").setValue(-12);
    b.property("ADBE Transform Group").property("ADBE Rotate Z").setValue(-12);
    return [a, b];
};

WNC.footage = function (path) {
    var key = "NH_IMG::" + path;
    for (var i = 1; i <= app.project.numItems; i++) {
        var it = app.project.item(i);
        if (it instanceof FootageItem && it.comment === key) { return it; }
    }
    var f = new File(path);
    if (!f.exists) { WNC.log.push("missing image " + path); return null; }
    var item = app.project.importFile(new ImportOptions(f));
    item.comment = key;
    item.parentFolder = WNC.folder("NH_ASSETS");
    return item;
};

WNC.roundMask = function (L, w, h, radius, focusY) {
    // rounded-rect mask centred on a focus point of the source (default: 32% from top = face height
    // in portrait photos); the anchor point moves there too so the layer is positioned by the face.
    var src = L.source;
    var fy = (focusY === undefined) ? 0.32 : focusY;
    var cx = src.width / 2, cy = Math.min(Math.max(src.height * fy, h / 2), src.height - h / 2);
    L.property("ADBE Transform Group").property("ADBE Anchor Point").setValue([cx, cy]); hw = w / 2, hh = h / 2, r = radius, k = 0.5523 * r;
    var shp = new Shape();
    shp.vertices = [[cx - hw + r, cy - hh], [cx + hw - r, cy - hh], [cx + hw, cy - hh + r], [cx + hw, cy + hh - r],
                    [cx + hw - r, cy + hh], [cx - hw + r, cy + hh], [cx - hw, cy + hh - r], [cx - hw, cy - hh + r]];
    shp.inTangents = [[-k, 0], [0, 0], [0, -k], [0, 0], [k, 0], [0, 0], [0, k], [0, 0]];
    shp.outTangents = [[0, 0], [k, 0], [0, 0], [0, k], [0, 0], [-k, 0], [0, 0], [0, -k]];
    shp.closed = true;
    var m = L.property("ADBE Mask Parade").addProperty("ADBE Mask Atom");
    m.property("ADBE Mask Shape").setValue(shp);
    return m;
};

WNC.fadeInOut = function (L, n, inF, outF) {
    var op = L.property("ADBE Transform Group").property("ADBE Opacity");
    var fr = [0, inF], va = [0, 100];
    if (outF > 0) { fr.push(n - outF, n); va.push(100, 0); }
    WNC.keys(op, fr, va);
};

WNC.popScale = function (L, n, inF, outF, from) {
    var sc = L.property("ADBE Transform Group").property("ADBE Scale");
    var a = from || 85;
    var fr = [0, inF], va = [[a, a], [100, 100]];
    if (outF > 0) { fr.push(n - outF, n); va.push([100, 100], [96, 96]); }
    WNC.keys(sc, fr, va, 80);
};

/* ---------------------------------------------------------------- templates */
WNC.T = {};

WNC.T.hook_title = function (c, ev, t, n) {
    var p = ev.params, y = p.y || t.y;
    var bar = WNC.rect(c, "Bar", [100, 20], [WNC.W / 2, y], {fillCtrl: "Brand Teal", radius: 4, rtlSweep: true,
        sizeExpr: 'var r=thisComp.layer("Title").sourceRectAtTime(time,false);[r.width+48, r.height*0.42]'});
    bar.property("ADBE Transform Group").property("ADBE Position").expression =
        'var L=thisComp.layer("Title");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height*0.80])';
    var tx = WNC.text(c, "Title", p.text, {font: WNC_DATA.fonts.headline, size: p.size || t.size, y: y, leading: (p.size || t.size) * 1.25});
    var sc = bar.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Scale");
    WNC.keys(sc, [2, 2 + 6], [[0, 100], [100, 100]]);
    WNC.popScale(tx, n, t.in_frames, t.out_frames, 80);
    WNC.fadeInOut(tx, n, t.in_frames, t.out_frames);
    WNC.fadeInOut(bar, n, 2, t.out_frames);
};

WNC.T.term_callout = function (c, ev, t, n) {
    var p = ev.params, y = p.y || t.y, rtl = !p.latin;
    var tx = WNC.text(c, "Term", p.text, {font: WNC_DATA.fonts.term, size: p.size || t.size, y: y, rtl: rtl});
    var bar = WNC.rect(c, "Underline", [100, 8], [WNC.W / 2, y], {fillCtrl: "Brand Teal", radius: 4, rtlSweep: rtl,
        sizeExpr: 'var r=thisComp.layer("Term").sourceRectAtTime(time,false);[r.width+20, 8]'});
    bar.property("ADBE Transform Group").property("ADBE Position").expression =
        'var L=thisComp.layer("Term");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height+14])';
    WNC.keys(bar.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Scale"),
            [3, 3 + 6], [[0, 100], [100, 100]]);
    WNC.popScale(tx, n, t.in_frames, t.out_frames, 90);
    WNC.fadeInOut(tx, n, t.in_frames, t.out_frames);
    WNC.fadeInOut(bar, n, 3, t.out_frames);
};

WNC.T.glass_card = function (c, ev, t, n) {
    var p = ev.params, y = p.y || t.y, w = p.w || t.w;
    var tx = WNC.text(c, "Statement", p.text, {font: WNC_DATA.fonts.body, size: p.size || t.size, y: y,
        leading: (p.size || t.size) * 1.35, shadow: false});
    var card = WNC.rect(c, "Card", [w, 300], [WNC.W / 2, y], {radius: t.radius, fillCtrl: "Brand White", fillOpacity: t.fill_opacity,
        strokeCtrl: "Brand White", strokeOpacity: t.stroke_opacity, strokeWidth: 2.5,
        sizeExpr: 'var r=thisComp.layer("Statement").sourceRectAtTime(time,false);[' + w + ', r.height+90]'});
    card.property("ADBE Transform Group").property("ADBE Position").expression =
        'var L=thisComp.layer("Statement");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height/2])';
    card.moveAfter(tx);
    WNC.shadow(card, 0.25, 6, 40);
    var ic = WNC.glassIcon(c, [WNC.W / 2 + w / 2 - 10, y - 150]);
    ic[0].property("ADBE Transform Group").property("ADBE Position").expression =
        'var C=thisComp.layer("Card");var s=C.content("Box").content("Rectangle Path 1").size;C.toComp([s[0]/2-2,-s[1]/2+6])';
    ic[1].property("ADBE Transform Group").property("ADBE Position").expression =
        'var C=thisComp.layer("Card");var s=C.content("Box").content("Rectangle Path 1").size;C.toComp([s[0]/2-10,-s[1]/2+14])';
    var all = [tx, card, ic[0], ic[1]];
    for (var i = 0; i < all.length; i++) { WNC.fadeInOut(all[i], n, t.in_frames, t.out_frames); }
    var pos = card.property("ADBE Transform Group").property("ADBE Scale");
    WNC.keys(pos, [0, t.in_frames], [[94, 94], [100, 100]]);
    c.comment = "Frosted blur: in Premiere add an Adjustment Layer under this clip with Gaussian Blur 40 masked to the card (see handoff).";
};

WNC.T.checklist = function (c, ev, t, n) {
    var p = ev.params, y0 = p.y || t.y, gap = p.line_gap || t.line_gap;
    var items = p.items || [];
    var top = y0 - ((items.length - 1) * gap) / 2;
    if (p.title) {
        var tt = WNC.text(c, "Title", p.title, {font: WNC_DATA.fonts.body, size: t.title_size, y: top - gap * 1.1});
        WNC.fadeInOut(tt, n, t.item_in_frames, 5);
    }
    for (var i = 0; i < items.length; i++) {
        var it = items[i], f0 = Math.max(0, it.rel_frame), y = top + i * gap;
        var tx = WNC.text(c, "Item_" + (i + 1), it.text, {font: WNC_DATA.fonts.body, size: t.size, x: WNC.W / 2 - 20, y: y, rtl: !it.latin});
        var dot = WNC.ellipse(c, "Bullet_" + (i + 1), 26, [WNC.W / 2 + 300, y], "Brand White", 3);
        dot.property("ADBE Transform Group").property("ADBE Position").expression =
            'var L=thisComp.layer("Item_' + (i + 1) + '");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width+30,r.top+r.height/2])';
        var lay = [tx, dot];
        for (var k = 0; k < lay.length; k++) {
            var op = lay[k].property("ADBE Transform Group").property("ADBE Opacity");
            WNC.keys(op, [f0, f0 + t.item_in_frames, n - 5, n], [0, 100, 100, 0]);
        }
        var ps = tx.property("ADBE Transform Group").property("ADBE Position");
        WNC.keys(ps, [f0, f0 + t.item_in_frames], [[WNC.W / 2 + 40, y], [WNC.W / 2 - 20, y]]);
    }
};

WNC.T.broll_card = function (c, ev, t, n) {
    var p = ev.params;
    var bg = c.layers.addSolid([1, 1, 1], "Paper_BG", WNC.W, WNC.H, 1);
    var fill = bg.property("ADBE Effect Parade").addProperty("ADBE Fill");
    fill.property("ADBE Fill-0002").expression = WNC.brandExpr("Brand Paper");
    try {
        var noise = c.layers.addSolid([0.5, 0.5, 0.5], "Paper_Texture", WNC.W, WNC.H, 1);
        noise.property("ADBE Effect Parade").addProperty("ADBE Fractal Noise");
        noise.blendingMode = BlendingMode.SOFT_LIGHT;
        noise.property("ADBE Transform Group").property("ADBE Opacity").setValue(18);
    } catch (e) {}
    var hd = WNC.text(c, "Headline", p.headline || p.text, {font: WNC_DATA.fonts.body, size: p.size || t.size,
        y: t.headline_y, colorCtrl: "Brand Ink", color: [0.12, 0.2, 0.2], shadow: false,
        leading: (p.size || t.size) * 1.3});
    if (p.image_path) {
        var item = WNC.footage(p.image_path);
        if (item) {
            var L = c.layers.add(item);
            L.name = "Image";
            var s = Math.max(t.card_w / item.width, t.card_h / item.height) * 100;
            L.property("ADBE Transform Group").property("ADBE Scale").setValue([s, s]);
            WNC.roundMask(L, t.card_w / (s / 100), t.card_h / (s / 100), 40 / (s / 100), p.focus_y);
            L.property("ADBE Transform Group").property("ADBE Position").setValue([WNC.W / 2, t.card_y]);
            WNC.shadow(L, 0.3, 14, 50);
            WNC.keys(L.property("ADBE Transform Group").property("ADBE Scale"), [0, n], [[s * 0.96, s * 0.96], [s * 1.02, s * 1.02]], 33);
            WNC.fadeInOut(L, n, t.in_frames + 2, 0);
        }
    } else if (p.placeholder) {
        var ph = WNC.rect(c, "IMAGE_PLACEHOLDER (needs approved visual)", [t.card_w, t.card_h], [WNC.W / 2, t.card_y],
            {radius: 40, strokeCtrl: "Brand Teal", strokeWidth: 4, fillCtrl: "Brand White", fillOpacity: 0.5});
    }
    WNC.fadeInOut(hd, n, t.in_frames, 0);
    WNC.keys(hd.property("ADBE Transform Group").property("ADBE Position"), [0, t.in_frames + 4],
            [[WNC.W / 2, t.headline_y + 30], [WNC.W / 2, t.headline_y]]);
};

WNC.T.photo_card = function (c, ev, t, n) {
    var p = ev.params, item = WNC.footage(p.image_path);
    if (item) {
        var L = c.layers.add(item);
        L.name = "Photo";
        var s = Math.max(t.card_w / item.width, t.card_h / item.height) * 100;
        L.property("ADBE Transform Group").property("ADBE Scale").setValue([s, s]);
        WNC.roundMask(L, t.card_w / (s / 100), t.card_h / (s / 100), 36 / (s / 100), p.focus_y);
        L.property("ADBE Transform Group").property("ADBE Position").setValue([WNC.W / 2, t.card_y]);
        WNC.shadow(L, 0.35, 16, 60);
        WNC.fadeInOut(L, n, t.in_frames, t.out_frames);
        WNC.keys(L.property("ADBE Transform Group").property("ADBE Scale"), [0, t.in_frames, n], [[s * 0.9, s * 0.9], [s, s], [s * 1.03, s * 1.03]]);
        var fr = WNC.rect(c, "Frame", [t.card_w, t.card_h], [WNC.W / 2, t.card_y], {radius: 36, strokeCtrl: "Brand White", strokeWidth: 4});
        WNC.fadeInOut(fr, n, t.in_frames, t.out_frames);
    }
    if (p.text) {
        var tx = WNC.text(c, "Caption", p.text, {font: WNC_DATA.fonts.body, size: t.size, y: t.card_y + t.card_h / 2 + 90});
        WNC.fadeInOut(tx, n, t.in_frames + 4, t.out_frames);
    }
    if (WNC_DATA.logo) {
        var lg = WNC.footage(WNC_DATA.logo);
        if (lg) {
            var LL = c.layers.add(lg); LL.name = "Logo";
            LL.property("ADBE Transform Group").property("ADBE Scale").setValue([16, 16]);
            LL.property("ADBE Transform Group").property("ADBE Position").setValue([WNC.W / 2, t.card_y - t.card_h / 2 - 70]);
            WNC.fadeInOut(LL, n, t.in_frames + 6, t.out_frames);
        }
    }
};

WNC.T.name_card = function (c, ev, t, n) {
    var p = ev.params, y = p.y || t.y, w = p.w || t.w, lines = p.lines || [];
    var nm = WNC.text(c, "Name", p.name, {font: WNC_DATA.fonts.headline, size: t.name_size, y: y - 70});
    var box = WNC.rect(c, "Card", [w, 250], [WNC.W / 2, y], {radius: 26, fillCtrl: "Brand White", fillOpacity: 0.12,
        strokeCtrl: "Brand White", strokeOpacity: 0.85, strokeWidth: 2.5});
    var rule1 = WNC.rect(c, "Rule_1", [w - 160, 2], [WNC.W / 2, y - 25], {fillCtrl: "Brand White", fillOpacity: 0.8, rtlSweep: true});
    var lay = [nm, box, rule1];
    for (var i = 0; i < lines.length; i++) {
        lay.push(WNC.text(c, "Line_" + (i + 1), lines[i], {font: WNC_DATA.fonts.small, size: t.line_size, y: y + 22 + i * 50}));
    }
    for (var k = 0; k < lay.length; k++) { WNC.fadeInOut(lay[k], n, t.in_frames, t.out_frames); }
    WNC.keys(rule1.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Scale"),
            [4, 4 + 10], [[0, 100], [100, 100]]);
    WNC.keys(box.property("ADBE Transform Group").property("ADBE Scale"), [0, t.in_frames], [[96, 96], [100, 100]]);
};

WNC.T.cta = function (c, ev, t, n) {
    var p = ev.params, y = p.y || t.y;
    var tx = WNC.text(c, "CTA", p.text, {font: WNC_DATA.fonts.headline, size: p.size || t.size, y: y, shadow: false});
    var pill = WNC.rect(c, "Pill", [600, 110], [WNC.W / 2, y], {radius: 55, fillCtrl: "Brand Teal",
        sizeExpr: 'var r=thisComp.layer("CTA").sourceRectAtTime(time,false);[r.width+90, r.height+44]'});
    pill.property("ADBE Transform Group").property("ADBE Position").expression =
        'var L=thisComp.layer("CTA");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height/2])';
    pill.moveAfter(tx);
    WNC.shadow(pill, 0.3, 8, 30);
    WNC.popScale(pill, n, t.in_frames, t.out_frames, 70);
    WNC.fadeInOut(pill, n, t.in_frames, t.out_frames);
    WNC.fadeInOut(tx, n, t.in_frames + 2, t.out_frames);
};

WNC.T.logo_outro = function (c, ev, t, n) {
    var bg = c.layers.addSolid([1, 1, 1], "BG", WNC.W, WNC.H, 1);
    bg.property("ADBE Effect Parade").addProperty("ADBE Fill").property("ADBE Fill-0002").expression = WNC.brandExpr("Brand White");
    WNC.fadeInOut(bg, n, t.in_frames, 0);
    if (WNC_DATA.logo) {
        var lg = WNC.footage(WNC_DATA.logo);
        if (lg) {
            var L = c.layers.add(lg); L.name = "Logo";
            WNC.keys(L.property("ADBE Transform Group").property("ADBE Scale"), [0, t.in_frames + 6, n], [[60, 60], [72, 72], [75, 75]]);
            WNC.fadeInOut(L, n, t.in_frames + 2, 0);
        }
    }
};

WNC.T.flash_transition = function (c, ev, t, n) {
    var s = c.layers.addSolid([1, 1, 1], "Flash", WNC.W, WNC.H, 1);
    var pk = Math.max(1, Math.round(n / 2));
    WNC.keys(s.property("ADBE Transform Group").property("ADBE Opacity"), [0, pk, n], [0, (t.peak_opacity || 0.9) * 100, 0]);
};

/* ---------------------------------------------------------------- captions */
WNC.buildCaptions = function (cap) {
    var name = "CAPTIONS";
    var old = WNC.findComp(name);
    if (old) { old.remove(); }
    var c = app.project.items.addComp(name, WNC.W, WNC.H, 1, cap.duration_frames / WNC.FPS, WNC.FPS);
    c.parentFolder = WNC.folder("NH_CAPTIONS");
    c.comment = "Animated social captions from captions-short.srt (verify text against subtitle-review.md).";
    for (var i = 0; i < cap.cues.length; i++) {
        var q = cap.cues[i];
        var nm = "CAP_" + (i + 1);
        var tx = WNC.text(c, nm, q.text, {font: WNC_DATA.fonts.caption, size: cap.size, y: cap.y, leading: cap.size * 1.25});
        tx.inPoint = WNC.f2t(q.start_frame); tx.outPoint = WNC.f2t(q.end_frame);
        if (q.highlight) {
            var bar = WNC.rect(c, nm + "_HL", [100, 80], [WNC.W / 2, cap.y], {fillCtrl: "Brand Teal", radius: 6, rtlSweep: true,
                sizeExpr: 'var r=thisComp.layer("' + nm + '").sourceRectAtTime(time,false);[r.width+44, r.height+16]'});
            bar.property("ADBE Transform Group").property("ADBE Position").expression =
                'var L=thisComp.layer("' + nm + '");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height/2])';
            bar.moveAfter(tx);
            bar.inPoint = tx.inPoint; bar.outPoint = tx.outPoint;
            WNC.keys(bar.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group").property("ADBE Vector Scale"),
                    [q.start_frame, q.start_frame + 5], [[0, 100], [100, 100]]);
        } else {
            WNC.keys(tx.property("ADBE Transform Group").property("ADBE Scale"), [q.start_frame, q.start_frame + 3], [[92, 92], [100, 100]]);
        }
    }
    return c;
};

/* ---------------------------------------------------------------- main */
WNC.queue = function (comp, outPath) {
    var rq = app.project.renderQueue.items.add(comp);
    var om = rq.outputModule(1);
    var tplName = WNC_DATA.render_template;
    try { om.applyTemplate(tplName); } catch (e) { WNC.log.push("output template '" + tplName + "' missing: " + e); }
    om.file = new File(outPath);
    return rq;
};

WNC.build = function () {
    WNC.applyFps();
    WNC.applyFrameSize();
    app.beginUndoGroup("NH build");
    if (WNC_DATA.new_project) { app.newProject(); }
    WNC.buildBrand();
    var made = [];
    var tpls = WNC_DATA.templates;
    for (var i = 0; i < WNC_DATA.events.length; i++) {
        var ev = WNC_DATA.events[i];
        var n = ev.end_frame - ev.start_frame;
        var old = WNC.findComp(ev.event_id);
        if (old) { old.remove(); }
        var c = app.project.items.addComp(ev.event_id, WNC.W, WNC.H, 1, n / WNC.FPS, WNC.FPS);
        c.parentFolder = WNC.folder("NH_COMPS");
        c.comment = ev.template + " | " + (ev.evidence || "") + " | seq " + ev.start_tc + "-" + ev.end_tc;
        try {
            WNC.T[ev.template](c, ev, tpls[ev.template], n);
            made.push(ev.event_id);
            WNC.queue(c, WNC_DATA.render_dir + "/" + ev.event_id + ".mov");
        } catch (err) {
            WNC.log.push("FAILED " + ev.event_id + ": " + err.toString() + " line " + err.line);
        }
    }
    if (WNC_DATA.captions) {
        try {
            var cc = WNC.buildCaptions(WNC_DATA.captions);
            WNC.queue(cc, WNC_DATA.render_dir + "/CAPTIONS.mov");
            made.push("CAPTIONS");
        } catch (err2) { WNC.log.push("FAILED CAPTIONS: " + err2.toString() + " line " + err2.line); }
    }
    app.endUndoGroup();
    app.project.save(new File(WNC_DATA.aep_path));
    return "NH_RESULT|made=" + made.length + "|" + made.join(",") + "|log=" + WNC.log.join(" ; ");
};


/* ================================================================ MOGRT authoring
   Builds one Essential Graphics template per text template, exported to .mogrt for Premiere.
   - local BRAND null with colour controls (exposed as Essential Properties)
   - main text layers exposed as editable text
   - protected intro/outro regions so Premiere can stretch the middle to any duration       */
WNC.addLocalBrand = function (c) {
    var n = c.layers.addNull();
    n.name = "BRAND";
    n.enabled = false;
    var cols = WNC_DATA.brand.controls;
    for (var i = 0; i < cols.length; i++) {
        var fx = n.property("ADBE Effect Parade").addProperty("ADBE Color Control");
        fx.name = cols[i].name;
        fx.property(1).setValue(cols[i].rgb);
    }
    return n;
};

WNC.expose = function (c, layerName, label, kind) {
    var L = c.layer(layerName);
    if (!L) { WNC.log.push("expose: no layer " + layerName + " in " + c.name); return; }
    var prop = (kind === "color") ? L.property("ADBE Effect Parade").property(label.replace("Colour: ", "")).property(1)
                                  : L.property("ADBE Text Properties").property("ADBE Text Document");
    try { prop.addToMotionGraphicsTemplateAs(c, label); } catch (e) { WNC.log.push("expose failed " + label + ": " + e); }
};

WNC.protect = function (c, inF, outF, n) {
    var mp = c.markerProperty;
    var a = new MarkerValue("intro (protected)"); a.duration = inF / WNC.FPS; a.protectedRegion = true;
    mp.setValueAtTime(0, a);
    if (outF > 0) {
        var b = new MarkerValue("outro (protected)"); b.duration = outF / WNC.FPS; b.protectedRegion = true;
        mp.setValueAtTime((n - outF) / WNC.FPS, b);
    }
};

WNC.MOGRT_SPECS = {
    hook_title:   {sample: {text: "\u0633\u0624\u0627\u0644 \u0627\u0644\u062d\u0644\u0642\u0629\r\u0647\u0646\u0627"}, expose: [["Title", "Text"]]},
    term_callout: {sample: {text: "Medical Term", latin: true}, expose: [["Term", "Text"]]},
    glass_card:   {sample: {text: "\u062c\u0645\u0644\u0629 \u0645\u0647\u0645\u0629 \u0645\u0646 \u0643\u0644\u0627\u0645\u0647\u0627\r\u0641\u064a \u0633\u0637\u0631\u064a\u0646"}, expose: [["Statement", "Text"]]},
    name_card:    {sample: {name: "\u0627\u0644\u0627\u0633\u0645 \u0647\u0646\u0627", lines: ["\u0627\u0644\u0633\u0637\u0631 \u0627\u0644\u0623\u0648\u0644", "\u0627\u0644\u0633\u0637\u0631 \u0627\u0644\u062b\u0627\u0646\u064a"]},
                   expose: [["Name", "Name"], ["Line_1", "Line 1"], ["Line_2", "Line 2"]]},
    cta:          {sample: {text: "\u0627\u0643\u062a\u0628\u0648\u0644\u064a \u0641\u064a \u0627\u0644\u0643\u0648\u0645\u0646\u062a\u0633"}, expose: [["CTA", "Text"]]}
};

WNC.buildChecklistMogrt = function (c, t, n) {
    // 5 slots; each item's reveal time is a slider (seconds from clip start) -> per-video timing in Premiere
    var top = t.y - 2 * t.line_gap;
    var ctl = c.layers.addNull(); ctl.name = "TIMING"; ctl.enabled = false;
    var tt = WNC.text(c, "Title", "\u0639\u0646\u0648\u0627\u0646 \u0627\u0644\u0642\u0627\u0626\u0645\u0629", {font: WNC_DATA.fonts.body, size: t.title_size, y: top - t.line_gap * 1.1});
    tt.property("ADBE Transform Group").property("ADBE Opacity").expression = 'linear(time,0,5/24,0,100)*linear(time,thisComp.duration-5/24,thisComp.duration,1,0)';
    for (var i = 1; i <= 5; i++) {
        var sl = ctl.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
        sl.name = "Item " + i + " In (s)";
        sl.property(1).setValue(0.3 + (i - 1) * 0.8);
        var y = top + (i - 1) * t.line_gap;
        var tx = WNC.text(c, "Item_" + i, i <= 3 ? ("\u0628\u0646\u062f \u0631\u0642\u0645 " + i) : "", {font: WNC_DATA.fonts.body, size: t.size, x: WNC.W / 2 - 20, y: y});
        var dot = WNC.ellipse(c, "Bullet_" + i, 26, [WNC.W / 2 + 300, y], "Brand White", 3);
        dot.property("ADBE Transform Group").property("ADBE Position").expression =
            'var L=thisComp.layer("Item_' + i + '");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width+30,r.top+r.height/2])';
        var vis = 'var s=thisComp.layer("TIMING").effect("Item ' + i + ' In (s)")(1);' +
                  'var has=thisComp.layer("Item_' + i + '").text.sourceText.length>0;' +
                  '(has?1:0)*linear(time,s,s+5/24,0,100)*linear(time,thisComp.duration-5/24,thisComp.duration,1,0)';
        tx.property("ADBE Transform Group").property("ADBE Opacity").expression = vis;
        dot.property("ADBE Transform Group").property("ADBE Opacity").expression = vis.replace('Item_' + i + '").text', 'Item_' + i + '").text');
        tx.property("ADBE Transform Group").property("ADBE Position").expression =
            'var s=thisComp.layer("TIMING").effect("Item ' + i + ' In (s)")(1);value+[ease(time,s,s+5/24,60,0),0]';
    }
    c.layer("Title").property("ADBE Text Properties").property("ADBE Text Document").addToMotionGraphicsTemplateAs(c, "Title");
    for (var k = 1; k <= 5; k++) {
        c.layer("Item_" + k).property("ADBE Text Properties").property("ADBE Text Document").addToMotionGraphicsTemplateAs(c, "Item " + k);
        c.layer("TIMING").property("ADBE Effect Parade").property("Item " + k + " In (s)").property(1).addToMotionGraphicsTemplateAs(c, "Item " + k + " In (s)");
    }
};

WNC.buildMogrts = function () {
    WNC.applyFps();
    WNC.applyFrameSize();
    app.beginUndoGroup("NH mogrts");
    if (WNC_DATA.new_project) { app.newProject(); }
    WNC.BRAND_SCOPE = "local";
    var made = [], tpls = WNC_DATA.templates, dur = WNC_DATA.mogrt_frames || Math.round(4 * WNC.FPS);   // 4 s at the profile rate
    var names = ["hook_title", "term_callout", "glass_card", "name_card", "cta", "checklist"];
    for (var i = 0; i < names.length; i++) {
        var key = names[i], t = tpls[key];
        try {
            var c = app.project.items.addComp("NH_" + key, WNC.W, WNC.H, 1, dur / WNC.FPS, WNC.FPS);
            c.parentFolder = WNC.folder("NH_MOGRT");
            WNC.addLocalBrand(c);
            if (key === "checklist") {
                WNC.buildChecklistMogrt(c, t, dur);
            } else {
                var spec = WNC.MOGRT_SPECS[key];
                WNC.T[key](c, {params: spec.sample}, t, dur);
                for (var e = 0; e < spec.expose.length; e++) { WNC.expose(c, spec.expose[e][0], spec.expose[e][1]); }
            }
            var br = c.layer("BRAND").property("ADBE Effect Parade");
            try { br.property("Brand Teal").property(1).addToMotionGraphicsTemplateAs(c, "Brand Teal"); } catch (e1) {}
            try { br.property("Brand White").property(1).addToMotionGraphicsTemplateAs(c, "Brand White"); } catch (e2) {}
            WNC.protect(c, t.in_frames || t.item_in_frames || 6, t.out_frames === undefined ? 5 : t.out_frames, dur);
            // AE writes "<motionGraphicsTemplateName>.mogrt" INTO the given folder; names with
            // several spaces were truncated/failed in AE 2026, so keep names space-free.
            c.motionGraphicsTemplateName = "NH_" + key;
            var ok = c.exportAsMotionGraphicsTemplate(true, new Folder(WNC_DATA.mogrt_dir).fsName);
            made.push(key + (ok ? "" : "(export=false)"));
        } catch (err) { WNC.log.push("FAILED mogrt " + key + ": " + err + " line " + err.line); }
    }
    app.endUndoGroup();
    app.project.save(new File(WNC_DATA.aep_path));
    return "NH_MOGRT|made=" + made.length + "|" + made.join(",") + "|log=" + WNC.log.join(" ; ");
};
