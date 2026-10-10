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

A single run is noisy: the same agent can pass a scenario once and fail it the next time. So:

1. Run all scenarios once (`auto/evaluate.py ab --tag ...`). It prints, against the best kept run, which scenarios
   are newly passing and which are newly failing.
2. Every scenario that changed either way is run two more times (`--only ... --reps 2`). A scenario counts as
   **fixed** only if it now passes 3 of 3, and as **regressed** if it fails at least 2 of 3.
3. **Keep** when there is no regression and at least one fix, or no change in results but simpler code.
   **Discard** (git revert the commit) when something regressed and the change cannot be repaired within one more
   experiment, or when nothing was fixed.
4. After every third kept change, and at the end: the confirmation run. All scenarios three times, and each talking
   style of the kit (`pieces`, `corrects`, `talkative`, `asks_back`, `in_words`) once. The final asks for three of
   three, so `passed 3/3` from this run is the number that is reported as the result.

## Budget

- Model calls of the builder: 30 USD from the start of the loop. Every build adds its cost to `auto/spend.tsv`.
  A change in `engine.py` or `runtime.py` needs no model call: recompile the saved spec with `--spec`.
- Platform: one simulation at a time, at most 10 calls at once. No probing of anything outside the kit's routes.
- Time: freeze at 19:00 Istanbul on Sunday. After the hidden briefs open (20:00) only bug fixes.

## Never stop

Until the freeze the loop continues without asking: take the most frequent failure in the last run, form one
hypothesis, change one thing, measure, record. If nothing fails once, switch to the confirmation run; its failures
are the next targets.
