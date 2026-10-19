<!-- Verbatim copy of BACKLOG.md section BL-18, taken 2026-10-19 15:24. BACKLOG.md stays the source if they differ. -->
### BL-18 [Gate 4]: Two wrong fix lines seen in the installer dogfood (REL-PREVIEW, 2026-10-19)  [Gate 4 value: med]  Model: opus
- **(i)** `install.ps1 -Home <sandbox>`: the gpu step says "no NVIDIA GPU found (nvidia-smi)". `_nvidia_present` deliberately never probes in a sandbox, so only the wording is wrong. Say «وضع تجربة: كارت الشاشة ما اتفحصش / sandbox: GPU not probed».
- **(ii)** `onboard.py` guard-heartbeat fix line: "install Git for Windows" shows whenever no heartbeat exists.
  - Show it only when Git Bash is really missing.
  - Otherwise: «لسه مفيش جلسة WhyNot Cut شغّلت الحارس: افتح Claude Code أو اعمله restart، وبعدين /hooks» / "no WhyNot Cut session has run the guard yet: open or restart Claude Code, then /hooks".
- **Owner:** the executor (the installer track is archived and onboard.py is executor-committed). One small commit with a test for each line. installer/** is touched only for the (i) wording.
- Risk: low (wording; but a wrong fix sends the editor to install something they already have).

