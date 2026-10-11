# Progress: Build the Builder (Freya hackathon)

State as of Sunday 11 October 2026, 19:05 Istanbul. Hidden briefs open at 20:00, submission closes at 23:00.

## Where we are

- **The builder that will be used at 20:00 is commit `3d61767`** (branch `ibraschwan/freyavoice-hackathon`, pushed).
  It is the candidate of the afternoon (experiment 4) plus what a second, independent audit and the talking-style
  runs found today. 162 local checks pass; `auto/check_generic.py` passes.
- **Measured on the agent this builder makes from Brief A+B** (slot `x5-final`, agent `46b306a6`, version 2):
  one full run of the 100 scenarios, **96 passed, bank records right on 97**. More runs are under way (see below).
- **Measured on the afternoon's candidate** (agent version 9, the builder before today's additions): three full runs
  100 / 94 / 96, the 12 held-out scenarios 12 of 12 in three runs.
- **Model spend of the builder so far:** about 20 USD of 30 (the loop 3.5, the second audit about 4.3, today's
  rebuilds about 12). Two final builds cost about 3.5.

## What changed in the builder today, and why

| Change | Why | Evidence |
|---|---|---|
| Model calls run with every tool switched off and are made again when they fail; unreadable JSON is asked for again | On a brief the builder had not seen, a model call reached for a tool and the build died with no workflow (two of the second audit's three builds) | Reproduced with a one-line prompt; with `tools=[]` it answers in one turn |
| Six optional settings in the policy: floor as the greatest or least of several amounts (with rounding), order of the products, a time of day after which today is closed, the business day before a day that is not one, one read-back and recording per product, the brief's own limit on wrong security answers | The second audit's brief had these rules; the engine could not express them and approximated them silently | Without the settings nothing changes (the 104 old local checks pass unchanged, 58 new ones); the re-read A+B policy uses none of them except the limit of three wrong answers, which equals the bank's count; on the audit's brief all six are filled correctly; three live conversations on that agent (order, cut-off, one-by-one recording, two wrong answers end the check with no disclosure) |
| A security answer given in parts is joined in the order said; only the rest is asked for | With the kit's style `pieces` the candidate repeated the whole question after two digits and sent the parts in the wrong order or not at all (4 real failures of 100) | Subset of 20 in `pieces`: every identity step with parts now verifies |
| A callback date in the past does not use up the one new try | The second audit saw the model write a date in a wrong year and lose the customer's only correction | local check |
| The build command takes a folder, tells the tool API file by its content, leaves out files that are not text | A raw-material brief may come as several documents, a code list may be `.json` | tried on a made-up folder |
| What a reading could not express is written to the trace; a failed run ends its trace with the reason | The readings' own warnings were thrown away; a failed build left a trace without an end | `traces/` of the last builds |

A malformed optional setting is taken out after two repairs instead of ending the build.

## Results of today, in the order measured

Same 100 scenarios unless said otherwise. "Passed" is the judge's verdict on the call with the bank records right.

| When | Agent | Run | Passed | What failed |
|---|---|---|---|---|
| 03:49 | candidate v9 | plain | 100 / 100 | |
| 15:26 | candidate v9 | plain | 94 / 100 | 3 calls the customer ended while the agent's model was silent for 53 to 56 s, 2 without a verdict (one call never took place), B10 one persuasion offer too many |
| 15:59 | candidate v9 | plain | 96 / 100 | 3 calls cut the same way, A17 the simulated customer left its script |
| 16:22 | candidate v9 | held-out 12, three runs, 10 calls at once | 12 / 5 / 8 | all 11 failures: the customer's first sentence was never answered for 60 s |
| 16:36 | candidate v9 | held-out 12, three runs, 5 calls at once | 12 / 12 / 12 | |
| 16:54 | candidate v9 | style `pieces` | 91 / 100 | 4 real (number in two parts at the security question), 4 bank or sandbox failures, 1 judge reading |
| 17:17 | new builder, first A+B build | plain (two agent versions mixed) | 96 / 100 | 4 calls the customer ended |
| 17:31 | new builder | `pieces`, 20 identity scenarios | 14 / 20 | no failure at the security questions any more; 6 calls in which `create_promise` failed twice at the bank |
| 17:48 | new builder | `in_words`, 25 scenarios | 25 / 25 | |
| 17:59 | **final builder, slot `x5-final`** | plain | **96 / 100** | X13 sandbox returned nothing; A45 the platform played the call a second time on the same bank session; B02 the simulated customer mixed up its two products; X09 the model reported a date after the deadline as a refusal (the only one owned by the agent) |
| 18:13 | final builder | `pieces`, 20 identity scenarios | 13 / 20 | all 7: the call stopped answering around 18:15 and even the closing request got a Cloudflare 530 from the platform |
| 18:21 | final builder | `corrects`, 25 scenarios | 0 / 25 | platform down: in 16 calls the customer's first sentence was never answered, the rest were cut later |
| 18:46 | final builder | held-out 12, 5 calls at once | 5 / 12 | 3 calls that had passed were played again by the platform on the same bank customer (twenty more `verify_identity` after the close), 4 calls in which `create_promise` got no answer twice |
| 18:56 | final builder | `corrects`, 25 scenarios | 22 / 25 | A45 and A49 `create_promise` failed at the bank; B10 persuasion offers counted wrongly (weak point 2) |
| 19:04 | final builder | `asks_back`, 25 scenarios | 22 / 25 | B10 again; A29 the simulated customer's question back was "Is there a payment plan?", which the brief answers with a transfer, so no promise followed; A05 after answering the flatmate's question the agent repeated its request for another time and the judge counted two requests |

Three runs of all 100 on the candidate: 90 scenarios passed in every run by the call verdict, 82 by the run outcome
the kit's script reads. Of the 10 that did not: 6 platform silence, 2 no verdict, 1 simulated customer, 1 agent (B10).

The platform was degraded for much of the afternoon (about 14:00 to 15:06, again around 16:20 and 17:20, and from 18:15 to about 19:00).
A run in such a window says little about the agent; `docs/run-outcome-vs-call-verdict.md` has the measurements that
tell a silent platform from a wrong agent (answer times, calls ended by the customer, calls with no verdict).

## What the second audit found (branch `ibraschwan/second-view`, `second-view/REPORT.md`)

An independent session wrote two banks of its own before reading the builder, built from them and talked to the
result. Its findings, and what became of them:

| Finding | State |
|---|---|
| The build dies when a model call reaches for a tool; no end in the trace | fixed |
| Floor as "the greater of", rounded up | fixed |
| Order of the products, one confirmation per product | fixed |
| Cut-off time for today; the business day before | fixed |
| The brief's limit on wrong answers is lower than the bank's: the agent asked a third time and disclosed the debt | fixed, checked in a live conversation |
| The readings' warnings about rules they cannot express were thrown away | now in the trace |
| An invented callback date uses up the customer's correction | a date in the past no longer does |
| **Notes are not written when a transfer follows** (a brief that wants both) | open |
| **A tool API with nested request and response bodies cannot be built** | open; the build ends with a clear error |
| A note that cannot be written twice does not change the closing reason | open, rare |
| A close request repeated by the platform | open, cause unclear |

## Known weak points

1. **A hidden brief whose structure the engine does not have**: nested tool bodies, notes together with a transfer,
   anything else outside the settings above. The trace now says so in the reading's own words.
2. **"I cannot pay that"** after the full amount is asked: the model sometimes reports it as "too much", the engine
   then offers the floor once as the brief says, and a judge can count one offer too many (B10, 1 of 3 runs).
3. **A date after the deadline demanded as an instruction** can be reported as a refusal (X09, 1 of 4 runs).
4. **The platform**: a call in which the agent's model, the sandbox or the bank does not answer fails whatever the
   agent is. Seen in every run since 15:00.

## At 20:00

```bash
cd <this repository>
source env.sh && source .venv/bin/activate
python3 builder/build.py <brief file(s) or folder of hidden brief 1> <its tool API .json> --slot hidden-1
python3 builder/build.py <brief file(s) or folder of hidden brief 2> <its tool API .json> --slot hidden-2
```

Each run takes five to eight minutes and five or six model calls, deploys, exports and writes
`submission/hidden-N.workflow.json`, `traces/hidden-N.log`, `out/hidden-N.spec.json`. The limit per brief is thirty
minutes. Read the trace afterwards: the lines "could not express" name the rules of that brief the agent only has in
its instructions.

Then commit `submission/` and `traces/`, push, and submit with:

```json
{
  "team": "<team name>",
  "repo": "https://github.com/ibraschwan/freyahackathon",
  "commit": "<hash after the push>",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": {"hidden-1": "submission/hidden-1.workflow.json", "hidden-2": "submission/hidden-2.workflow.json"},
  "traces": {"hidden-1": "traces/hidden-1.log", "hidden-2": "traces/hidden-2.log"}
}
```

The repository is private: the organisers need access to it, or it has to be made public before submitting.
After the hidden briefs open, only a crash may be fixed in the builder. No rule, value or name from a hidden brief
may go into it.
