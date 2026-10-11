# Independent organiser-perspective audit — preliminary report

Checkpoint: 11 October 2026, 17:20 Istanbul (before the requested 17:45 first version). Audit baseline `de4f07e`; branch `ibraschwan/second-view`. Builder files are unchanged. This report will be updated with live-chat and Cedar results before 18:45.

I would not expect this builder to hold reliably on an unseen brief that changes the *structure* of the policy. The most likely loss is a correctly read rule being forced into an engine that cannot express it, then silently approximated. A passing self-test does not expose that: the model itself explicitly identified unsupported floors, cutoff times, product ordering, per-product confirmations and transfer notes, but those warnings are discarded before the spec and trace are written. This is measured on an independent brief, not inferred from another Brief A run.

## Evidence and scope

- Independent dimensions and both briefs/customer scoring designs were written before opening builder/. Commit `fb39ca6` freezes the design. The API fixture was generated just after first inspecting build.py, but its nested fields and envelope had already been specified in the Cedar brief; this is a sequencing deviation, not concealed independence.
- `briefs/sv-one.md` uses the kit API. `briefs/sv-two.txt` plus `sv-two-memo.md` use a fresh nested API. Seven names are preserved for the contract-valid test. A separate renamed-tool fixture is explicitly beyond the final's guaranteed seven names.
- `customers/design.md`: 8 independent customer designs per bank with expected records and conversation criteria. `customers/live.json` and `live-adaptation.md`: same Alder behaviors bound to real public practice accounts, because no custom-bank-upload route is documented. Original odd-cent and custom-account cases remain local.
- `results/local-sv-one-b.json`: 16 named deterministic mechanism probes using **out/sv-one-b.spec.json**, the unchanged runtime, and tests/local_sim.py. They are not dialogue runs and cannot establish dialogue pass rates.
- `results/model-evidence.json`: recovered final model outputs and usage from this audit's SDK sessions only. No thinking blocks. These are valuable evidence that the extraction *noticed* missing expressiveness.
- Local replay: `python3 second-view/audit_local.py sv-one-b`. No main-line scenarios, heldout cases or simulations have been run.

## Findings, highest expected exposure first

### F1 — Unsupported rules are knowingly approximated, and the warnings disappear

Origin: reading/engine contract and build trace. Evidence: `builder/extract.py:185` requests an explanation of unexpressible rules, then `policy_once` returns only `llm.json_of(text)`. In recovered SDK sessions `18149152-cfbd-40eb-acf1-42caf9cc17a7`, `aa179e67-ec02-4398-95eb-3ea69701004e`, `21ae3538-61bc-47d0-b326-cc73cf0baa98`, and `be960fa1-3359-4a58-a4eb-d9b73621c118`, the final text explicitly says floors/order/cutoff/transfer notes cannot be represented. The final trace instead says policy accepted and self-test passed (`traces/sv-one-b.log`, 125.5s and 334.5s).

This hits any brief requiring a policy operation outside the fixed schema; a different number inside a supported operation is much safer. Conditional cost: all customers touching an omitted rule; 30/30 is possible for a universally required change, but hidden prevalence is unknown. Do not sum this with its concrete manifestations F2–F6. No fix proposed yet; a fail-closed unsupported-rule check would prevent silently wrong deployment but could leave no agent, so it is not a scoring fix by itself.

### F2 — Amount floor loses max() and rounds down a required ceiling

Brief O8 line 27 requires min(arrears,max(ceil(50% arrears to cents),service minimum)). Spec `/product/types/credit_card/floor` is only `{percent_of_full:50}`; both loan floors are only `{field:instalment_amount}`. Runtime `terms`, `builder/runtime.py:221`, permits only field OR percentage OR constant, and uses round(), not ceiling.

Measured locally: arrears 401.01 / service minimum 80 requires 200.51, engine gives 200.50 and accepts it. With service minimum 300 it still gives 200.50. Evidence: results/local-sv-one-b.json probes O8. On loans whose half-arrears exceeds the instalment, it underestimates the floor by an arbitrarily large amount. This hits compound or rounding-sensitive floors, not all briefs. Conditional cost out of 30: N customers accepting or offering a value the wrong floor admits, with N unknown. No proposal; a generic expression/rounding schema is needed, not a bank-specific constant.

### F3 — Transfers erase mandatory notes; a singleton dispute can terminate before transfer

Brief O10/O12/O15 lines 32/34/37 require notes before transfer and retention. Spec `/notes/enabled=true`, `/notes/reasons` are correct, but no transfer-note setting exists. `NOTE_NEXT` at runtime.py:707 gates notes on `not st['transfer']`; `TRANSFER_POST` immediately routes to goodbye. Local two-product probe records transfer general and transferred/human but zero notes, expected p1 dispute and p2 refused. A singleton `set_note(dispute)` immediately closes no_promise/dispute; the transfer is no longer reachable. Generated `/prompts/negotiation` R1 asks for both tools in one message; actual live ordering is still to be measured.

Exposure: any brief requiring notes on escalation. Conditional cost: N qualifying transfers out of 30, potentially every transfer. No proposal; making notes precede transfer has failure-ordering and duplicate-write risks and would change Brief B's opposite rule unless configurable.

### F4 — Product order and individual commitment timing are fixed to Brief B behavior

Brief O6 line 18 requires descending days late, then individual read-back/confirmation/recording before moving on. Spec has no sort or confirmation-mode field. `/prompts/negotiation` instead instructs account/FACTS order. `PREPARE` runtime.py:445 preserves returned order; `SYNC` asks the next open product before reading agreements back.

Local p1 late=4, p2 late=22 still lists p1 first. After agreeing p2 600 today, the engine asks about p1 instead of reading p2 back. Evidence: O6 probes in local-sv-one-b.json. Exposure: order changes and per-product consent requirements. Conditional cost: N multi-product customers subject to these requirements, 0–30 unknown. No proposal; confirmation and already-recorded-product transitions need configurable semantics.

### F5 — Cutoff is not enforced; backward adjustment gets contradictory tool guidance

Brief O4 line 13 requires no same-day payment at or after 15:00 and backward holiday adjustment. No cutoff exists in the spec. `SET_PROMISE` checks date against today, not the time. Local at 2026-10-15T15:00 accepts payment on 15 October, where earliest is Saturday 17 October. On holiday 16 October with now 14 October, expected adjustment is Thursday 15 October, but the tool says both “Do not move it forward to Saturday 17 October” and “If the customer accepts, CALL check_terms with 2026-10-17.” `/guidance/not_business_day` contains the right words while runtime supplies the wrong final command.

Exposure: cutoff/backward-roll briefs, not simple forward-only calendars. Conditional cost: N such date choices among 30, unknown. The Tuesday–Saturday calendar and holidays themselves are extracted correctly. No proposal; earliest-date and roll-direction policy need first-class representation.

### F6 — Identity maximum and non-answer semantics are not controlled by policy code

O3 line 9 says stop at two wrong answers, kit bank allows three. Local two wrong phone answers leave the call open. The reviewed dialogue prompt explicitly patches this by telling the model to close when wrong_answers_left=1, so **this is a missing deterministic guarantee, not yet a proven live failure**. The top-level instruction also says obey tool guidance, while that guidance demands the same question again. O9 line 28 says silence is not a refusal, but two `STALL` events close a zero-attempt product as refused locally. A stall event represents six messages without a tool, not merely two customer messages.

Exposure: limits differing from bank response, or non-answer policies differing from the engine. Conditional cost: N customers crossing those boundaries; unknown. No proposal; preserve hints and per-question resets when introducing configurable counters.

### F7 — Build failure loses trace completion and cost accounting

First Alder invocation `sv-one` exited 1 during reconciliation: SDK “Reached maximum number of turns (1).” The raw SDK session shows a Bash search attempt despite the builder's intended no-tools call. No spec/workflow was produced. Original trace ends after the two policy readings; no END and no auto/spend.tsv entry. `results/sv-one-failure.md` records the exception chain. Retry `sv-one-b` succeeds unchanged, so this is a build/model-SDK failure, not an agent policy score failure.

A single final invocation hitting this yields no submitted agent (potentially 30/30 lost for that brief); frequency is not estimated from two builds. Completed first-attempt calls cost $0.79, excluding the failed call; successful retry costs $1.47. No proposal yet. A try/finally ledger/trace plus tool-disabled SDK configuration would improve observability/reliability but requires careful SDK verification.

### F8 — Failed note writes still close with the original reason

O14 line 36 says after two failed note writes close no_promise/service_error. The local fake bank was configured to fail add_note twice; it recorded no notes but close_call no_promise/refused. Two retries occurred; error precedence is wrong. Evidence: final O14 probe, runtime NOTE_NEXT. Conditional cost: N double-note-write failures, not an estimated platform failure frequency. No proposal.

## Correct readings and checks so far

In brief order: bank/opening/automated/recording text; phone then birth-date question order; DMY dates and swapped-month hint; immediate first security refusal; Sunday/Monday closures and all three holidays; callback exclusion of today, two-working-day horizon and 09:15–12:45 window; all three band boundaries, business-day offsets and 2/1/0 budgets; deadline-based persuasion offers; immediate human queue and outcome pairs in prompts; paid two-working-day sentence; confirmation question, portal sentence, no-SMS instruction and branch direction for later changes. Local probes confirmed first security refusal, Saturday acceptance, two-day callback and singleton zero-persuasion closure with a note.

## Build/live inventory and spend (checkpoint)

| Slot | Result | Workflow | Agent | Reported cost |
|---|---|---|---|---:|
| sv-one | extraction failed | none | none | $0.79 completed calls + unreported failed call |
| sv-one-b | deployed, 341s, 5 calls | fc696bd6-e957-4890-9a66-5ba29138d0c8 | 58b2c2b3-0668-4e83-9f17-cdaf0dcabc9b | $1.47 |
| sv-two | no-deploy build running | none | none | pending |

Reserve $0.50 for the first failure's unreported call when enforcing the $5 ceiling. Inherited auto/spend.tsv rows belong to the baseline and are excluded; the missing failed-run cost means that file alone understates this audit. No simulations, personas, non-sv workflows or candidate mutations.

## In progress / not established

Live chat judgments and exact ledger scores are in progress, not claimed as passes. Cedar build and strict nested API execution are pending. Two full successful independent builds per brief have NOT been achieved; a failed build is not a second policy measurement. A .txt + overriding memo is in the Cedar invocation; contradictions and renamed-tool behavior are not yet run. No fixes to builder/ have been made. No hidden-case pass rate is estimated. The hypotheses above will be qualified by final evidence rather than retroactively changing our briefs to suit the builder.
