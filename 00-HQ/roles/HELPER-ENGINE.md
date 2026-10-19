# Role: HELPER 1 — Engine builder (Mayar, mayar@thewhynot.ai — own Team seat, on the company PC)

You build and test the Python engine (`reel`, `reel serve`), its features and Kalam/Hush/Tidy. You never open
Premiere or After Effects: live checks go in your report as "needs live check" and the master runs them.

## Where you live
- Claude config: `D:\ClaudeData\accounts\h1` (your login, your settings, your memory, a copy of the house rules
  in its `CLAUDE.md`).
- Worktree: `D:\WNC-work\h1`. You never write in the master's `WhyNotCut` folder or another worktree.
- Started from the desktop shortcut **«WhyNot - Helper 1»**: it opens a command window with your config, in your
  worktree, and sends the kickoff line.

## One-time (your human does this once, about 5 minutes)
1. Double-click «WhyNot - Helper 1» and type `/login`. Open the login link in a **private browser window**
   (the normal browser is signed in as Yunus), then sign in **with your own Team seat**.
2. Check that `claude auth status` (or `/status`) shows **your** e-mail (mayar@thewhynot.ai), not info@thewhynot.ai. The launcher refuses any other account.
3. First task = `SETUP-H1`: run the full test suite through the job queue and report the numbers in
   `00-HQ/inbox/h1/<date>-SETUP-H1.md`.

## Every session
1. PLAYBOOK §3 start (git, BOARD, usage).
2. Take the top `READY` card with `assigned: H1`. Nothing assigned → write that in a short inbox report and stop.
3. Life-cycle per PLAYBOOK §2: branch `h1/<ID>`, TDD, fence only, suite through the queue, commit, push, update
   report.
4. If the usage limit is close: stop at a commit boundary, push, report `PARTIAL`.

## Your area (default fences; the card is the final word)
`whynot-cut/engine/**`, `whynot-cut/tests/**`, `tools/**` (Kalam/Hush/Tidy), and `whynot-cut/skills/**` only
when the card says so.

## Not yours
Panels (`adobe/**`), installers (`setup/**`), release scripts, BOARD/STATUS/LOCKED-AREAS, anything in another
builder's open fence.
