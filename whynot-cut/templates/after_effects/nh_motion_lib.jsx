/*  whynot-cut — After Effects motion library (ExtendScript, ES3).
    Renders a compiled motion-plan.json (frames and pixels decided by the engine) as a native AE project: one comp per
    scene, persistent layers and audio in MAIN_<reel id>, brand colours linked to BRAND_CONTROLS. Loaded after
    nh_ae_lib.jsx (helpers NH.*) by nh_ae_bridge.jsx, or embedded in a fallback script. Never writes files except
    app.project.save().
*/
var NHM = NHM || {};

/* ---------------------------------------------------------------- text and shape helpers (probe + build) */
NHM.dirName = function (v) {
    try {
        if (v === ParagraphDirection.DIRECTION_RIGHT_TO_LEFT) { return "RTL"; }
        if (v === ParagraphDirection.DIRECTION_LEFT_TO_RIGHT) { return "LTR"; }
    } catch (e) {}
    return (v === undefined || v === null) ? null : String(v);
};

NHM.setFont = function (td, ps, useObject) {
    if (useObject && app.fonts && app.fonts.getFontsByPostScriptName) {
        var arr = app.fonts.getFontsByPostScriptName(ps);
        if (arr && arr.length) { td.fontObject = arr[0]; return; }
    }
    td.font = ps;
};

/* o: {text, font, size, color, rtl, justify: "center"|"right"|"left", leading, caps}. Returns the direction read back. */
NHM.styleText = function (L, o) {
    var sp = L.property("ADBE Text Properties").property("ADBE Text Document");
    var td = sp.value, caps = o.caps || {};
    try { td.resetCharStyle(); td.resetParagraphStyle(); } catch (e0) {}
    td.text = o.text;
    NHM.setFont(td, o.font, caps.fontobject !== false);
    td.fontSize = o.size;
    td.applyFill = true;
    td.fillColor = o.color || [1, 1, 1];
    td.applyStroke = false;
    td.justification = o.justify === "right" ? ParagraphJustification.RIGHT_JUSTIFY :
        (o.justify === "left" ? ParagraphJustification.LEFT_JUSTIFY : ParagraphJustification.CENTER_JUSTIFY);
    if (o.leading) { try { td.autoLeading = false; td.leading = o.leading; } catch (eL) {} }
    if (o.rtl) {
        try { td.composerEngine = ComposerEngine.UNIVERSAL_TYPE_ENGINE; } catch (e1) {}
        if (caps.rtl_direction !== false) {
            try { td.direction = ParagraphDirection.DIRECTION_RIGHT_TO_LEFT; } catch (e2) {}
        }
    }
    sp.setValue(td);
    var rb = {direction_textdocument: null, direction_paragraph_range: null};
    if (o.rtl && caps.rtl_direction !== false) {
        rb.direction_textdocument = NHM.dirName(sp.value.direction);
        rb.direction_paragraph_range = rb.direction_textdocument;
        if (rb.direction_textdocument !== "RTL") {          // AE 25.2 dropped TextDocument.direction on setValue
            try {
                var t2 = sp.value;
                t2.paragraphRange(0).direction = ParagraphDirection.DIRECTION_RIGHT_TO_LEFT;
                sp.setValue(t2);
            } catch (e3) { rb.paragraph_error = String(e3); }
            try { rb.direction_paragraph_range = NHM.dirName(sp.value.paragraphRange(0).direction); } catch (e4) {}
        }
    }
    L.property("ADBE Transform Group").property("ADBE Anchor Point").expression =
        "var r=sourceRectAtTime(time,false);[r.left+r.width/2,r.top+r.height/2]";
    return rb;
};

NHM.readText = function (L) {
    var td = L.property("ADBE Text Properties").property("ADBE Text Document").value;
    var r = {text: td.text, font_ps: td.font, substitute: false, composer: null, direction: null};
    try { r.substitute = !!(td.fontObject && td.fontObject.isSubstitute); } catch (e) {}
    try { r.composer = (td.composerEngine === ComposerEngine.UNIVERSAL_TYPE_ENGINE) ? "UNIVERSAL" : "LATIN"; } catch (e2) {}
    try { r.direction = NHM.dirName(td.direction); } catch (e3) {}
    return r;
};

/* layer box in comp pixels [left, top, width, height] at time t (no parenting or rotation in our comps) */
NHM.compRect = function (L, t) {
    var r = L.sourceRectAtTime(t, false), tg = L.property("ADBE Transform Group");
    var a = tg.property("ADBE Anchor Point").valueAtTime(t, false), p = tg.property("ADBE Position").valueAtTime(t, false);
    var s = tg.property("ADBE Scale").valueAtTime(t, false), sx = s[0] / 100, sy = s[1] / 100;
    return [p[0] + (r.left - a[0]) * sx, p[1] + (r.top - a[1]) * sy, r.width * sx, r.height * sy];
};

/* word or line reveal synced to cue times (seconds); basedOn 3 = Words, 4 = Lines */
NHM.revealWords = function (L, cueSecs, basedOn, durS) {
    var an = L.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
    an.name = "Reveal";
    an.property("ADBE Text Animator Properties").addProperty("ADBE Text Opacity").setValue(0);
    var sel = an.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
    try { sel.property("ADBE Text Range Type2").setValue(basedOn); } catch (e) {}
    sel.property("ADBE Text Expressible Amount").expression = "var T=[" + cueSecs.join(",") +
        "];var t=T[Math.min(textIndex,T.length)-1];ease(time,t,t+" + durS + ",100,0)";
    return an;
};

/* fill colour on the given 1-based word indexes */
NHM.emphasisWords = function (L, idx, rgb, colorExpr) {
    var an = L.property("ADBE Text Properties").property("ADBE Text Animators").addProperty("ADBE Text Animator");
    an.name = "Emphasis";
    var fc = an.property("ADBE Text Animator Properties").addProperty("ADBE Text Fill Color");
    fc.setValue(rgb);
    if (colorExpr) { fc.expression = colorExpr; }
    var sel = an.property("ADBE Text Selectors").addProperty("ADBE Text Expressible Selector");
    try { sel.property("ADBE Text Range Type2").setValue(3); } catch (e) {}
    sel.property("ADBE Text Expressible Amount").expression =
        "var E=[" + idx.join(",") + "];var on=0;for(var i=0;i<E.length;i++){if(E[i]==textIndex){on=100;}}on";
    return an;
};

/* shape layer from engine subpaths {vertices, inTangents, outTangents, closed}; Trim Paths sits above the stroke */
NHM.shapeLayer = function (comp, name, shapes, o) {
    var L = comp.layers.addShape();
    L.name = name;
    var g = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
    g.name = "Icon";
    var v = g.property("ADBE Vectors Group");
    for (var i = 0; i < shapes.length; i++) {
        var s = new Shape();
        s.vertices = shapes[i].vertices; s.inTangents = shapes[i].inTangents;
        s.outTangents = shapes[i].outTangents; s.closed = shapes[i].closed;
        v.addProperty("ADBE Vector Shape - Group").property("ADBE Vector Shape").setValue(s);
    }
    var tr = v.addProperty("ADBE Vector Filter - Trim");
    var st = v.addProperty("ADBE Vector Graphic - Stroke");
    st.property("ADBE Vector Stroke Width").setValue(o.stroke || 6);
    st.property("ADBE Vector Stroke Color").setValue(o.color || [1, 1, 1]);
    if (o.colorExpr) { st.property("ADBE Vector Stroke Color").expression = o.colorExpr; }
    try {
        st.property("ADBE Vector Stroke Line Cap").setValue(2);
        st.property("ADBE Vector Stroke Line Join").setValue(2);
    } catch (e) {}
    return {layer: L, trim: tr, stroke: st};
};
