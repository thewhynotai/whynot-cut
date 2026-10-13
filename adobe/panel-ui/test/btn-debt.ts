// <button> debt, to pay in B-T2. Premiere UXP paints every <button> as its own native grey control (spike 0.1.7 CSS
// lab), so the kit never emits one: a kit control is a <div role="button" tabindex="0"> (src/kit/html.ts control(),
// test/kit-uxp.test.ts). The panel's screens (src/render.ts) are not on the kit yet: B-T1 froze them, and B-T2 moves
// them onto it. This is the number of `<button` occurrences left in src/render.ts (source text, comments included).
// test/kit-uxp.test.ts keeps it EXACT: a new <button> in render.ts fails, and so does one removed without lowering this
// number here, so the count can only go down, visibly. B-T2 is done when it is 0.
export const RENDER_BUTTONS_TO_MIGRATE_IN_B_T2 = 13;

/** The `<button` occurrences in a source text (the debt's unit). */
export const buttonCount = (src: string): number => (src.match(/<button\b/g) ?? []).length;
