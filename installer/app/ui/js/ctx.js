/* The one shared context of a mounted window: language, OS, the string table, build/config flags, and the record of
   every string key or icon a component asked for that does not exist (the self-check's missing= field). */
export const C = {
  lang: "en",
  rtl: false,
  /* G11: macOS first. "win" draws the Windows title bar and picks the ".win" twin of a string when there is one. */
  os: "mac",
  /* draw the OS title bar inside the page (as the mockups do); ET1-17 decides native decorations vs this */
  chrome: true,
  S: {},
  missing: [],
  cfg: {
    /* D-04: the 3.0 beta is never signed, so the beta chip and the honest test-build line always show */
    signed: false,
    /* D-05: the WhatsApp support chat is live by default; off = copy only + the ONE "coming soon" line */
    supportLive: true
  }
};
