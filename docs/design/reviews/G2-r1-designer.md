# Addendum G round 1 — designer premium critique (P-01, P-03, P-07)

Reviewer: brand-systems-designer agent (AI review, not a human sign-off). References were checked through public docs
and pages only, read and not viewed (WebFetch can't see images).

**Verdict: none of the three is at the $1,000 bar yet.** All three are clean and calm, and in places clearer than the
references. They miss on four points:
- the no-Claude state;
- keyboard shortcuts;
- showing the media itself;
- the Arabic register.

| Screen | Verdict | Ref 1 | Ref 2 |
|---|---|---|---|
| P-01 | not yet: clearer than AutoCut's first launch, but no no-Claude render and no path to a first result | AutoCut first launch (autocut.com help center) | Adobe's one-time notice for generative features (helpx.adobe.com) |
| P-03 | not yet: right hierarchy, but thin (no frame, duration or step status; verbs never show done; no shortcuts) | Raycast action panel + shortcuts (manual.raycast.com) | FireCut panel scope, I/O range (learn.firecut.ai) |
| P-07 | closest: the flagged gate and the pinned bar go beyond Frame.io's statuses, but there's no picture of the edit, and the timecodes are dead text | Premiere Text-Based Editing (adobe.com/learn) | Frame.io status labels in Premiere (blog.frame.io) |

## P0 (a buyer would cancel)
1. **P-07 no-Claude state.** Show "Approved and saved. Claude is signed out, so the build waits." with Open Claude as the fix button.
2. **P-01 no-Claude rows.** Add claude-signed-out and claude-missing. The Claude row turns red and its fix button becomes the screen's one primary.

## P1 (a buyer would notice)
3. **P-03 no-Claude.** Make my edit is disabled with "Sign in to Claude first", and the fix goes in the notice slot.
4. **Shortcut layer.**
   - A `.m-kbd` chip: 20px tall, 4px padding, 1px #383838 border, radius 4, mono 11/16, muted, LTR, 8px start margin.
   - Ctrl/⌘+Enter runs the primary; Esc closes a notice; Alt+1/2/3 switches tabs. No single keys (Premiere owns them).
   - UXP keydown capture is unproven (lab).
5. **P-07 edit map.** A 24px strip, #0D0D0D, radius 4:
   - cuts as 1px #B3B3B3 ticks;
   - statements as 4px text-colour bars;
   - B-roll as #7A7A7A bars;
   - flagged lines in the warn colour;
   - "0:00" and "0:52" at the ends.
6. **P-07 timecodes seek** the Premiere playhead: a 32px ghost button with a 12px play icon. The UXP playhead API needs a lab check.
7. **P-03 hero.**
   - A poster frame (36×64 for 9:16) in a #0D0D0D well;
   - the duration;
   - "Step 3 of 7 · waiting for you";
   - done verbs show a check and their result.
8. **Header collapse.** When all three statuses are OK, show one "All set" pill, expanded only on a failure. This also fixes the 300 px AR header.
9. **P-01 sample clip.** Once everything is green, add a secondary "Try the sample clip" (G-T10).
10. **Motion table per screen:** trigger, property, token and the finished static state.
11. **Arabic register:** one register (controller decision: professional Egyptian, see G2-r1-agency-owner.md).

## P2 (polish)
12. The P-03 Settings row is glass with radius 16. Make it solid #141414, radius 8, with a 2px matching border.
13. The P-07 footer hint names a box that is hidden. Change it to "Check the 3 flagged lines to turn on Approve", and make that text the expand control.
14. P-01: add "3 of 4 ready" with a 4-segment step bar.
15. "Log · 42 lines" becomes "Activity" with no count (controller: it moves to Settings → Details for support).
16. P-03 shows C0239 twice. Drop it from the context row on Home.

## Pattern changes for every screen
- Every screen ships `no-claude` (signed out and not installed).
- Every primary has a shortcut chip, and Esc closes notices.
- The header collapses to "All set".
- A timecode either seeks (with a play icon) or is plain meta.
- Result and approval screens show the media: a poster frame or an edit map.
- Each screen has a motion table with a static fallback.
- Tappable means solid with radius 8. Glass with radius 16 is for containers you can't tap.
- One Arabic register, and no "Log" wording.

## Controller decisions
- **Seeking timecodes** replace the E-D3 r1 rule "timecodes are plain text in 3.0". They are designed now and ship only if the UXP lab proves the playhead API. Otherwise they fall back to plain meta.
- **Data requests to the executor and engine:** a poster frame per item; the edit map data (cuts, statements, B-roll and flagged spans with times); the time saved; step state per verb.
- **UXP lab run (spike css_lab, next live session) must prove:**
  - keydown capture;
  - CSS transitions and @keyframes (static fallbacks);
  - fill-rule;
  - `<bdi>`, text-transform, letter-spacing, tabular-nums;
  - `<img>` thumbnails from a file path;
  - sticky/pinned action bar scrolling;
  - the playhead seek API.
