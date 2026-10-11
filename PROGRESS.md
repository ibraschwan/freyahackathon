# Progress: Build the Builder (Freya hackathon)

State as of Sunday 11 October 2026, 15:05 Istanbul. Hidden briefs open at 20:00, submission closes at 23:00.

## Where we are

- **The builder is frozen at the code of experiment 4** plus plumbing that makes builds and test runs survive a busy
  platform. Nothing that changes what the phone agent does will be added without a strong reason.
- **Best measured result of the agent the builder makes by itself** (Brief A+B, agent version 9, rules extracted in
  build 5): **100 of 100 scenarios passed, bank records right on 100 of 100, no call ended by the customer**, one
  run, at 03:49. This is a single run. The final asks for three of three.
- **Not measured yet:** three runs of all 100, the 12 held-out scenarios on other call days, the kit's five talking
  styles. The confirmation run of experiment 4 was started at 14:15 and is crawling: since about 14:00 the platform
  answers every second API request with a timeout or a 504, and simulated calls are retried for many minutes.
- **Model spend of the builder since the loop started:** 3.53 USD of 30.

## How the score moved (agent built by the builder, 100 scenarios, one run each)

| Step | Passed | Records right | What changed |
|---|---|---|---|
| first build | 92 | 96 | |
| after fixes to the instruction writing and the engine | 97 | 100 | repeated questions capped, callback day checked first, required sentences in every branch |
| loop baseline | 98 | 100 | stall step in two stages |
| experiment 1 | 96 | 98 | discarded: nothing fixed by the 3-of-3 rule, records wrong in 3 of 54 calls |
| experiment 2 | 98 | 98 | not kept: the new counting tool closed a call it should not and swallowed a third wrong answer |
| experiment 2b | 99 | 99 | discarded: one scenario regressed (a question asked together with an answer was never answered) |
| experiment 4 | 100 | 100 | experiments 2 and 2b plus: a question that comes with an answer is answered in the same message |

Every experiment, with its commit, harness version, agent version and the reason for the decision, is in
`auto/results.tsv`. Every single test is in `auto/tests.jsonl`.

## What the three-run repeats have shown so far

Same agent, same scenario, three runs (judge's verdict on the call):

- Baseline: of 7 scenarios that had failed at least once, 4 passed 3 of 3; A12 failed 3 of 3; A20 and B10 passed 2 of 3.
- Experiment 2b, 20 scenarios: 17 passed 3 of 3 (A12 among them); A08 1 of 3; A17 and X25 2 of 3.
- Experiment 4: not repeated yet.

So a single run of 100 out of 100 does not mean 100 scenarios at three of three.

## Known weak points of the candidate

1. **A counter-offer can be lost** when the model reports a too-low amount and something else in one message (B14,
   X25: records wrong once each in three runs, before experiment 4). A fix exists outside the tree
   (`.context/exp3n`, 116 local checks pass): the engine itself words the counter-offer. It needs the brief to be
   read again and has never run in a real call, so it is not in the candidate.
2. **Persuasion attempts on several products** can come out one too many (B10: 2 of 3 at the baseline).
3. **One call lost its code environment** (every code step failed 35 times in a row; nothing was recorded). Seen once
   in about 800 calls, not reproduced. Nothing in the workflow can rescue such a call.
4. **Judge noise:** a call the judge passes can read "inconclusive" on the run. Our runner settles those with the
   verdict stored on the call and logs both readings. The kit's script reads only the run.

## What we noticed about the platform

`docs/run-outcome-vs-call-verdict.md` has the ids for the organisers: run outcome against call verdict, a simulation
that stays "running" and blocks the workspace, and the call with the broken code environment. Not sent to anyone yet.

## At 20:00

```bash
cd /Users/ibrahim/conductor/workspaces/freyahackathon/port-of-spain
source env.sh && source .venv/bin/activate
python3 builder/build.py <brief file(s) of hidden brief 1> <its tool API .json> --slot hidden-1
python3 builder/build.py <brief file(s) of hidden brief 2> <its tool API .json> --slot hidden-2
```

Each run reads the brief (about four minutes, four or five model calls), deploys, exports and writes:
`submission/hidden-N.workflow.json`, `traces/hidden-N.log`, `out/hidden-N.spec.json`. With the platform as slow as it
is now the deploy alone took ten minutes at 14:50; the limit per brief is thirty.

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
