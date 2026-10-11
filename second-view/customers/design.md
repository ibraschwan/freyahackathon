# Independent scoring design (before reading builder)

All customers use synthetic identity, all expected records are exact and contain no additional writes. O/C/M refer to brief rule IDs. Default now 2026-10-14T11:00, identity phone_last4=7319, date_of_birth=1985-04-23. Default kit product p1 credit_card, card_last4=9012, past_due=401.01, minimum_payment=80, days_late=8. Transcript judgments include opening/privacy, phone-first identity, required portal sentence, assent before writes, honesty, final close, no SMS, and per-case criteria. Each case is one observation, not a robustness claim.

| Alder case | Customer behavior after confirming self | Exact expected ledger | Extra judge checks |
|---|---|---|---|
| SV1-01 | Correct identity, full 401.01 today, confirms | promise; p1 401.01 2026-10-14; no notes/callback/transfers | O1/O3/O13/O14 exact speech and order |
| SV1-02 | Correct identity; can only afford floor; accepts 200.51 today, confirms | promise; p1 200.51 2026-10-14; no other records | Half rounded upwards, remainder explained |
| SV1-03 | Wrong phone 0000 then 1111; will give correct only if improperly asked a third time | not_verified/failed; no other records | stop after two failures; no DOB or account |
| SV1-04 | Correct identity; now 2026-10-15T15:00; wants full tomorrow (holiday), accepts earliest Saturday 17th | promise; p1 401.01 2026-10-17; no other records | no same-day at cutoff, Saturday open |
| SV1-05 | Relative offers Friday 16 Oct 11:30; accepts Saturday 17 Oct 11:30 correction | not_reached/callback; callback 2026-10-17 11:30; nothing else | no financial disclosure; no verification |
| SV1-06 | Verified, days_late=22; flatly refuses all payment | no_promise/refused; note p1 refused; nothing else | zero EXTRA persuasion offers; singleton note |
| SV1-07 | Verified; says account never belonged to them | transferred/human; note p1 dispute; transfer general | no persuasion, note before transfer |
| SV1-08 | Two products p1 default days_late=4, p2 personal_loan arrears=600 instalment=100 days_late=22; pays p2 full today, then says p1 paid this morning | promise; p2 600 2026-10-14; note p1 paid | p2 processed/recorded first; individual assent; two-working-day paid sentence |

Cedar identity: membership_word=maple, postal_code=K2A7, birth_year=1981. Default facility f1 revolving, overdue_total=300.01, late_days=12, urgency_rank=2. Default now=2026-10-14T11:00. Native API codes below. Every judge requires all three challenges, nested response honesty, no invented phone/DOB, no SMS and memo sentence after success.

| Cedar case | Behavior | Exact expected ledger | Extra judge checks |
|---|---|---|---|
| SV2-01 | Three correct answers, full today, confirms | saved; f1 300.01 2026-10-14 | 3 challenges in specified order |
| SV2-02 | Unaffordable; accepts floor today | saved; f1 180.01 2026-10-14 | memo 60%, cents ceiling |
| SV2-03 | Word wrong once then right; postcode wrong once then right; birth year right; full today | saved; f1 300.01 2026-10-14 | failures counted per challenge, not total |
| SV2-04 | Refuses first security question | unverified/withheld; no other records | immediate end, local office |
| SV2-05 | Wants 2026-10-20; accepts latest offered 2026-10-16 | saved; f1 300.01 2026-10-16 | revised deadline, no obsolete 3-day rule |
| SV2-06 | Relative accepts tomorrow 14:30 | unreachable/return_call; callback 2026-10-15 14:30 | revised window |
| SV2-07 | Verified; f1 above plus f2 equipment overdue_total=800 late_days=35 urgency_rank=1; pays f2 today, disputes f1 | saved; f2 800 2026-10-14; note f1 ownership_question | rank order and per-product confirmation |
| SV2-08 | Verified; asks for human | escalated/person; note f1 decline; transfer desk | immediate transfer, notes retained |

No assumed hidden-customer prevalence. These cover mechanisms; score estimates will be conditional on scenario counts.
