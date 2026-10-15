"""wnc-queue: a detached per-user runner for long NON-AI dev work (suites, flaky hunts, benchmarks, renders, downloads,
CI watches, handoff builds) that keeps going after a Claude session ends, hits a usage limit or the app restarts.

Jobs are JSON files in <home>/queue; a single runner (a per-user scheduled task) takes them through heavy.sh, enforces
timeouts and stop conditions, and writes <home>/done/<id>.json. Dev tool only: not part of the shipped product.
Usage guide: docs/dev/wnc-queue.md.
"""
