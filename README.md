# Build the Builder: our entry

A builder that reads a bank's collections brief and its tool API file and creates a phone agent on Freya, with no
manual step.

```bash
pip install -r requirements.txt          # Python 3.10 or newer
export FREYA_API_KEY=fak_...             # your Freya workspace key
# a Claude login (Claude Code) or ANTHROPIC_API_KEY for the builder's model calls

python3 builder/build.py {brief_path} {tool_api_path}
```

A brief that builds on another one takes both files, base first:
`python3 builder/build.py briefs/brief-a.md briefs/brief-b.md tools/openapi.json`. A brief that comes as several
documents can be given as a folder; the tool API file is recognised by its content, so a code list in `.json` stays
brief material.

The slot name is the brief's file or folder name without its ending (`hidden-1.md` -> `hidden-1`). One run writes:

| File | What |
|---|---|
| `submission/<slot>.workflow.json` | the phone agent as exported from Freya |
| `traces/<slot>.log` | the trace: start and end, every model call with model and purpose, what was created, what was tested |
| `out/<slot>.spec.json` | the policy the builder read out of the brief |

A run takes five to eight minutes and five or six model calls. The model calls run with every tool switched off and
are made again when they fail; a run that still fails ends its trace with the reason.

## How it works

1. **Read** (`builder/extract.py`). Claude reads the brief and the tool API file into a policy spec: calendar,
   deadlines per lateness band, floors, persuasion offers, security questions, limits, outcome table, the fixed
   sentences. Two independent readings; a third call settles them only if they disagree on a rule or a value. Then
   the step instructions for the dialogue model are written and reviewed against the brief. Every value is checked
   against the tool API file before it is used. What a reading could not express in the spec is written to the trace.
   Rules that only some banks have are optional settings: a floor that is the greatest or least of several amounts,
   the order of the products, a time of day after which today is closed, the business day before a day that is not
   one, one read-back and recording per product, the bank's own limit on wrong security answers.
2. **Compile** (`builder/engine.py`, `builder/runtime.py`). No model involved. The spec becomes a Freya workflow of
   the same shape for every brief. The dialogue model listens and reports with code tools; it never writes to the
   bank and never words an offer. Code checks every day and amount, counts the persuasion attempts and the limits
   of the opening, speaks the offers, the read-back and the sentences the brief prescribes, makes the bank calls
   that change records, and closes the call exactly once. A safety net closes a call that breaks off.
3. **Check** (`tests/local_sim.py`). The compiled in-call code runs against a fake bank before anything is deployed.
4. **Deploy and export** (`freya.py`). The same slot updates the same workflow.

Nothing in `builder/` comes from a brief. `auto/check_generic.py` fails if a date, a name, a value or a sentence of
a known brief appears there.

## How it was developed

- `tests/scenarios.json`: 100 own practice customers (one and several products, manipulation attempts, other call
  days), scored like the kit scores: the bank's records must be exact and the judge must pass the conversation.
- `tests/heldout.json`: 12 more on other call days, kept out of the tuning.
- `auto/`: an improvement loop after Karpathy's autoresearch. One change per experiment, a fixed evaluation, keep
  or discard by rule. `auto/program.md` has the rules, `auto/results.tsv` every experiment, `auto/tests.jsonl`
  every single test.
- `tests/variants/`: a brief for a different bank in raw form (mail, policy extract, memo, code list) with another
  tool API, to see that the builder reads rules it has not seen.
- A second, independent session wrote two banks of its own without knowing the builder and audited what the
  builder made of them (branch `ibraschwan/second-view`). Its findings led to the optional settings above and to
  the crash fixes.
- `PROGRESS.md`: what was measured and when. `docs/`: what we noticed about the platform.

The starter kit's own README is `KIT_README.md`.
