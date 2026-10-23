# OPS-10 — heavy.sh: a psuite blocked only by RAM runs as a serial suite

- **Assigned:** MASTER (built by a fresh sub-agent; one fresh review)    **Size:** S    **Tier:** LIGHT (dev tooling)
- **Status:** READY, but start only while the heavy queue is quiet (no waiting tickets). Editing heavy.sh in place
  while bash processes are executing it can corrupt them, so use a copy, test it with `heavy-test.sh`, and swap it
  in with nothing waiting.

## Why
On 2026-10-23 the PC sat at RAM 77-78% all morning (the open Claude sessions hold ~10 GB). A `psuite` starts only below
75%. `suite` and `psuite` share one first-come-first-served queue, so the waiting psuite `t29-fu2c-psuite` blocked every
suite behind it for 4+ hours. A serial suite would have started (the first suite needs RAM < 85%), and OPS-09 proved
serial and parallel give the same result. A stopgap rule went into PLAYBOOK §2 and MASTER-INTAKE 1B at 09:55: queue a
psuite only when RAM < 75%, otherwise queue the serial suite. A rule cannot help a call that is already waiting, though.

## Change
- In heavy.sh: when the head `psuite` ticket has waited ≥ 20 min, and RAM is its only blocker (75 ≤ RAM < 85, a
  suite slot free), run it as a serial `suite`. Strip ` --parallel <N>` from its command (both argv forms: a plain
  argv, and inside a `bash -c '…'` string). Log `[heavy] psuite '<label>' run serial: RAM <x>% for <m> min`.
- Nothing else changes: the RAM ≥ 85% brake, the slot counts, first come first served, job slot reservation.

## Acceptance
- [ ] `heavy-test.sh` extended first (red): a RAM-blocked psuite becomes a serial suite after the wait; a psuite blocked
      by slots (not RAM) stays a psuite; RAM ≥ 85% blocks both; the strip works for both argv forms and leaves
      every other argument as it was.
- [ ] heavy-test passes all (old + new); one fresh review, at most 2 fix rounds; backup `heavy.sh.bak-ops10`.
- [ ] Swapped in with no waiting tickets; the next real demotion appears in `heavy.sh log`.
