---
description: Run the research loop for one experiment: build, pre-OOS selection, review, then stop at the OOS gate.
argument-hint: <exp-name> <what to test>
---

Experiment: $ARGUMENTS

Follow CLAUDE.md. "The trial log" below means the current line's trial log, per CLAUDE.md
(`trials_hl.json` for the Hyperliquid line; `trials.json` belongs to the closed Binance line).
Loop:

1. **Plan.** Write research/<exp>/PLAN.md with the hypothesis, the single change vs the
   previous experiment, the pre-OOS selection plan, and a kill criterion fixed in
   advance. If research/<prev>/REVIEW.md proposed a next experiment, start from it.
2. **Build and select on pre-OOS only.** Implement, add tests for any new harness
   or loader code, and run tests + selftest if harness/ changed. Do all selection
   on pre-OOS data and log it to selection_trials.json.
3. **Pre-OOS review.** Spawn the research-reviewer subagent on research/<exp>
   (it has not seen your reasoning, which is the point). Fix every blocking issue
   and re-run the review, at most 3 rounds. If the kill criterion is already hit
   on pre-OOS, write RESULTS.md saying so, commit, and STOP. No OOS run.
4. **OOS gate. STOP HERE and ask me.** Show a short summary: the chosen config,
   pre-OOS numbers, the adversarial fold-id accuracy, the review decision, and the exact OOS command. Do NOT run the
   walk-forward OOS evaluation (for the HL line: the holdout run) or write to the trial log
   until I reply "go".
5. After "go": run OOS once, log one trial, write RESULTS.md, and spawn the reviewer
   again on the final result. Apply non-blocking fixes to the writeup only (never
   re-run OOS with changes). Commit.
6. Finish with a 5-line summary: decision, key numbers, breakeven bps, what we
   learned, and the reviewer's proposed next experiment.
