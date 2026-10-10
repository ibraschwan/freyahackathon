# Progress: Build the Builder (Freya hackathon)

State as of Sunday 11 October 2026, 00:40 Istanbul. Hidden briefs open at 20:00, submission closes at 23:00.

## The task in one paragraph

We submit a **builder**: one command that reads a bank's collections brief and its tool API file and creates a
phone agent on Freya, with no manual step. The organisers run that agent against simulated customers. A customer
counts only if the bank's records are exactly right, the conversation stayed inside the brief and the agent told
the truth, three runs out of three. Two hidden briefs, 30 customers each.

## What exists

| Part | Where | What it does |
|---|---|---|
| Builder command | `builder/build.py` | brief + tool API file in, deployed agent + exported workflow + trace out |
| Extraction | `builder/extract.py` | Claude reads the brief into a policy spec (numbers, names, tables, fixed sentences) and writes the step instructions. Two independent readings, a third call only if they disagree on a rule, then a review against the brief |
| Engine | `builder/engine.py` | compiles the spec into a Freya workflow. No model involved, same shape for every brief |
| In-call code | `builder/runtime.py` | the Python that runs inside the agent: date and amount checks, persuasion counting, recording, closing |
| Local fake bank | `tests/local_sim.py` | runs the in-call code without Freya or a model; 71 checks |
| Scenario suite | `tests/make_scenarios.py`, `tests/run_scenarios.py` | 68 own practice customers (50 one-product, 18 multi-product), scored like the kit scores |
| Variant brief | `tests/variants/` | our own brief for a different bank in raw form (mail, policy extract, memo that changes it, code list) with a different tool API |

## The design

The dialogue model talks and decides; it never writes to the bank.

- It notes what the customer agreed to with code tools. Code checks every amount and date against the spec and
  refuses with an instruction ("after the deadline: offer 23 October") when a value breaks a rule.
- The engine itself calls `create_promise`, `add_note` and `close_call`, speaks the sentences the brief prescribes
  (opening, debt statement, "your promise is recorded…", goodbye) and closes the call exactly once, last.
- Persuasion attempts are counted in code: the model reports a refusal and gets the exact next offer to say.
- A safety net closes any call that breaks off, from the records.

Nothing in `builder/` knows Brief A or B. Every number, name and sentence comes from the extracted spec.

## Measured results

All single runs. The final needs three passes out of three, so read these as upper bounds.

| Agent | Test | Passed |
|---|---|---|
| Kit's base agent | official Brief A (10) | 0 / 10 |
| Kit's example builder | official Brief A (10) | 9 / 10 |
| Kit's example builder | our 50 one-product scenarios | 42 / 50 (bank records right on 48) |
| Our engine, hand-written reference spec | official Brief A (10) | 10 / 10 |
| Our engine, hand-written reference spec | official Brief B (3) | 2 / 3, before the persuasion counter |
| Our engine, hand-written reference spec, Brief A+B rules | all 68 own scenarios | 63 / 68 (bank records right on 66) |

In the 68-scenario run all 50 one-product scenarios passed; the five failures are all multi-product.

Not measured yet: the agent our builder produces from the brief by itself (built and deployed, not yet run against
the scenarios), any `--style` variation except three scenarios, and three repetitions.

The builder's own run on Brief A+B: 4 to 5 model calls, about 4 minutes, about 1.5 USD.

## What we learned about the platform

- A pre-hook or code tool that raises stops the call before the bank is reached, and its message reaches the
  model. This is how a rule refusal is delivered.
- Prompts are rendered again on every model call, so a variable written by code steers the model at once.
- Engine-run bank calls in a loop (code step, API step, code step) take well under a second per call.
- A step re-entered silently has no assistant message, and the platform then suppresses routing on tool results.
  Every entry must speak. This cost four hung calls before it was found.
- The model sometimes makes two tool calls in one message. They run in parallel on the same snapshot of the
  variables, and the second write overwrites the first.
- A simulation can stay "running" after every call is judged when one verdict is "inconclusive".
- The network here blocks `*.workers.dev`; `FREYA_BANK_PIN_DNS=1` looks that one host up publicly.

## Open problems

1. **Parallel tool calls lose state.** Two of the five failures (B04, B12): the model noted a promise and a
   dispute in one message and one of them was lost. Fix in progress: the tools record events instead of rewriting
   one state value, and a code step merges them and speaks the next sentence itself.
2. **Judge reads our internal tool as a bank write.** B05: no promise was recorded, but the judge took
   `set_promise` for one. The internal tools need names that cannot be mistaken.
3. **A required sentence was skipped.** B03: with two products both "already paid", the model did not say that
   payments can take a business day. The engine should say it.
4. **Judge noise.** B16 was "inconclusive" with every check met.
5. **The built agent is untested.** The reference spec is hand-written; the builder's own output has to reach the
   same score, and has to be run three times.
6. **Hidden briefs cannot be rehearsed.** The bank mock only serves the public accounts, so the variant brief was
   checked by reading its spec and by the local fake bank, not by real calls.

## Next

1. Finish the event-based state and the code-spoken next sentence; rename the internal tools.
2. Run the 68 scenarios against the agent the builder produces, then with three repetitions and the kit's styles.
3. Fix what that shows, in the builder only.
4. Rehearse the final: clean checkout, one command per brief, export, trace, inside 30 minutes.
5. Freeze before 20:00. After the hidden briefs open, only bug fixes.
