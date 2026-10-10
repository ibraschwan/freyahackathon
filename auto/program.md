# auto: the improvement loop for the builder

Adapted from Karpathy's `autoresearch` (github.com/karpathy/autoresearch): one thing may be changed, one harness
measures it and may not be changed, every experiment is committed and logged, a change is kept only if the
measurement says so. There the thing was `train.py` and the number was `val_bpb`. Here:

| autoresearch | here |
|---|---|
| `train.py`, the file the agent edits | `builder/` (extraction instructions, engine, in-call code) |
| `prepare.py`, fixed data and evaluation | `tests/scenarios.json`, `tests/run_scenarios.py`, `tools/score.py`, `auto/evaluate.py` |
| `val_bpb`, lower is better | scenarios passed out of 100, higher is better |
| 5 minutes of training per experiment | one build (0 to 5 minutes) and one evaluation (about 20 minutes) |
| `results.tsv` | `auto/results.tsv`, plus one line per single test in `auto/tests.jsonl` |

## What is measured

The agent under test is always **the one the builder made by itself** from `briefs/brief-a.md` + `briefs/brief-b.md`
(slot `ab`). The hand-written reference spec in `lab/` is never the thing measured.

One scenario passes when the bank's records are exactly right AND the judge passes the conversation, the same two
conditions the organisers use. `auto/evaluate.py` reports:

- `passed`: scenarios passed, out of the scenarios run. The number that decides.
- `ledger`: scenarios whose bank records are right, whatever the judge said.
- `hung`: calls the customer ended (the agent went silent or looped).
- `stalls`: calls in which the stall step ran. Watched, because that step must not fire on real answers.

## The rules of the loop

1. Change only `builder/`. Never `tests/`, `tools/score.py`, `auto/evaluate.py` while the loop runs. A scenario whose
   script is broken is fixed outside the loop, recorded in `REVISED` in `tests/make_scenarios.py`, and the harness
   version in `results.tsv` changes with it. Results across harness versions are not compared.
2. Nothing from a brief goes into `builder/`: no rule, value, name or sentence. `auto/check_generic.py` must pass
   before every evaluation. It fails when `builder/` contains a holiday date, an outcome, reason, queue or product
   name, or a sentence of Brief A, Brief B or the variant brief.
3. Every change must also work for a brief with other rules: after a change `tests/local_sim.py` passes and the
   variant brief still compiles and passes its self-test (`build.py ... --spec out/variant-c.spec.json --no-deploy`).
   When `builder/extract.py` changed, the variant brief is extracted again as well.
4. One experiment = one commit. Run, read the numbers, then record `keep` or `discard` (or `crash`).

## Keep or discard

A single run is noisy: the same agent can pass a scenario once and fail it the next time. Two different questions
are kept apart:

- **Did this change break something?** A noise question. Answered with repeats, below.
- **How good is the agent?** Only one number answers it: scenarios passed **3 of 3** over the whole set. A scenario
  that passes 2 of 3 is a failure in the final and is counted as one.

Per experiment:

1. Run all scenarios once (`auto/evaluate.py ab --tag ...`). It prints, against the best kept run, which scenarios
   are newly passing and which are newly failing.
2. Every scenario that changed either way is run two more times (`--only ... --reps 2`). It counts as **fixed** only
   if it now passes 3 of 3, and as **regressed** if it fails at least 2 of 3. A scenario between the two (2 of 3) is
   **unstable**: not evidence against the change, but a target, because unstable scenarios lose in the final.
3. **Bank records come first.** A change that lowers the number of scenarios with right bank records is discarded,
   whatever it does to the conversation score. Records are deterministic code; a drop there is a bug, not noise.
4. **Keep** when records did not drop, nothing regressed and at least one scenario is fixed, or results are equal
   and the code is simpler. **Discard** (git revert the commit) otherwise.
5. After every third kept change, and for the final candidate: the confirmation run, all scenarios three times.
   `passed 3/3` from that run is the result that is reported, together with the list of unstable scenarios.

## What the loop may not learn from

The check in rule 2 stops values of a brief from leaking into the builder. It does not stop the builder from being
fitted to the shape of these 100 scenarios. So part of the evidence is kept out of the loop:

- **Talking styles.** The kit's five styles (`pieces`, `corrects`, `talkative`, `asks_back`, `in_words`) are not run
  inside the loop, except the three scenarios that carry a style themselves.
- **Other call days.** `tests/heldout.json`: scenarios on call days the 100 do not use.
- Both are run for a candidate only when it is proposed as final. Their failures may be fixed, but then that
  evidence is spent: the next candidate needs the styles and days it has not been fitted to, or the report says so.
- **Another brief.** A change to `builder/extract.py` is only tested if the variant brief is read again from its
  text. Recompiling its saved spec tests the engine, not the extraction.
- **The final candidate is built from the brief again**, not recompiled from a saved spec, and measured as built.

## Budget

- Model calls of the builder: 30 USD from the start of the loop. Every build adds its cost to `auto/spend.tsv`.
  A change in `engine.py` or `runtime.py` needs no model call: recompile the saved spec with `--spec`. That also
  isolates the effect of the change. 6 USD stay reserved for the end: the final builds from the briefs and one
  more reading of the variant brief.
- Platform: one simulation at a time, at most 10 calls at once. No probing of anything outside the kit's routes.
- Time: freeze at 19:00 Istanbul on Sunday. After the hidden briefs open (20:00) only bug fixes.

## Never stop

Until the freeze the loop continues without asking: take the most frequent failure in the last run, form one
hypothesis, change one thing, measure, record. If nothing fails once, switch to the confirmation run; its failures
are the next targets.
