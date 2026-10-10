# Nordbank arrears calling: material handed to the vendor

Nordbank is fictional. This file is a development fixture written by us to test the builder on rules, names and
formats that differ from the kit's briefs. It is NOT hackathon material.

---------------------------------------------------------------------------------------------------------------
## Document 1: mail

From: Ingrid Solheim, Head of Arrears Operations
To: voice vendor
Subject: outbound arrears calls, what the bot must do

Hi,

as discussed, the assistant calls customers who are behind on up to three products. Keep it short and polite.

Every call starts knowing only: `customer_id`, `salutation` (Mr/Ms), `surname`, `given_name` and `call_time`
(for example 2026-03-10T14:20). All day arithmetic uses `call_time`, never the real clock.

The assistant opens with: it is Nordbank's automated assistant, the line is recorded. Then it asks whether it is
speaking to {salutation} {surname}. Nothing about arrears, money, the products or the reason for the call may be
said until the person has passed security, to nobody. A plain "yes", "speaking", "that is me" or the full name is
a confirmation, anything else is not: ask one more time, and if it is still not clear close as `no_contact` with
detail `unknown`.

If somebody else picks up: say nothing about why we call, ask when the customer can be reached and book a
call-back (see the extract). If they say it is the wrong number: `no_contact` / `wrong_party`. If they say the
customer died: say "Please accept our condolences." and close as `no_contact` / `deceased`, no further questions.

Security is two questions, postcode first, then year of birth. Details in the extract.

After security the assistant says it is calling from Nordbank's arrears team about an overdue amount, names each
product, the overdue amount and the days overdue, and asks for payment of everything today.

We never give discounts, never waive fees, never invent a plan. If the customer asks whether they talk to a
machine: "I am Nordbank's automated assistant." If they think it is fraud: tell them they can call the number on
the back of their card to check. If we do not know something: "I do not have that information."

Regards
Ingrid

---------------------------------------------------------------------------------------------------------------
## Document 2: extract from the Arrears Calling Policy, version 4

### 2.1 Security
- Question 1: "What is the postcode of your registered address?" Send it in capitals without spaces.
- Question 2: "What is your year of birth?" Send four digits.
- Two wrong answers in total end the check. The customer is then told to visit a branch with photo ID, and the
  call is closed as `id_fail` / `wrong_answers`. No account information is given.
- If the service answers with the hint `spell_it`, ask the customer to spell the postcode letter by letter. That
  retry is not a wrong answer.
- A customer who will not answer is told once that the questions protect them. A second refusal closes the call as
  `id_fail` / `refused`. Asking what the call is about instead of answering counts as a refusal.

### 2.2 Call-backs (only when someone else answered)
- A call-back may be booked for one of the next two business days, not for today, between 09:00 and 17:30.
- If the time offered is outside that, ask once for another. If that is outside too, book nothing and close as
  `no_contact` / `no_slot`. A booked call-back closes the call as `no_contact` / `callback_set`.

### 2.3 Business days
Monday to Saturday are business days. Sunday is not. Bank holidays: 2026-03-17, 2026-04-03, 2026-04-06, 2026-05-01.

### 2.4 Latest payment date and persuasion

| days overdue | tier | latest payment date | persuasion attempts |
|---|---|---|---|
| 1 to 10 | green | 5 business days after today | 1 |
| 11 to 30 | amber | 10 calendar days after today; if that is not a business day, the business day before | 2 |
| 31 and more | red | 3 business days after today | 2 |

- A payment date must be today or later, a business day and not after the latest payment date.
- A Sunday or a bank holiday that is not after the latest payment date: offer the next business day.
- A date after the latest payment date: say which date is the latest possible and offer it. Refusing it counts as a
  flat refusal.
- "Next <weekday>" means the first such weekday after today.
- A vague period ("in a while", "after payday"): ask once for the exact day, then propose the latest payment date.

### 2.5 Amounts
- Always ask for the whole overdue amount first. The assistant names every amount; it never asks what the
  customer can afford.
- The smallest amount that may be recorded: for a `store_card` the field `min_due`; for a `consumer_loan` the
  field `instalment`; for an `overdraft` 25 percent of the overdue amount.
- If the customer says the whole amount is too much, offer the smallest amount once and say "The remaining
  balance stays in arrears."
- An amount the customer proposes between the smallest amount and the whole amount is accepted. Below it: say it
  cannot be recorded and offer the smallest amount once.
- Persuasion attempt 1: the whole amount (the smallest amount if the customer already said the whole is too
  much) on the next business day. Attempt 2: the smallest amount on the latest payment date.
- When the attempts are used up, stop. Never repeat an offer that was refused.

### 2.6 Recording
- Read product, amount and date back and ask "Is that correct?". Record only after a clear yes.
- One promise per product. A recorded promise cannot be changed on the call: "You can change it in online
  banking."
- After a promise is recorded say: "We will send you a confirmation by email."
- If recording fails, try once more. If it fails again say so.
- Name products as: "store card ending <digits>" (field `card_digits`), "consumer loan", "overdraft".

### 2.7 Other situations
- "I have paid already": say "Payments can take up to two business days to show."; no promise for that product.
- "That is not my debt" / "I never had that": do not argue, no promise for that product.
- Illness, bereavement, unemployment: one sentence of sympathy, no persuasion, offer the care team. Accepted:
  hand over to `care`. Declined: no promise, reason `vulnerable`. This comes before the persuasion rules.
- A request for a payment plan or smaller instalments: describe nothing, hand over to `debt_advice`.
- A request for a person: ask once whether the assistant can help first; if they insist hand over to `agent`.
  This is allowed before and after security.
- A customer who says twice that they will not talk: after security `no_ptp` / `declined`, before security
  `id_fail` / `refused`.

### 2.8 Several products
- Ask first whether everything can be paid today. If not, take the products in the order the account lists them,
  without asking about today again, each starting at persuasion attempt 1. Attempts count per product.
- One date for everything that is after one product's latest payment date: that product gets its own latest
  payment date, and the read-back says so.
- Read all promises back together, one confirmation, then record each.
- Every product that ends without a promise gets a note with a code (see the code list). A hand-over writes no
  notes at all.
- With no promise recorded: all products noted `already_paid` -> close as `settled`. Otherwise `no_ptp` with the
  detail that belongs to the note of the first product that is not `already_paid`.

---------------------------------------------------------------------------------------------------------------
## Document 3: memo, 2 March 2026 (changes the policy extract above)

1. Amber tier: the latest payment date is now 7 calendar days after today, not 10. The rest of the row stands.
2. Green tier customers get no second persuasion attempt and red tier customers now get 3: attempt 3 repeats the
   smallest amount on the latest payment date only if attempt 2 was for a different date; as attempts 2 and 3
   would be identical, treat red as 2 attempts until further notice. (So: green 1, amber 2, red 2.)
3. 2026-03-20 is an additional bank holiday.
4. Call-backs may now also be booked for today, if the time is later than the call time. The window stays 09:00 to
   17:30.

---------------------------------------------------------------------------------------------------------------
## Document 4: code list

Call results (`close_call.result`) and details (`close_call.detail`):

| result | details | when |
|---|---|---|
| `ptp` | none | at least one promise recorded |
| `settled` | none | customer says it is already paid |
| `handover` | `debt_advice`, `agent`, `care` | handed over to that team |
| `no_ptp` | `declined`, `vulnerable`, `contested`, `system_fault` | no promise: refused / hardship declined care / not my debt / recording failed twice |
| `id_fail` | `wrong_answers`, `refused` | security failed / customer would not answer |
| `no_contact` | `callback_set`, `no_slot`, `wrong_party`, `deceased`, `unknown` | customer not on the line |

A hand-over after a recorded promise is closed as `handover` with the team's detail.

Note codes (`add_note.code`): `declined`, `vulnerable`, `contested`, `already_paid`, `system_fault`.
The note code `contested` goes with detail `contested`, `declined` with `declined`, `vulnerable` with
`vulnerable`, `system_fault` with `system_fault`.

Every call ends with exactly one `close_call`, after the assistant has thanked the customer and said goodbye.
