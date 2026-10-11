# Scoring reel candidates

Four integers, 1–10. The engine averages them (`total`) and sorts the plan by it. Score honestly: the editor uses the
order to choose, and a flat 8 on everything helps nobody.

| criterion | 9–10 | 6–8 | 3–5 | 1–2 |
|---|---|---|---|---|
| **hook** (first 3 s) | a question, claim, number or turn a stranger can't scroll past | interesting but needs a second | starts on context or a greeting | starts mid-sentence or on filler |
| **standalone** | fully clear to someone who never heard the episode | one context card fixes it | depends on earlier talk | an inside reference; unusable alone |
| **payoff** | a clear lesson, result, emotion or punchline | a decent point | trails off into the next topic | no point yet |
| **ending** | a finished thought; a strong last line | ends cleanly but flat | ends on "and…" or the host's question | cut mid-thought |

## Boundaries
- Start on the first word of the hook sentence (the engine adds a 120 ms lead-in). If the setup is long, start later
  and use a context card.
- End after the payoff sentence, before the next question or "and also…". The engine adds a 250 ms tail.
- 30–90 s is the target. A great 25 s moment beats a padded 60 s one (it will show a duration warning; that's fine).

## Red flags (lower the score or drop the candidate)
- Pronouns without a referent in the reel ("he did it" — who?), "as I said", "the second point" without the first.
- The key line is the host's question, not the guest's answer (or vice versa) — check the speaker turns.
- A claim that needs approval (medical, money, legal, religious) — keep it only with a `risks` note.
- The same story told twice in the episode — keep the better telling.
- Overlap with another candidate by more than half — keep the better-bounded one.

## Risks field
Short strings the editor reads at Gate 0: `"claim needs approval: …"`, `"mentions <avoid topic>"`, `"names a third
person"`, `"host speaks the last line"`, `"music under speech in the episode (cleanup limited)"`.
