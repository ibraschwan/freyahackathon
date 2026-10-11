# Independent organiser-perspective audit — final report

Final: 11 October 2026, before 18:45 Istanbul. Preliminary report was pushed at 17:20 (`40044c2`, evidence inclusion `8e660a4`), before the requested 17:45 checkpoint. Audit baseline `de4f07e`; branch `ibraschwan/second-view`. Builder files and the main candidate are unchanged. No fixes are proposed or deployed. The numbered findings below retain their checkpoint identifiers; F9 is the highest-exposure concrete API finding and F6 is the highest-severity live privacy finding.

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

## Final live evidence, strict policy judgment and platform separation

One conversation per original customer, not three repetitions. `results/chat-SV1-XX.json` contains complete fetched provider messages, bank ledger and turn timings; `results/chat-summary.json` gives indexed speech/events. The built-in ledger scorer passes 5/8 original cases, but two of those violate conversation/tool policy. Only SV1-01, 02 and 06 have correct observed records and policy in these observations, all with ending-transport qualifications. **This is not a hidden-case pass-rate estimate.**

| Case / call id | Records and strict audit | Transport |
|---|---|---|
| 01 / d70dd62d-2224-4b77-acad-36e9a6ea6e31 | 420 today, portal sentence, one close: correct observed | Ending 504, 21.758s; concurrent auditor end/send confounds ending timing; see transport note |
| 02 / 455d3494-596e-4e9c-bbcb-6eaef9438486 | Floor 1062.55, explicit consent and portal: correct observed | Ending 504, 33.312s |
| 03 / 335747f9-d12d-4681-b970-434f74da6450 | **Fail O3:** two wrong answers followed by third phone attempt, DOB, account fetch and disclosure of 95 arrears. Expected failed verification without disclosure | No 504; ledger snapshot has no close |
| 04 / 9f2f93bc-6696-438c-8f9b-41e7651b69e4 | Date 17 October correct, ledger score passes; **fail O15:** three close_call bank invocations, two rejected as already closed | Ending 504, 60.286s |
| 05 / bfa5bad1-d5f9-44ac-b778-d7c23a30099c | **Fail O5:** requested Friday 16 then Saturday 17; model sent May 2025 twice, used replacement allowance, no callback. Expected 17 October 2026 11:30 | Ending 504, 19.070s; wrong tool dates precede it |
| 06 / d2e46e8d-7cd7-488e-ab57-bf9a0c8155f5 | Zero extra persuasion, singleton refused note and correct closure: correct observed | Ending 504, 20.618s |
| 07 / a3563945-7f96-471e-ad2d-482751888f25 | **Fail O12/O15:** general transfer but no dispute note | Ending 504, 44.196s; missing note is separately in bank records |
| 08 / 51afc781-5357-4256-a562-4d938cdd518d | Eventual loan promise 900 and card paid note correct; **fail O6:** card first despite loan older, asks next product before individual loan readback | Ending 504, 30.328s |

F6 is now a **proven live failure**, not just a missing deterministic guarantee. In case 03 provider messages 13/21 are the first two checks, 24 asks illegally again, 29 verifies the third answer, 37 verifies DOB, 41 fetches account and 49 discloses the debt. Expected not_verified/failed, no account fetch. Its later ending cannot undo that disclosure. The reviewed prompt's two-wrong patch lost to engine guidance.

F3 is live-confirmed in case 07: provider messages 38/40 show skip_product then transfer, but ledger has zero notes versus expected dispute note. The model did mark the dispute; the engine transfer gate loses it. F4 is live-confirmed in case 08: account order and deferred readback are directly observable. The script includes an unsolicited loan confirmation before the agent's loan readback; it correctly ignores that, which does not excuse wrong order already observed earlier.

Seven original calls encountered an ending 504. These are **not scored as policy failures merely because they timed out**: retrieved transcripts and bank writes show substantial completion, including goodbyes. Attribution between platform routing, workflow execution and ending behavior is unresolved. Case 01 also has an auditor concurrency mistake: end was initiated while the last send was pending, and concurrent saves lost that error row. `results/chat-SV1-01-transport.md` preserves it; do not use that ending as clean latency evidence.

### F9 — Nested API contracts cannot be validated or executed; fake bank hides the mismatch

Cedar preserves the seven guaranteed operation names but changes body fields, response envelope and success enum. `results/cedar-api-sv-two.json` uses the recovered **intermediate** reconciled policy, not a completed spec/workflow. The reading correctly maps dotted fields, but extraction validation rejects 14 body paths because it only sees top-level member_token/request. `engine.bank_tool` converts the nested request object to string and defaults member_token to its own variable rather than documented customer_id alias. Runtime reads flat dotted keys and boolean success, not nested result.state=ACCEPTED.

Controlled local comparison with the same policy/account: existing Sim verifies all three challenges and loads one facility; NativeResponseSim returning actual nested contract stays unverified with zero products. Thus a passing spec-shaped fake-bank result is not evidence of actual API compatibility. Origin: schema validation, compilation and runtime API adapter, not unclear brief. Exposure: any nested request/response or enum-success API, potentially all 30 customers if universally required. No fix commit; a generic recursive adapter would also require matching fake-bank contracts and regression checks. Cedar build additionally fails during repair (F7), so no deployed Cedar score is claimed.

### F10 — Implicit callback dates acquire an invented month/year

Case 05 above invents 2025-05-16 and 2025-05-17 despite callback guidance specifying October 2026, then exhausts the customer's replacement allowance on its own date errors. Diagnostic control 09, call `6bf36202-69d3-47c2-809b-88a08bbec2a2`, repeats the behavior with explicit month/year: correct callback 2026-10-17 11:30 and not_reached/callback, one close, but ending 504 29.689s. Origin: dialogue date interpretation and retry charging; explicit-date success separates it from calendar-window extraction. One paired observation, no general reliability estimate. Cost: N implicit-date customers among 30, unknown. No fix commit.

### F11 — Exactly-one closure is not assured; ledger scorer misses duplicate attempts

Case 04 has three bank close invocations: provider messages 91 and 93 in close_call, 100 in end/close_call_at_end. First succeeds, later attempts return already closed. O15 requires exactly one; `tools/score.py` examines the last closure, not the count. Runtime CLOSE_PRE lacks a closed guard; fallback has one, so platform replay/state propagation is also a plausible cause. Do not attribute all three solely to the dialogue model. Exposure: closure replay/end-hook interactions, prevalence unknown, N affected customers out of 30. No fix commit; idempotency and persisted state need verification.

Diagnostic control 10, call `ed343d1e-5fb0-4e00-958f-d4a73cb96465`, supplies workflow now=2026-10-15T15:00 and explicitly offers 15 October. It records that date and says the portal sentence, while expected earliest is 17 October; two closes and ending 504 60.290s. **Clock caveat:** practice ledger still reports its session clock 2026-10-14T11:00, so this is not an independent bank-clock cutoff test. Workflow receives overridden now; local F5 at cutoff is the unconfounded engine test. Case 04's correct holiday adjustment does not establish cutoff enforcement.

## Build/live inventory and spend (final)

| Slot | Result | Workflow | Agent | Reported cost |
|---|---|---|---|---:|
| sv-one | extraction failed | none | none | $0.79 completed calls + unreported failed call |
| sv-one-b | deployed, 341s, 5 calls | fc696bd6-e957-4890-9a66-5ba29138d0c8 | 58b2c2b3-0668-4e83-9f17-cdaf0dcabc9b | $1.47 |
| sv-two | no-deploy extraction/repair failed; about 401s | none | none | $1.08 completed calls + unreported failed call |
| sv-two-renamed | existing-spec compile rejected missing required tool names; no model calls | none | none | $0 |

Known completed-call costs total **$3.34**. Two failed SDK calls have no returned monetary cost; reserve $0.50 each, for a conservative working envelope of **$4.34**, not a verified final bill. Each failed session recorded roughly 20–21k cache-creation input, 10.6k cache-read input and 0.8–1.1k output tokens; usage is in model-evidence.json. No further paid builds were launched. Inherited auto/spend.tsv rows belong to baseline; failed invocations produce no row and understate audit spend. No simulations, personas, non-sv workflows or candidate mutations. Deployed Alder export is intentionally not committed under submission/.

Cedar completed policy calls at $0.35/$0.36 and reconciliation $0.37, then validator rejection triggers repair whose Bash search attempt hits SDK maximum turns=1. Thus F7 happened in two of three full build invocations; this small audit is not a frequency estimate. Both fail well within 30 minutes, but leave no deliverable or completed trace. Successful Alder is 341.4s, 14 steps, workflow 470515 bytes. Trace/secret checks are in artifact-check.json, with zero secret matches.

## Repeated readings, correct rules and uncompleted coverage

`results/reading-comparison.json` compares recovered policy JSON readings, not independent completed agents. First Alder pair differs on loan floor: 50% versus instalment. Neither fully expresses O8. Cedar initial pair differs on extra-offer counts: correct 1/1/1 versus incorrect 2/2/2; reconciled intermediate returns correct counts. This is extraction variability even though no second completed Cedar build exists.

In Cedar rule order: C1 bank name and opening/privacy instructions extracted correctly. C2 all three questions extracted, but wrong-count ceiling lacks deterministic per-challenge implementation. C3 memo M1's 60% overrides 40% in all recovered readings, and revised 4/2/1 deadlines are extracted; ceiling limitation remains (F2), and initial extra-offer counts vary. C4 calendar, forward adjustment wording and memo M2's callback 10:20–14:40 are extracted. C5 nested product mapping is read but not executable (F9); rank order and individual recording have no engine setting (F4). C6 exact memo M3 office sentence and no-SMS rule are extracted, but ACCEPTED success enum cannot be consumed correctly (F9). C7 escalation/note policy meets the same transfer-note engine limitation. C8 custom outcome/reason codes are read, but exactly-one closure is not proven (F11 class). Correct extraction does not establish executable Cedar behavior.

Deliverable coverage: .md table brief succeeds; .txt plus overriding memo is accepted and read, but later API repair fails. Renamed operations are intentionally **outside** final's seven-name guarantee: zero-model existing-spec compile rejects all seven missing names (`results/renamed-tools-console.log`), not a scored contract-valid defect. This is not a fresh Cedar reading. Artifact checker confirms builder unchanged and no credentials in audit artifacts.

Not completed: two successful full builds per brief; eight Cedar customer conversations; repeated live runs for robustness; hard contradictory-brief test; full live hardship, note-write-failure, rounding, swapped-hint and persuasion-question dialogues. Some have extraction/local evidence only, identified above. No hidden cases accessed; no fixes or regression suites run because builder was not changed. There is one full successful build, two failed builds, 16 Alder local probes, one Cedar paired response-shape probe, eight original live conversations and two post-observation controls. Do not reinterpret SDK sub-readings or controls as fulfilling missing full builds or predesigned customer coverage.
