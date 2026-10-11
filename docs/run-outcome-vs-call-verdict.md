# Run outcome and call verdict disagree in simulations

Observed on 11 October 2026 on `staging-app.freyavoice.ai`, workspace `686221c4-a7e8-4c9d-af8f-db0781714a4f`, while running the practice customers
with `runsPerPersona: 1` three times in a row for the same seven personas (the way `tools/run_cases.py --reps 3` does it).

## What we see

The judge's verdict is stored in two places: on the run (`GET /api/v2/simulations/{id}/iterations/{id}` -> `runs[].outcome`)
and on the call (`GET /api/v2/call/{id}` -> `successCriteriaResult.success`). They do not always agree:

1. A run can read `inconclusive` while the call holds a clear verdict (`success: true` or `false`).
2. After the same personas are run again in a later simulation, the runs of the earlier simulation read `inconclusive`,
   although the iteration's own counters (`passedRuns`, `failedRuns`) still show the original verdicts.

`tools/run_cases.py` counts a customer as passed only when `runs[].outcome == "pass"`, so a call the judge passed can be
scored as failed, and with `--reps 3` a customer needs three such readings.

## Evidence

### Simulation `abee67ec-d201-43b0-ac7b-183614aa57c1` ("scen 02:12:31"), iteration `93fa0409-f814-4120-8c1d-9e701c32646f`

Iteration counters: totalRuns 7, passedRuns 0, failedRuns 0, inconclusiveRuns 7, status completed.

| persona | run id | `runs[].outcome` now | call id | `successCriteriaResult.success` |
|---|---|---|---|---|
| A01 Never confirms who he is | `3626eff3-63f4-45d4-9339-e3f339eeecfd` | inconclusive | `65fe0afd-03b2-427c-94be-b7434a7913d0` | True |
| A05 Flatmate, first time out | `4f1a0d96-406e-45bf-9ed9-7c08371a9105` | inconclusive | `b9e9ce5a-58dd-4297-9aa7-3d7f52ff93ea` | True |
| A12 Asks what the call is ab | `1e8ad3ee-3637-44a4-9d6b-f6dd6c7d7845` | inconclusive | `a584b487-105c-4618-a280-6ffe131caa09` | False |
| A20 Only a date after the de | `f7f13f0a-efd2-4ba4-9d45-cb10368c59f0` | inconclusive | `429f6242-eccd-49c9-8f45-a4f998d85637` | False |
| A37 A death in the family, b | `d6815aeb-e011-4253-81c2-0bea9985f15a` | inconclusive | `2da9184e-7a6d-4c67-8d71-4fa5b29eb4c5` | True |
| A40 Asks for a human, then l | `ca9352f6-f036-4eef-bae0-8d4df5c5970b` | inconclusive | `faa2f989-964c-4b0f-8ca4-a68bf13b0836` | True |
| B10 Refuses all three | `33022f44-5956-4f6c-95ae-728d0d46de99` | inconclusive | `f1d62e95-3789-47f7-86d4-56d08bff34df` | True |

### Simulation `3a210fe6-5db0-430d-9410-10bc5164965f` ("scen 02:16:20"), iteration `36b2be83-e8ae-4a94-8126-61deaa5d5c94`

Iteration counters: totalRuns 7, passedRuns 1, failedRuns 1, inconclusiveRuns 5, status completed.

| persona | run id | `runs[].outcome` now | call id | `successCriteriaResult.success` |
|---|---|---|---|---|
| A01 Never confirms who he is | `baad1289-7cc5-43ca-93be-9f35028fd589` | pass | `5ab75c82-daa0-4513-9804-3d27500d7036` | True |
| A05 Flatmate, first time out | `bd1361d2-0d5f-40b7-8261-ad16c992fe03` | inconclusive | `d47f944b-5546-4f2c-bc43-fc02421c2888` | True |
| A12 Asks what the call is ab | `576c3739-da38-4208-84da-0a70356e2e93` | inconclusive | `fd3e0c3d-567a-41ad-960e-4434c1009f41` | False |
| A20 Only a date after the de | `a0a2f83d-1f6f-4cfb-af77-d8cbfb0e13e0` | inconclusive | `25685698-c810-47ee-94e5-ebb71c3f63c9` | True |
| A37 A death in the family, b | `ecf5bce7-8569-426b-bf64-144d9234abd1` | inconclusive | `69c205b2-84a2-40d7-809f-b2e965f882f0` | True |
| A40 Asks for a human, then l | `8171760a-7982-4731-8652-b3940329b536` | inconclusive | `defcb723-651b-4812-8e43-71248fe77230` | True |
| B10 Refuses all three | `fd27a23a-c60e-45cd-b7d5-b4f781a3593d` | fail | `02384986-68d8-4f37-8d41-deb75d160659` | False |

### Simulation `83ae6f0f-c626-4c08-a15a-33ff458853cd` ("scen 02:19:03"), iteration `5ee33143-719b-4040-aec8-f851c7200e0d`

Iteration counters: totalRuns 7, passedRuns 4, failedRuns 0, inconclusiveRuns 3, status completed.

| persona | run id | `runs[].outcome` now | call id | `successCriteriaResult.success` |
|---|---|---|---|---|
| A01 Never confirms who he is | `3cf02d72-52f3-4aa6-a0f2-a179a5ebbe64` | inconclusive | `cf7e050d-e30c-498c-a946-8646bf476f22` | True |
| A05 Flatmate, first time out | `20b9a53f-c26a-4357-9c6f-e6c592aa6162` | inconclusive | `78f1c9c4-acc0-48e8-9a1a-0cdca774c5b1` | True |
| A12 Asks what the call is ab | `417926b2-d0b7-425d-9360-3bcf1ffe3051` | inconclusive | `8a24d306-c987-4b65-b076-7958ad71603f` | False |
| A20 Only a date after the de | `eac5ff32-5a65-44a4-9cf5-3436d54867b1` | pass | `4823d9d9-340a-40ef-814a-0a9530652fa2` | True |
| A37 A death in the family, b | `fc25b061-bb4a-4c62-aacf-6c01b7533a46` | pass | `bcd8b738-e2dc-487d-adfd-efdf0bdfcb3e` | True |
| A40 Asks for a human, then l | `e17b1306-be0b-42f0-bf41-c3fa29ebfb53` | pass | `7da73f78-a13f-4c9a-9773-3f2aebfbda0e` | True |
| B10 Refuses all three | `98528854-fa32-4c37-97fe-f248289e3123` | pass | `f275acf3-7bfb-4f2d-b9c5-58d96eac26b2` | True |

## A second, smaller thing

A simulation can stay at status `running` after every run has a verdict. Seen on simulation `8ceab80d-3903-4fa5-bcda-8103185694eb`
(68 runs: 64 pass, 3 fail, 1 inconclusive). While it stays `running`, `POST /api/v2/simulations` answers that another simulation is running,
so the workspace is blocked until the status is set to `completed` by hand (`PUT /api/v2/simulations/{id}` with `{"status": "completed"}`).

## What we do about it

Our own runner (`tests/run_scenarios.py`) takes `runs[].outcome` when it is `pass` or `fail`, and reads the verdict on the call otherwise.
A call with no verdict at all stays failed. Both readings are logged for every test (`auto/tests.jsonl`, `auto/report.py`).
We do not know which reading the final scoring uses.

## A third thing: a call in which every code step failed

Call `e6c9d54b-f817-4f85-a225-a6a32f5fafbc` (11 October 2026, about 00:19 UTC, practice customer id `c_4664a827-dd0`). After 41 seconds of normal conversation
every `code_exec` step of the workflow answered `Sandbox did not return a parseable result (returncode=0). Stdout: __CODE_EXEC_RESULT__{"vars": ...`,
35 times in a row, including the `pre_process_code` of the end-of-call tool. The same snippets had run without error earlier in the same call,
and the same conversation replayed over `POST /api/v2/chat/message` ran through. The variables of the call were small (147 variables, about 12 kB of values).
The customer had confirmed three promises; none was recorded and the call was not closed. We have seen this once in about 800 simulated calls.

## A fourth thing: the agent's model answers after 50 seconds and the simulated customer hangs up

Simulation "scen 15:07:21 6ed331" (11 October 2026, calls between 12:27 and 13:00 UTC, right after the outage), agent version 9, 100 calls.
We measured, for every customer message, the time until the agent's next tool call or sentence:

| Simulation | Agent reactions | Median | 90th percentile | 99th percentile | Slowest | Calls ended by the customer |
|---|---|---|---|---|---|---|
| "scen 03:49:48" (00:49 UTC, same agent version, same 100 customers) | 578 | 0.8 s | 2.2 s | 4.0 s | 5.7 s | 0 |
| "scen 15:07:21 6ed331" | 598 | 1.8 s | 11.2 s | 33.2 s | 55.8 s | 3 |

In three calls the agent's tool call came 53 to 56 seconds after the customer's message; the tool answered at once, and while the agent's next
sentence was awaited the call ended with `customer-ended-call`. Two of the three were judged failed, with the reason that the agent "never responded":

- `f97c6f8a-bbf6-477a-ad8c-8f4da8914f5d`: date of birth given at 29.8 s, `verify_identity` called at 85.6 s (correct, accepted), call over at 90 s.
- `12f619de-e37b-464e-bb90-cd5110114bb2`: payment day named at 73.0 s, the date check ran at 126.0 s, call over at 133 s.

Nothing in a workflow can shorten the model's answer time, so calls like these fail whatever the agent is.
