/*  whynot-cut - After Effects motion library (ExtendScript, ES3).
    Renders a compiled motion-plan.json (frames and pixels decided by the engine) as a native AE project: one comp per
    scene, persistent layers and audio in MAIN_<reel id>, brand colours linked to BRAND_CONTROLS. Loaded after
    wnc_ae_lib.jsx (helpers WNC.*) by wnc_ae_bridge.jsx, or embedded in a fallback script. Never writes files except
    app.project.save().
*/
var WNCM = WNCM || {};

/* ---------------------------------------------------------------- the editor's open project (bridge + fallback script) */
WNCM.projectInfo = function () {
    var p = app.project, dirty = null, n = null;
    try { dirty = p.dirty; } catch (e) { dirty = null; }       // undocumented, present since AE 17.5
    try { n = p.numItems; } catch (e2) { n = null; }
    return {project: p && p.file ? p.file.name : null, project_path: p && p.file ? p.file.fsName : null, dirty: dirty,
            num_items: n};
};

/* app.newProject() discards the open project: only when AE reports it clean, or it is an empty untitled project */
WNCM.mayDiscard = function (info) {
    return info.dirty === false || (info.dirty === null && !info.project_path && info.num_items === 0);
};

/* ---------------------------------------------------------------- text and shape helpers (probe + build) */
WNCM.dirName = function (v) {
    try {
        if (v === ParagraphDirection.DIRECTION_RIGHT_TO_LEFT) { return "RTL"; }
        if (v === ParagraphDirection.DIRECTION_LEFT_TO_RIGHT) { return "LTR"; }
    } catch (e) {}
    return (v === undefined || v === null) ? null : String(v);
};

WNCM.setFont = function (td, ps, useObject) {
    if (useObject && app.fonts && app.fonts.getFontsByPostScriptName) {
        var arr = app.fonts.getFontsByPostScriptName(ps);
        if (arr && arr.length) { td.fontObject = arr[0]; return; }
    }
    td.font = ps;
};

/* o: {text, font, size, color, rtl, justify: "center"|"right"|"left", leading, caps}. Returns the direction read back. */
WNCM.styleText = function (L, o) {
    var sp = L.property("ADBE Text Properties").property("ADBE Text Document");
    var td = sp.value, caps = o.caps || {};
    try { td.resetCharStyle(); td.resetParagraphStyle(); } catch (e0) {}
    td.text = o.text;
    WNCM.setFont(td, o.font, caps.fontobject !== false);
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
        rb.direction_textdocument = WNCM.dirName(sp.value.direction);
        rb.direction_paragraph_range = rb.direction_textdocument;
        if (rb.direction_textdocument !== "RTL") {          // AE 25.2 dropped TextDocument.direction on setValue
            try {
                var t2 = sp.value;
                t2.paragraphRange(0).direction = ParagraphDirection.DIRECTION_RIGHT_TO_LEFT;
                sp.setValue(t2);
            } catch (e3) { rb.paragraph_error = String(e3); }
            try { rb.direction_paragraph_range = WNCM.dirName(sp.value.paragraphRange(0).direction); } catch (e4) {}
        }
    }
    L.property("ADBE Transform Group").property("ADBE Anchor Point").expression =
        "var r=sourceRectAtTime(time,false);[r.left+r.width/2,r.top+r.height/2]";
    return rb;
};

WNCM.readText = function (L) {
    var td = L.property("ADBE Text Properties").property("ADBE Text Document").value;
    var r = {text: td.text, font_ps: td.font, substitute: false, composer: null, direction: null};
    try { r.substitute = !!(td.fontObject && td.fontObject.isSubstitute); } catch (e) {}
    try { r.composer = (td.composerEngine === ComposerEngine.UNIVERSAL_TYPE_ENGINE) ? "UNIVERSAL" : "LATIN"; } catch (e2) {}
    try { r.direction = WNCM.dirName(td.direction); } catch (e3) {}
    return r;
};

/* layer box in comp pixels [left, top, width, height] at time t (no parenting or rotation in our comps) */
WNCM.compRect = function (L, t) {
    var r = L.sourceRectAtTime(t, false), tg = L.property("ADBE Transform Group");
    var a = tg.property("ADBE Anchor Point").valueAtTime(t, false), p = tg.property("ADBE Position").valueAtTime(t, false);
    var s = tg.property("ADBE Scale").valueAtTime(t, false), sx = s[0] / 100, sy = s[1] / 100;
    return [p[0] + (r.left - a[0]) * sx, p[1] + (r.top - a[1]) * sy, r.width * sx, r.height * sy];
};

/* word or line reveal synced to cue times (seconds); basedOn 3 = Words, 4 = Lines */
WNCM.revealWords = function (L, cueSecs, basedOn, durS) {
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
WNCM.emphasisWords = function (L, idx, rgb, colorExpr) {
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
WNCM.shapeLayer = function (comp, name, shapes, o) {
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
    v.addProperty("ADBE Vector Filter - Trim");
    var st = v.addProperty("ADBE Vector Graphic - Stroke");
    var tr = v.property("ADBE Vector Filter - Trim");   // re-acquired: adding the stroke invalidated the old reference
    st.property("ADBE Vector Stroke Width").setValue(o.stroke || 6);
    st.property("ADBE Vector Stroke Color").setValue(o.color || [1, 1, 1]);
    if (o.colorExpr) { st.property("ADBE Vector Stroke Color").expression = o.colorExpr; }
    try {
        st.property("ADBE Vector Stroke Line Cap").setValue(2);
        st.property("ADBE Vector Stroke Line Join").setValue(2);
    } catch (e) {}
    return {layer: L, trim: tr, stroke: st};
};

/* ================================================================ motion build (plan -> AE project)
   Every key time is frame * comp.frameDuration (29.97/23.976 never drift). Frames in the plan are absolute sequence
   frames; inside a scene comp they are made relative to the scene start. */
WNCM.S = WNCM.S || {};
WNCM.P = WNCM.P || {};

WNCM.t = function (comp, frame) { return frame * comp.frameDuration; };

/* JS string literal with every non-ASCII char as \uXXXX (safe inside expressions, whatever the file encoding) */
WNCM.jsq = function (s) {
    var out = '"';
    s = String(s);
    for (var i = 0; i < s.length; i++) {
        var c = s.charAt(i), code = s.charCodeAt(i);
        if (c === '"' || c === "\\") { out += "\\" + c; }
        else if (code < 32 || code > 126) { out += "\\u" + ("0000" + code.toString(16)).slice(-4); }
        else { out += c; }
    }
    return out + '"';
};

/* expression linking a colour to BRAND_CONTROLS when it is exactly one of the brand colours (else null) */
WNCM.colorExpr = function (rgb) {
    var cs = WNCM.plan.brand.controls;
    for (var i = 0; i < cs.length; i++) {
        var c = cs[i].rgb;
        if (Math.abs(c[0] - rgb[0]) < 0.003 && Math.abs(c[1] - rgb[1]) < 0.003 && Math.abs(c[2] - rgb[2]) < 0.003) {
            return 'comp("BRAND_CONTROLS").layer("BRAND").effect("' + cs[i].name + '")("Color")';
        }
    }
    return null;
};

WNCM.EASE = {smooth: [75, 6], snappy: [90, 4], bouncy: [80, 5], gentle: [33, 12]};
WNCM.easeOf = function () { return WNCM.EASE[WNCM.plan.recipe_motion.ease] || WNCM.EASE.smooth; };

WNCM.keys = function (prop, comp, frames, values) {
    var inf = WNCM.easeOf()[0];
    for (var i = 0; i < frames.length; i++) { prop.setValueAtTime(WNCM.t(comp, frames[i]), values[i]); }
    for (var k = 1; k <= prop.numKeys; k++) {
        var dims = 1;
        try { var v = prop.keyValue(k); if (v instanceof Array) { dims = v.length; } } catch (e) {}
        if (prop.propertyValueType === PropertyValueType.TwoD_SPATIAL || prop.propertyValueType === PropertyValueType.ThreeD_SPATIAL) { dims = 1; }
        var e1 = [], e2 = [];
        for (var d = 0; d < dims; d++) { e1.push(new KeyframeEase(0, inf)); e2.push(new KeyframeEase(0, inf)); }
        try { prop.setTemporalEaseAtKey(k, e1, e2); } catch (err) {}
    }
};

WNCM.tg = function (L, name) { return L.property("ADBE Transform Group").property(name); };

/* element appears at frame f (scene-relative): fade + pop (bouncy overshoots), or slide in the reading direction */
WNCM.appear = function (comp, L, f, slide) {
    var len = WNCM.easeOf()[1];
    WNCM.keys(WNCM.tg(L, "ADBE Opacity"), comp, [f, f + len], [0, 100]);
    if (slide) {
        var p = WNCM.tg(L, "ADBE Position").value;
        WNCM.keys(WNCM.tg(L, "ADBE Position"), comp, [f, f + len], [[p[0] - WNCM.plan.dir * 40, p[1]], [p[0], p[1]]]);
    } else if (WNCM.plan.recipe_motion.ease === "bouncy") {
        WNCM.keys(WNCM.tg(L, "ADBE Scale"), comp, [f, f + len, f + len + 3], [[85, 85], [106, 106], [100, 100]]);
    } else if (WNCM.plan.recipe_motion.ease !== "gentle") {
        WNCM.keys(WNCM.tg(L, "ADBE Scale"), comp, [f, f + len], [[92, 92], [100, 100]]);
    }
};

WNCM.solid = function (comp, name, rgb) {
    var L = comp.layers.addSolid([1, 1, 1], name, comp.width, comp.height, 1);
    var fill = L.property("ADBE Effect Parade").addProperty("ADBE Fill");
    fill.property("ADBE Fill-0002").setValue(rgb);
    var ex = WNCM.colorExpr(rgb);
    if (ex) { fill.property("ADBE Fill-0002").expression = ex; }
    return L;
};

/* Word/line reveal: one text layer per word, chained by sourceRectAtTime from the line's reading-start edge (Arabic
   never joins across spaces, so shaping is unchanged). An expression selector "Based On: Words" mapped textIndex
   inconsistently for RTL Arabic in After Effects 26.5 (probe), so no selector is used. A guide layer (not rendered)
   keeps the whole text: the editable reference, and what the read-back checks. */
WNCM.wordLayers = function (comp, el, sceneStart, byLine) {
    var caps = WNCM.caps || {}, rtl = !!el.rtl, fd = comp.frameDuration;
    var guide = comp.layers.addText(el.text);
    guide.name = el.name;
    WNCM.styleText(guide, {text: el.text, font: el.font_ps, size: el.size, color: el.color, rtl: el.rtl,
        justify: el.anchor === "start" ? (rtl ? "right" : "left") : "center", leading: el.size * 1.25, caps: caps});
    if (el.anchor === "start") {
        WNCM.tg(guide, "ADBE Anchor Point").expression = rtl ? "var r=sourceRectAtTime(time,false);[r.left+r.width,r.top+r.height/2]" :
            "var r=sourceRectAtTime(time,false);[r.left,r.top+r.height/2]";
    }
    WNCM.tg(guide, "ADBE Position").setValue([el.x, el.y]);
    guide.guideLayer = true;
    guide.comment = el.cue_hash || "";
    var lines = el.lines || [el.text], toks = el.tokens || [], k = 0, sp = el.size * 0.3, lh = el.size * 1.25;
    var rf = Math.max(2, Math.round((WNCM.plan.word_reveal_s || 0.18) / fd)), emph = el.emphasis || [];
    for (var i = 0; i < lines.length; i++) {
        var raw = String(lines[i]).split(" "), wds = [], names = [], j, q;
        for (j = 0; j < raw.length; j++) { if (raw[j] !== "") { wds.push(raw[j]); } }
        for (j = 0; j < wds.length; j++) { names.push('"' + el.name + "_w" + (k + j + 1) + '"'); }
        var y = el.y + (i - (lines.length - 1) / 2) * lh;
        for (j = 0; j < wds.length; j++) {
            var idx = k + j + 1, isE = false;
            for (q = 0; q < emph.length; q++) { if (emph[q] === idx) { isE = true; } }
            var W = comp.layers.addText(wds[j]);
            W.name = el.name + "_w" + idx;
            WNCM.styleText(W, {text: wds[j], font: el.font_ps, size: el.size, color: isE ? el.accent : el.color, rtl: el.rtl,
                justify: rtl ? "right" : "left", caps: caps});
            WNCM.tg(W, "ADBE Anchor Point").expression = rtl ? "var r=sourceRectAtTime(time,false);[r.left+r.width,r.top+r.height/2]" :
                "var r=sourceRectAtTime(time,false);[r.left,r.top+r.height/2]";
            var ex = "var n=[" + names.join(",") + "];var me=" + j + ";var sp=" + sp + ";var w=0,o=0;" +
                "for(var q=0;q<n.length;q++){var Lq=thisComp.layer(n[q]);var r=Lq.sourceRectAtTime(time,false).width*Lq.transform.scale[0]/100;" +
                "w+=r;if(q<me){o+=r+sp;}}" +
                "w+=sp*(n.length-1);";
            if (el.anchor === "start") { ex += rtl ? "[" + el.x + "-o," + y + "]" : "[" + el.x + "+o," + y + "]"; }
            else { ex += rtl ? "[" + el.x + "+w/2-o," + y + "]" : "[" + el.x + "-w/2+o," + y + "]"; }
            WNCM.tg(W, "ADBE Position").expression = ex;
            var cue = byLine ? ((el.line_cues && el.line_cues[i] !== undefined) ? el.line_cues[i] : sceneStart)
                : ((toks[idx - 1] && toks[idx - 1].cue_frame !== undefined) ? toks[idx - 1].cue_frame : sceneStart);
            var f0 = cue - sceneStart;
            WNCM.keys(WNCM.tg(W, "ADBE Opacity"), comp, [f0, f0 + rf], [0, 100]);
            WNCM.keys(WNCM.tg(W, "ADBE Scale"), comp, [f0, f0 + rf], isE ? [[90, 90], [108, 108]] : [[92, 92], [100, 100]]);
        }
        k += wds.length;
    }
    return guide;
};

/* text element (plan.scenes[].elements kind text|counter) inside a scene comp starting at sceneStart */
WNCM.textEl = function (comp, el, sceneStart) {
    var caps = WNCM.caps, revealMode = el.reveal || "none";
    if ((revealMode === "word" || revealMode === "line") && el.tokens && el.tokens.length) {
        return WNCM.wordLayers(comp, el, sceneStart, revealMode === "line");
    }
    var L = comp.layers.addText(el.text);
    L.name = el.name;
    var just = el.anchor === "start" ? (el.rtl ? "right" : "left") : "center";
    WNCM.styleText(L, {text: el.text, font: el.font_ps, size: el.size, color: el.color, rtl: el.rtl, justify: just,
        leading: el.size * 1.25, caps: caps});
    var cex = WNCM.colorExpr(el.color);
    if (cex) {
        try { L.property("ADBE Text Properties").property("ADBE Text Document").expression = "text.sourceText.style.setFillColor(" + cex + ")"; } catch (e0) {}
    }
    if (el.anchor === "start") {
        WNCM.tg(L, "ADBE Anchor Point").expression = el.rtl ?
            "var r=sourceRectAtTime(time,false);[r.left+r.width,r.top+r.height/2]" :
            "var r=sourceRectAtTime(time,false);[r.left,r.top+r.height/2]";
    }
    WNCM.tg(L, "ADBE Position").setValue([el.x, el.y]);
    L.comment = el.cue_hash || "";
    if (revealMode === "item") {
        WNCM.appear(comp, L, el.appear_frame - sceneStart, true);
    } else if (el.appear_frame !== null && el.appear_frame !== undefined) {
        WNCM.appear(comp, L, el.appear_frame - sceneStart, false);
    }
    if (el.emphasis && el.emphasis.length && caps.emphasis_animator !== false && caps.word_index_logical !== false) {
        WNCM.emphasisWords(L, el.emphasis, el.accent, WNCM.colorExpr(el.accent));
        var an = L.property("ADBE Text Properties").property("ADBE Text Animators").property("Emphasis");
        try { an.property("ADBE Text Animator Properties").addProperty("ADBE Text Scale 3D").setValue([108, 108, 100]); } catch (e1) {}
    }
    return L;
};

WNCM.counterEl = function (comp, el, sceneStart) {
    var L = WNCM.textEl(comp, el, sceneStart), fd = comp.frameDuration;
    var a = (el.from_frame - sceneStart) * fd, b = (el.to_frame - sceneStart) * fd;
    var ex = "var v=linear(time," + a + "," + b + ",0," + el.target + ");var s=v.toFixed(" + (el.decimals || 0) + ");";
    if (el.group) { ex += "s=s.replace(/\\B(?=(\\d{3})+(?!\\d))/g,',');"; }
    if (el.digits === "arabic_indic") { ex += "var D=" + WNCM.jsq("\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669") + ";s=s.replace(/[0-9]/g,function(d){return D.charAt(d);});"; }
    ex += WNCM.jsq(el.prefix || "") + "+s+" + WNCM.jsq(el.suffix || "");
    L.property("ADBE Text Properties").property("ADBE Text Document").expression = ex;
    return L;
};

WNCM.iconEl = function (comp, el, sceneStart) {
    var r = WNCM.shapeLayer(comp, el.name, el.shapes, {stroke: el.stroke, color: el.color, colorExpr: WNCM.colorExpr(el.color)});
    WNCM.tg(r.layer, "ADBE Position").setValue([el.x, el.y]);
    var f = (el.draw_on_frame === null || el.draw_on_frame === undefined ? sceneStart + 4 : el.draw_on_frame) - sceneStart;
    WNCM.keys(r.trim.property("ADBE Vector Trim End"), comp, [f, f + 14], [0, 100]);
    return r.layer;
};

WNCM.vectorEl = function (comp, el, sceneStart) {
    var L = comp.layers.addShape();
    L.name = el.name;
    var g = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group"), v = g.property("ADBE Vectors Group");
    for (var i = 0; i < el.shapes.length; i++) {
        var s = new Shape();
        s.vertices = el.shapes[i].vertices; s.inTangents = el.shapes[i].inTangents;
        s.outTangents = el.shapes[i].outTangents; s.closed = el.shapes[i].closed;
        v.addProperty("ADBE Vector Shape - Group").property("ADBE Vector Shape").setValue(s);
    }
    var fl = v.addProperty("ADBE Vector Graphic - Fill");
    fl.property("ADBE Vector Fill Color").setValue(el.fill);
    WNCM.tg(L, "ADBE Position").setValue([el.x, el.y]);
    WNCM.appear(comp, L, (el.appear_frame || sceneStart + 4) - sceneStart, false);
    return L;
};

WNCM.imageEl = function (comp, el, sceneStart) {
    var item = WNC.footage(el.path);
    if (!item) { WNCM.report.warnings.push(el.name + ": image missing " + el.path); return null; }
    var L = comp.layers.add(item);
    L.name = el.name;
    var s = (el.fit === "contain" ? Math.min(el.w / item.width, el.h / item.height) : Math.max(el.w / item.width, el.h / item.height)) * 100;
    WNCM.tg(L, "ADBE Scale").setValue([s, s]);
    if (el.radius && el.fit !== "contain") { WNC.roundMask(L, el.w / (s / 100), el.h / (s / 100), el.radius / (s / 100), 0.4); }
    WNCM.tg(L, "ADBE Position").setValue([el.x, el.y]);
    WNCM.appear(comp, L, (el.appear_frame || sceneStart + 4) - sceneStart, false);
    return L;
};

WNCM.dotEl = function (comp, el, sceneStart) {
    var L = comp.layers.addShape();
    L.name = el.name;
    var g = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group"), v = g.property("ADBE Vectors Group");
    v.addProperty("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size").setValue([el.r * 2, el.r * 2]);
    var fl = v.addProperty("ADBE Vector Graphic - Fill");
    fl.property("ADBE Vector Fill Color").setValue(el.color);
    var ex = WNCM.colorExpr(el.color);
    if (ex) { fl.property("ADBE Vector Fill Color").expression = ex; }
    WNCM.tg(L, "ADBE Position").setValue([el.x, el.y]);
    WNCM.appear(comp, L, el.appear_frame - sceneStart, false);
    return L;
};

WNCM.lineEl = function (comp, el, sceneStart) {
    var r = WNCM.shapeLayer(comp, el.name, [{vertices: [el.from, el.to], inTangents: [[0, 0], [0, 0]], outTangents: [[0, 0], [0, 0]], closed: false}],
        {stroke: el.width, color: el.color, colorExpr: WNCM.colorExpr(el.color)});
    WNCM.keys(r.trim.property("ADBE Vector Trim End"), comp, [el.draw_frames[0] - sceneStart, el.draw_frames[1] - sceneStart], [0, 100]);
    return r.layer;
};

WNCM.element = function (comp, el, sceneStart) {
    var k = el.kind;
    if (k === "text") { return WNCM.textEl(comp, el, sceneStart); }
    if (k === "counter") { return WNCM.counterEl(comp, el, sceneStart); }
    if (k === "icon") { return WNCM.iconEl(comp, el, sceneStart); }
    if (k === "vector") { return WNCM.vectorEl(comp, el, sceneStart); }
    if (k === "image") { return WNCM.imageEl(comp, el, sceneStart); }
    if (k === "dot") { return WNCM.dotEl(comp, el, sceneStart); }
    if (k === "line") { return WNCM.lineEl(comp, el, sceneStart); }
    WNCM.report.warnings.push(el.name + ": unknown element kind " + k);
    return null;
};

/* generic scene body: its background when its theme differs, then every element in plan order (drawn bottom-up) */
WNCM.sceneBody = function (comp, scene) {
    if (scene.theme !== WNCM.plan.theme.name) { WNCM.solid(comp, scene.id + "_bg", scene.bg); }
    var made = [];
    for (var i = 0; i < scene.elements.length; i++) {
        var L = WNCM.element(comp, scene.elements[i], scene.start_frame);
        if (L) { made.push(L); }
    }
    for (var j = 0; j < made.length; j++) { made[j].moveToBeginning(); }      // first element ends on top
    return made;
};

WNCM.S.kinetic_quote = function (comp, scene) { return WNCM.sceneBody(comp, scene); };
WNCM.S.title_card = function (comp, scene) { return WNCM.sceneBody(comp, scene); };

/* transition_in on the scene's layer in MAIN (and the outgoing layer for push) */
WNCM.transition = function (main, layer, prev, scene) {
    var tr = scene.transition_in, n = tr.frames, s = scene.start_frame, W = main.width, dir = WNCM.plan.dir;
    if (!n || tr.type === "cut") { return; }
    if (tr.type === "push") {
        WNCM.keys(WNCM.tg(layer, "ADBE Position"), main, [s, s + n], [[W / 2 + dir * W, main.height / 2], [W / 2, main.height / 2]]);
        if (prev) { WNCM.keys(WNCM.tg(prev, "ADBE Position"), main, [s, s + n], [[W / 2, main.height / 2], [W / 2 - dir * W, main.height / 2]]); }
    } else if (tr.type === "wipe") {
        var lw = layer.property("ADBE Effect Parade").addProperty("ADBE Linear Wipe");
        lw.property("ADBE Linear Wipe-0002").setValue(dir < 0 ? 90 : 270);
        lw.property("ADBE Linear Wipe-0003").setValue(60);
        WNCM.keys(lw.property("ADBE Linear Wipe-0001"), main, [s, s + n], [100, 0]);
    } else if (tr.type === "scale") {
        WNCM.keys(WNCM.tg(layer, "ADBE Scale"), main, [s, s + n], [[118, 118], [100, 100]]);
        WNCM.keys(WNCM.tg(layer, "ADBE Opacity"), main, [s, s + n], [0, 100]);
    } else {
        WNCM.keys(WNCM.tg(layer, "ADBE Opacity"), main, [s, s + n], [0, 100]);
    }
};

/* ---------------------------------------------------------------- persistent layers */
WNCM.P.background = function (main, plan) {
    var L = WNCM.solid(main, "BACKGROUND", plan.theme.bg);
    try {
        var ramp = L.property("ADBE Effect Parade").addProperty("ADBE Ramp");
        var c = plan.theme.bg, lift = [Math.min(1, c[0] + 0.06), Math.min(1, c[1] + 0.06), Math.min(1, c[2] + 0.06)];
        ramp.property("ADBE Ramp-0002").setValue(lift);
        ramp.property("ADBE Ramp-0004").setValue(c);
        ramp.property("ADBE Ramp-0001").expression = "[thisComp.width*(0.3+0.2*Math.sin(time*0.25)), 0]";
        ramp.property("ADBE Ramp-0003").expression = "[thisComp.width*(0.7-0.2*Math.sin(time*0.25)), thisComp.height]";
        var nz = L.property("ADBE Effect Parade").addProperty("ADBE Noise");
        nz.property("ADBE Noise-0001").setValue(2);
    } catch (e) { WNCM.report.warnings.push("background effects: " + e); }
    return L;
};

WNCM.persistentComp = function (name, plan) {
    var c = app.project.items.addComp(name, plan.w, plan.h, 1, plan.duration_frames / plan.fps, plan.fps);
    c.parentFolder = WNC.folder("NH_PERSISTENT");
    return c;
};

/* RTL paragraph direction only for text in Arabic script (an English window's Latin captions and names stay LTR) */
WNCM.isArabic = function (s) {
    return /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(String(s));
};

WNCM.P.captions = function (main, plan) {
    var cap = plan.persistent.captions;
    if (!cap || !cap.cues.length) { return null; }
    var c = WNCM.persistentComp("CAPTIONS", plan);
    for (var i = 0; i < cap.cues.length; i++) {
        var q = cap.cues[i], L = c.layers.addText(q.text);
        L.name = "CAP_" + (i + 1);
        WNCM.styleText(L, {text: q.text, font: cap.font_ps, size: cap.size, color: cap.color, rtl: WNCM.isArabic(q.text), justify: "center",
            caps: WNCM.caps});
        WNCM.tg(L, "ADBE Position").setValue([cap.x, cap.y]);
        WNC.shadow(L, 0.45, 4, 14);
        L.inPoint = WNCM.t(c, q.start_frame);
        L.outPoint = WNCM.t(c, q.end_frame);
        WNCM.keys(WNCM.tg(L, "ADBE Scale"), c, [q.start_frame, q.start_frame + 3], [[94, 94], [100, 100]]);
    }
    main.layers.add(c);
    return c;
};

WNCM.P.speaker_badge = function (main, plan) {
    var b = plan.persistent.speaker_badge;
    if (!b || !b.segments.length) { return null; }
    var c = WNCM.persistentComp("SPEAKER_BADGE", plan), rtl = plan.direction === "rtl";
    for (var i = 0; i < b.segments.length; i++) {
        var g = b.segments[i], L = c.layers.addText(g.name);
        L.name = "BADGE_" + (i + 1);
        WNCM.styleText(L, {text: g.name, font: b.font_ps, size: b.size, color: b.accent, rtl: WNCM.isArabic(g.name),
            justify: rtl ? "right" : "left", caps: WNCM.caps});
        WNCM.tg(L, "ADBE Anchor Point").expression = rtl ? "var r=sourceRectAtTime(time,false);[r.left+r.width,r.top+r.height/2]" :
            "var r=sourceRectAtTime(time,false);[r.left,r.top+r.height/2]";
        WNCM.tg(L, "ADBE Position").setValue([b.x, b.y]);
        L.inPoint = WNCM.t(c, g.start_frame);
        L.outPoint = WNCM.t(c, g.end_frame);
        WNCM.keys(WNCM.tg(L, "ADBE Opacity"), c, [g.start_frame, g.start_frame + 5], [0, 100]);
    }
    main.layers.add(c);
    return c;
};

WNCM.P.progress = function (main, plan) {
    if (!plan.persistent.progress) { return null; }
    var y = plan.safe.top - 30, L = WNC.rect(main, "PROGRESS", [main.width, 8], [main.width / 2, y], {fill: plan.theme.accent});
    var g = L.property("ADBE Root Vectors Group").property(1).property("ADBE Vector Transform Group");
    // anchored (and placed, so it does not move) at the reading-start edge: scaleX 0 -> 100 fills the reading way
    var edge = 'var s=content("Box").content("Rectangle Path 1").size;[' + (-plan.dir) + '*s[0]/2,0]';
    g.property("ADBE Vector Anchor").expression = edge;
    g.property("ADBE Vector Position").expression = edge;
    var sc = g.property("ADBE Vector Scale");
    sc.setValueAtTime(0, [0, 100]);
    sc.setValueAtTime(WNCM.t(main, plan.duration_frames), [100, 100]);
    return L;
};

WNCM.P.voice_pulse = function (main, plan) {
    var vp = plan.persistent.voice_pulse;
    if (!vp || !vp.values.length) { return null; }
    var ctl = main.layers.addNull();
    ctl.name = "VOICE_LEVEL";
    var sl = ctl.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
    sl.name = "Level";
    var times = [], vals = [];
    for (var i = 0; i < vp.values.length; i++) { times.push(WNCM.t(main, i)); vals.push(vp.values[i]); }
    sl.property(1).setValuesAtTimes(times, vals);
    var ring = WNC.ellipse(main, "VOICE_PULSE", 160, [main.width / 2, main.height - plan.safe.bottom + 120], "Brand Teal", 6);
    WNCM.tg(ring, "ADBE Scale").expression = 'var l=thisComp.layer("VOICE_LEVEL").effect("Level")(1);[100+60*l,100+60*l]';
    WNCM.tg(ring, "ADBE Opacity").expression = 'var l=thisComp.layer("VOICE_LEVEL").effect("Level")(1);40+60*l';
    return ring;
};

/* ---------------------------------------------------------------- audio */
WNCM.audio = function (main, plan) {
    var a = plan.audio, L, item;
    item = WNC.footage(a.dialogue);
    if (item) { L = main.layers.add(item); L.name = "DIALOGUE"; L.moveToEnd(); }
    if (a.music) {
        item = WNC.footage(a.music.file);
        if (item) {
            L = main.layers.add(item);
            L.name = "MUSIC";
            /* T4.6: a short track ends at its own end_frame (it plays once, no loop) */
            var e = Math.min(plan.duration_frames, a.music.end_frame || plan.duration_frames);
            L.outPoint = WNCM.t(main, e);
            var lv = L.property("ADBE Audio Group").property("ADBE Audio Levels");
            /* the plan's level keys [frame, dB]: fade in, ducked under the dialogue, lifted in long gaps, fade out */
            var ks = a.music.keyframes || [], kt = [], kv = [];
            for (var k = 0; k < ks.length; k++) { kt.push(WNCM.t(main, ks[k][0])); kv.push([ks[k][1], ks[k][1]]); }
            if (kt.length) {
                lv.setValuesAtTimes(kt, kv);
            } else {            /* a plan without keys (before T4.6): flat level, fade out at the layer's own end */
                lv.setValue([a.music.level_db, a.music.level_db]);
                lv.setValueAtTime(WNCM.t(main, e - a.music.fade_out_frames), [a.music.level_db, a.music.level_db]);
                lv.setValueAtTime(WNCM.t(main, e), [-48, -48]);
            }
            L.moveToEnd();
        }
    }
    for (var i = 0; i < a.sfx.length; i++) {
        item = WNC.footage(a.sfx[i].file);
        if (!item) { continue; }
        L = main.layers.add(item);
        L.name = "SFX_" + a.sfx[i].kind + "_" + (i + 1);
        L.startTime = WNCM.t(main, a.sfx[i].frame);
        L.property("ADBE Audio Group").property("ADBE Audio Levels").setValue([-3, -3]);
        L.moveToEnd();
    }
};

/* ---------------------------------------------------------------- build */
WNCM.build = function (job) {
    var plan = job.plan;
    WNCM.plan = plan;
    WNCM.caps = job.caps || {};
    WNCM.report = {made: [], failed: [], warnings: []};
    WNC.W = plan.w; WNC.H = plan.h; WNC.FPS = plan.fps;
    WNC_DATA = {brand: plan.brand};
    WNC.buildBrand();
    var main = app.project.items.addComp("MAIN_" + plan.reel_id, plan.w, plan.h, 1, plan.duration_frames / plan.fps, plan.fps);
    WNCM.P.background(main, plan);
    var prev = null;
    for (var i = 0; i < plan.scenes.length; i++) {
        var sc = plan.scenes[i];
        try {
            var n = sc.layer_out_frame - sc.start_frame;
            var c = app.project.items.addComp(sc.id + "_" + sc.type, plan.w, plan.h, 1, n / plan.fps, plan.fps);
            c.parentFolder = WNC.folder("NH_SCENES");
            c.comment = sc.type + " | " + (sc.beat_role || "") + " | frames " + sc.start_frame + "-" + sc.end_frame;
            (WNCM.S[sc.type] || WNCM.sceneBody)(c, sc);
            var L = main.layers.add(c);
            L.name = c.name;
            L.startTime = WNCM.t(main, sc.start_frame);
            L.inPoint = WNCM.t(main, sc.start_frame);
            L.outPoint = WNCM.t(main, sc.layer_out_frame);
            WNCM.transition(main, L, prev, sc);
            prev = L;
            WNCM.report.made.push(sc.id);
        } catch (err) {
            WNCM.report.failed.push({scene: sc.id, error: String(err), line: err.line});
        }
    }
    try { WNCM.P.captions(main, plan); } catch (e1) { WNCM.report.failed.push({scene: "CAPTIONS", error: String(e1), line: e1.line}); }
    try { WNCM.P.speaker_badge(main, plan); } catch (e2) { WNCM.report.failed.push({scene: "SPEAKER_BADGE", error: String(e2), line: e2.line}); }
    try { WNCM.P.progress(main, plan); } catch (e3) { WNCM.report.failed.push({scene: "PROGRESS", error: String(e3), line: e3.line}); }
    try { WNCM.P.voice_pulse(main, plan); } catch (e4) { WNCM.report.failed.push({scene: "VOICE_PULSE", error: String(e4), line: e4.line}); }
    try { WNCM.audio(main, plan); } catch (e5) { WNCM.report.failed.push({scene: "AUDIO", error: String(e5), line: e5.line}); }
    try {
        var rq = app.project.renderQueue.items.add(main);
        rq.outputModule(1).file = new File(job.render_path);
    } catch (e6) { WNCM.report.warnings.push("render queue: " + e6); }
    app.project.save(new File(job.aep_path));
    WNCM.report.saved = job.aep_path;
    WNCM.report.main = main.name;
    WNCM.report.ae_version = app.version;
    return WNCM.report;
};

/* ---------------------------------------------------------------- the other scene types
   The engine already placed every element (direction included); these add each type's own decoration. */
WNCM.firstText = function (comp, prefix) {
    for (var i = 1; i <= comp.numLayers; i++) {
        var L = comp.layer(i);
        if (L instanceof TextLayer && L.name.substr(0, prefix.length) === prefix) { return L; }
    }
    return null;
};

/* rounded card that follows a text layer's box (sourceRectAtTime), placed under it */
WNCM.cardBehind = function (comp, textLayer, name, rgb, opacity, pad) {
    if (!textLayer) { return null; }
    var tn = textLayer.name.replace(/"/g, "");
    var card = WNC.rect(comp, name, [600, 200], [comp.width / 2, comp.height / 2], {radius: 28, fill: rgb,
        fillOpacity: opacity, sizeExpr: 'var r=thisComp.layer("' + tn + '").sourceRectAtTime(time,false);[r.width+' + (2 * pad) + ', r.height+' + (2 * pad) + ']'});
    WNCM.tg(card, "ADBE Position").expression = 'var L=thisComp.layer("' + tn + '");var r=L.sourceRectAtTime(time,false);L.toComp([r.left+r.width/2,r.top+r.height/2])';
    WNCM.tg(card, "ADBE Opacity").expression = 'thisComp.layer("' + tn + '").transform.opacity';
    card.moveAfter(textLayer);
    return card;
};

WNCM.S.stat_counter = function (comp, scene) { return WNCM.sceneBody(comp, scene); };
WNCM.S.icon_point = function (comp, scene) { return WNCM.sceneBody(comp, scene); };
WNCM.S.list_steps = function (comp, scene) { return WNCM.sceneBody(comp, scene); };
WNCM.S.illustration_scene = function (comp, scene) { return WNCM.sceneBody(comp, scene); };
WNCM.S.outro = function (comp, scene) { return WNCM.sceneBody(comp, scene); };

WNCM.S.comparison = function (comp, scene) {
    var made = WNCM.sceneBody(comp, scene);
    var top = WNCM.plan.safe.top + 120, bottom = comp.height - WNCM.plan.safe.bottom - 220;
    var r = WNCM.shapeLayer(comp, scene.id + "_divider", [{vertices: [[comp.width / 2, top], [comp.width / 2, bottom]],
        inTangents: [[0, 0], [0, 0]], outTangents: [[0, 0], [0, 0]], closed: false}],
        {stroke: 3, color: WNCM.plan.theme.text, colorExpr: WNCM.colorExpr(WNCM.plan.theme.text)});
    WNCM.keys(r.trim.property("ADBE Vector Trim End"), comp, [2, 14], [0, 100]);
    WNCM.tg(r.layer, "ADBE Opacity").setValue(40);
    var bg = null;
    try { bg = comp.layer(scene.id + "_bg"); } catch (e) { bg = null; }
    if (bg) { r.layer.moveBefore(bg); } else { r.layer.moveToEnd(); }     // under the texts, above a themed scene's solid
    return made;
};

WNCM.S.timeline = function (comp, scene) {
    var made = WNCM.sceneBody(comp, scene), dots = [], i, el;
    for (i = 0; i < scene.elements.length; i++) {
        el = scene.elements[i];
        if (el.kind === "dot") { dots.push(el); }
    }
    if (dots.length < 2) { return made; }
    /* a traveller ring rides the line from point to point at their cues, entering from the reading start */
    var start = scene.start_frame, tr = WNC.ellipse(comp, scene.id + "_traveller", 54, [dots[0].x, dots[0].y], "Brand White", 4);
    var pos = WNCM.tg(tr, "ADBE Position"), fr = [Math.max(0, dots[0].appear_frame - start - 6)],
        val = [[dots[0].x - WNCM.plan.dir * 80, dots[0].y]];
    for (i = 0; i < dots.length; i++) { fr.push(dots[i].appear_frame - start); val.push([dots[i].x, dots[i].y]); }
    WNCM.keys(pos, comp, fr, val);
    WNCM.keys(WNCM.tg(tr, "ADBE Opacity"), comp, [fr[0], fr[0] + 4], [0, 100]);
    return made;
};

WNCM.S.quote_card = function (comp, scene) {
    var made = WNCM.sceneBody(comp, scene);
    WNCM.cardBehind(comp, WNCM.firstText(comp, scene.id + "_text"), scene.id + "_card", WNCM.plan.theme.text, 0.08, 56);
    return made;
};

WNCM.S.context_card = function (comp, scene) {
    var made = WNCM.sceneBody(comp, scene), L = WNCM.firstText(comp, scene.id + "_text");
    var card = WNCM.cardBehind(comp, L, scene.id + "_pill", WNCM.plan.theme.accent, 1, 40);
    if (card && L) {
        var td = L.property("ADBE Text Properties").property("ADBE Text Document");
        try { td.expression = "text.sourceText.style.setFillColor(" + (WNCM.colorExpr(WNCM.plan.theme.bg) || "[1,1,1,1]") + ")"; } catch (e) {}
    }
    return made;
};

WNCM.S.person_card = function (comp, scene) {
    var made = WNCM.sceneBody(comp, scene);
    for (var i = 0; i < scene.elements.length; i++) {
        var el = scene.elements[i];
        if (el.kind === "image") {
            var ring = WNC.ellipse(comp, scene.id + "_ring", el.w + 16, [el.x, el.y], "Brand Teal", 6);
            WNCM.appear(comp, ring, (el.appear_frame || scene.start_frame + 4) - scene.start_frame + 2, false);
        }
    }
    return made;
};
