"""Turns a bank's brief and tool API file into the policy spec the engine compiles.

Three kinds of model call:
  1. policy    the numbers, names, tables and fixed sentences, as JSON. Made twice, independently.
  2. settle    only when the two policies differ: a third call sees both and the brief and decides each difference.
  3. prompts   the step instructions for the dialogue model, then one review of them against the brief.

Everything the model returns is checked against the tool API file before it is used.
"""
import asyncio, json, re
from . import llm
from .engine import read_api, SEVEN, OPTIONAL as OPTIONAL_ROLES, service, roles as role_services

SYSTEM = ("You configure a phone-agent engine for a bank's collections calls. You are exact and literal. Every value comes from the brief and the tool API file you are given, "
          "never from other banks, other briefs or habit. If the material is several documents (a mail, a policy extract, a memo, a code list), read all of them: a later document "
          "that changes an earlier one wins, and you resolve them into one consistent policy.")

ENGINE = """HOW THE ENGINE WORKS. It is fixed. Only the configuration changes from bank to bank.

The phone agent has two conversational steps. A dialogue model listens, talks and reports what the customer says. Code checks, counts, speaks the fixed sentences and executes.

OPENING step
- The engine speaks `sentences.opening` as the very first line.
- The dialogue model finds out who is on the line, handles other people answering, books callbacks and asks the security questions. Its bank tools here: verify_identity, schedule_callback, transfer_to_agent. To end the call it calls wrap_up(outcome, reason).
- no_answer(about): how the two limits of the opening are counted, by code. The model calls it every time the person does not give the answer that was asked for: about "who_is_speaking" (neither confirmed nor denied being the customer) or about "security_question" (refuses a security question, or asks something instead of answering). Up to `opening_limits[about].times` times the engine answers with the instruction `opening_limits[about].say`; the next time it closes the call with `opening_limits[about].close`.
- verify_identity: after each result the engine tells the model what to do: repeat the same question after a wrong answer (it makes the model say `identity.wrong_sentence` first), ask the next question (the order of `identity.questions`, using each question's `ask` sentence), or follow `identity.hints[<hint value>]` when the bank returns a hint. When the bank reports that no wrong answers are left, the engine speaks `sentences.identity_failed` and closes the call with `outcomes.identity_failed`.
- schedule_callback: the engine refuses a day or time outside the `callback` window, without calling the bank, and tells the model `guidance.callback_outside_first` the first time and `guidance.callback_outside_second` the second time. After a booked callback it speaks `sentences.after_callback` and closes the call with `outcomes.callback_booked`.

After the last security answer is verified the engine calls get_account and computes, for every late product (in the order of get_account, or sorted by `product.order`): its name in words, the full amount, the floor, the days late, its band, its deadline and its persuasion offers. Then it speaks: `sentences.verified_ack` + `sentences.debt_intro` + one `sentences.product_statement` per product + `sentences.first_ask_single` (one product) or `sentences.first_ask_multi` (several).

NEGOTIATION step
- The dialogue model never writes to the bank and never words an offer or a read-back. It reports with these tools, and after each report the ENGINE says the next sentence to the customer:
  - check_terms(product_id, amount, date): the customer agreed to pay. The engine refuses, with an instruction to the model: an amount below the product's floor (`guidance.below_floor`), a day that is not a business day (`guidance.not_business_day`, it names the business day to offer instead), today when `dates.today_until` has passed (it names the earliest day), a day after the product's deadline (`guidance.after_deadline`), a day in the past, a product whose promise is already recorded (it makes the model say `sentences.change_later`). With several products and one day for all, a product whose deadline is earlier is put on its own deadline and the read-back says so.
  - customer_refused(product_id, kind): the customer does not agree. kind flat_refusal (a no with no day and no amount, a non-answer, a no to the offer on the table) or kind full_amount_too_much. This is how the persuasion attempts are counted, by code. For full_amount_too_much the engine says `guidance.too_much`, once per product. For flat_refusal it says the next entry of `attempt_offers` as "Could you pay <amount> for your <product> by <date>?" (plus `sentences.rest_overdue` when the amount is the floor), as many times as the product's band allows. When the attempts are used up the engine ends the product: with notes enabled it notes it with `notes.refused_reason`, otherwise it closes the call with `outcomes.refused`.
  - skip_product(product_id, reason), only when notes are enabled: the product ends without a promise for that reason. If `note_lines[<reason>]` exists the engine says that sentence.
- What the engine says after a report: the next persuasion offer; or, when a product is settled and another is open, `sentences.next_product` followed by that product's persuasion attempt 1; or, when every product is settled and something was agreed, the read-back "To confirm: you will pay <amount> for your <product> on <date>. " + `sentences.confirm_question`; or, when every product is settled and nothing was agreed, the closing (see below).
- customer_confirmed(): the customer said a clear yes to the read-back. The engine calls create_promise once per agreed product. A failed call is repeated once. Then it speaks `sentences.promise_recorded`. If a call failed twice it speaks `sentences.promise_failed`; when notes are enabled that product is noted with `notes.service_error_reason`, otherwise the call is closed with `outcomes.promise_service_error`.
- The engine writes the notes with add_note at the very end of the call, and never when the call was transferred.
- transfer_to_agent: after a successful transfer the engine speaks `sentences.after_transfer` and closes the call with `outcomes.transfer[<queue>]`. Promises agreed but not yet recorded are dropped. Recorded promises stay.
- A bank tool whose "tools" entry is null does not exist for this bank: the engine builds no such tool, and the instructions must not mention it or the situation it serves (no callback without schedule_callback, no transfer without transfer_to_agent, no notes without add_note). A service listed in "extra_tools" is a tool of the dialogue model in the step named there, under the tool API's own name.
- wrap_up(outcome, reason), or the automatic closing: the engine decides the final outcome and reason from the records, in this order: a transfer -> `outcomes.transfer[queue]`; a booked callback -> `outcomes.callback_booked`; before verification -> the model's pair if it is in `outcomes.before_verification`; at least one recorded promise -> `outcomes.promise_recorded`; notes enabled -> derived from the notes by `notes.close_from_notes`; otherwise the model's pair if it is in `outcomes.after_verification`. Then it speaks `closing_lines["<outcome>/<reason>"]` (or `closing_lines["<outcome>"]`) if there is one, then `sentences.goodbye`, and calls close_call exactly once, as the last tool call.
"""

SCHEMA = """THE CONFIGURATION. Return one JSON object with exactly these keys.

"bank_name": string.
"language": the language the agent speaks, as an English word.
"address": how to address the customer, built from call variables in double braces, for example "{{title}} {{last_name}}".
"call_variables": the names of the variables every call starts with, as the brief lists them. Tool body fields with these names are filled by the engine.
"now_variable": the call variable that holds the current date and time.
"test_variables": an object with one example value per call variable (from the brief's examples).
"calendar": {"weekend_days": numbers of the days that are NOT business days, Monday = 0 ... Sunday = 6, "holidays": ["YYYY-MM-DD", ...],
  "non_business_day": optional. "previous" only when the brief moves a weekend day or holiday the customer names to the business day BEFORE it. Leave the key out when the brief moves it to the next business day or says nothing}.
"callback": {"include_today": true/false, "business_days_ahead": how many business days after today a callback may be booked (1 = the next business day only), "from": "HH:MM", "to": "HH:MM" (both ends count as inside), "after_now": true when a callback today must be later than now}.
"identity": {
  "questions": the security questions in the order to ask them: [{"field": the value of the verify_identity question field for it, taken from the tool API enum, "kind": "date" | "digits" | "text", "ask": the exact question sentence to say, "transform": optional list for a text answer the brief wants normalised before it is sent, from "uppercase", "lowercase", "remove_spaces"}],
  "numeric_date_order": "DMY" or "MDY": how to read a date given only as numbers,
  "response": the names of the verify_identity response fields with these roles: {"verified": this answer was right, "all_verified": the whole check is passed, "left": how many wrong answers are left, "hint": the hint field},
  "hints": {<hint value from the tool API>: the instruction for the dialogue model when this hint comes back, including the exact sentence to say, and whether it counts as a wrong answer},
  "wrong_sentence": what to say after a wrong answer before the question is repeated. It must not reveal which part was wrong.
  "max_wrong": optional, only when the brief ends the security check after a number of wrong answers that it states itself: {"total": number} for wrong answers in the whole check, or {"per_question": number} for wrong answers to one and the same question. The engine then counts them itself, whatever the service counts. Leave the key out when the brief only follows the service's count.
}
"opening_limits": the two things the brief limits before the customer is verified. Both keys are required.
  {"who_is_speaking": {"times": how many more times the agent may ask whether it is speaking with the customer after the first ask in the opening line got no confirmation (the brief's "ask once more" = 1),
                       "say": the instruction for the dialogue model for such a further ask, with the exact question in quotes, for example: Ask exactly once more: "<the question>",
                       "close": [outcome, reason] the call is closed with when that is used up},
   "security_question": {"times": how many times the agent may explain and ask again when the customer does not answer a security question (the brief's "explain once" = 1),
                         "say": the instruction for that case: the exact sentence of explanation to say, in quotes, and then to ask the same security question again,
                         "close": [outcome, reason] for the refusal after that}}
"product": {
  "list_field": the get_account response field that holds the products, "id_field", "type_field", "full_field": the field with the full past-due amount, "days_late_field",
  "order": optional, only when the brief goes through the products in another order than get_account returns them: {"field": the product field to sort by, "direction": "ascending" | "descending"} (products with the same value keep the order of get_account),
  "types": {<product type value>: {"words": how the brief says to name this product aloud; a field of the product goes in angle brackets, for example "credit card ending <card_last4>",
                                   "floor": the lowest amount that can be recorded for it: {"field": <product field>} or {"percent_of_full": number} or {"amount": number}; when the brief combines several of these: {"greatest_of": [two or more of them]} or {"least_of": [two or more of them]}; a percent may carry "round": "up" or "down" when the brief says how it is rounded to the cent,
                                   "floor_name": what that amount is called aloud}}. Use the key "*" for a rule that covers every other type.
  "confirm": optional, leave it out unless the brief demands it. "each" when the brief wants every product read back, confirmed and recorded on its own before the next product is discussed: the engine then reads back one agreed product alone, records it after the customer's yes, and only then goes on to the next product. Without the key every agreed product is read back together for one confirmation.
}
"bands": the table that turns days late into a deadline and a number of persuasion attempts, in the brief's order:
  [{"name", "min": lowest days late in the band, "max": highest (null for no upper limit), "deadline": {"unit": "business_days" | "calendar_days", "n": number of days after today, "roll": "next" | "previous" (calendar_days only: where to move a deadline that is not a business day)}, "attempts": number of persuasion attempts}].
"attempt_offers": what each persuasion attempt proposes, in order (attempt 1 first). A band uses the first `attempts` entries.
  [{"amount": "full" | "floor" | "full_or_floor" (the full amount, but the floor if the customer already said the full amount is too much),
    "date": "last_business_day_of_week" (of this week; if today is that day or it has passed, of next week) | "deadline" | "next_business_day" | "today",
    "text": optional extra words the model must say or respect with this attempt}]
"dates": {"next_weekday": "following_week" when "next Friday" means the Friday of the following calendar week, "next_occurrence" when it means the first Friday after today,
  "today_until": optional "HH:MM", only when the brief allows a payment for today only before a time of day: from that time on the earliest day that can be recorded is the next business day}.
"guidance": instructions to the dialogue model, each one or two sentences, taken from the brief's rule for that case. They may use the tokens shown.
  {"below_floor": the customer proposed less than the floor (tokens <floor>, <floor_name>),
   "after_deadline": the customer named a day after the deadline (token <deadline>),
   "not_business_day": the customer named a weekend day or a holiday inside the deadline (token <next> = the business day the engine offers instead: the next one, or the one before it when calendar.non_business_day is "previous"),
   "too_much": the exact sentence that offers the floor when the customer says the full amount is too much, with everything the brief wants said with that offer (tokens <floor>, <floor_name>),
   "callback_outside_first": the first day or time offered for a callback is outside the window,
   "callback_outside_second": the second one is outside too. Name the wrap_up(outcome, reason) to call.}
"tools": for each bank tool, the names of its body fields with these roles (take the names from the tool API file):
  {"verify_identity": {"question", "answer"}, "create_promise": {"product", "amount", "date"}, "add_note": {"product", "reason"}, "schedule_callback": {"date", "time"}, "transfer_to_agent": {"queue"}, "close_call": {"outcome", "reason"}}
  When the tool API names the service that plays a role differently, add "service": its name in the tool API (the last segment of its path, or the whole path without the leading slash when several paths end the same way), for example "create_promise": {"service": "promise/create", "product": ..., "amount": ..., "date": ...}. The engine then calls that service; the dialogue model still sees the role name.
  When the tool API has no service at all for add_note, schedule_callback or transfer_to_agent, set that key to null: the engine then builds the agent without that tool. The other four roles are always needed.
"extra_tools": optional, only for services of the tool API that none of the seven roles covers and that the brief tells the agent to use: {<service name as in "service" above>: {"step": "opening" | "negotiation" | "both", "when": one or two sentences for the dialogue model: when to call it, with what, and what to say or do with the result}}. The model calls such a service itself, with the fields of the tool API, and sees the result as it comes. Leave the key out when there is no such service.
"response": {"ok": the response field that is true when the bank carried the action out}.
"transfer": {"before_verification": the queues that may be used before the customer is verified (a list; empty if the brief does not limit it)}.
"outcomes": {
  "table": {<outcome>: [its allowed reasons, empty when the outcome has no reason]} for every outcome of the brief, with the exact values of the tool API,
  "meaning": {<outcome>: when it applies, a few words},
  "promise_recorded": [outcome, reason or null] for a call in which at least one promise was recorded,
  "identity_failed": [outcome, reason] when the security check failed on wrong answers,
  "callback_booked": [outcome, reason],
  "promise_service_error": [outcome, reason] when the promise could not be recorded after the retry,
  "refused": [outcome, reason] for a verified customer who still refuses when the persuasion attempts are used up,
  "account_error": [outcome, reason] when the account could not be read (use the service-error pair if the brief has no own rule),
  "transfer": {<queue>: [outcome, reason]} for every queue of the tool API,
  "before_verification": every [outcome, reason] pair a call can end with while the customer is NOT verified and nothing was booked or transferred,
  "after_verification": every [outcome, reason or null] pair a call can end with when the customer IS verified, no promise was recorded and no transfer happened (leave out the service-error pair),
  "fallback_before_verification": [outcome, reason] for a call that breaks off before verification with nothing else known,
  "fallback_after_verification": [outcome, reason] for a call that breaks off after verification with no promise
}
"notes": {"enabled": true only when the brief tells the agent to record a note (add_note) for products that end without a promise; false when the brief does not use add_note,
  "reasons": the allowed note reasons, "service_error_reason": the reason for a promise that could not be recorded, "refused_reason": the reason for a product the customer refuses to pay,
  "reason_for_outcome": {<outcome>: the note reason that goes with it} for outcomes whose name is not itself a note reason,
  "close_from_notes": how a call with no recorded promise is closed from its notes:
     {"all": {<note reason>: [outcome, reason or null]} for the case that every product has that same note reason and the brief gives it its own outcome,
      "else_outcome": the outcome otherwise, "else_reason_from_first_note_not_in": [note reasons to skip]: the reason is the note reason of the first product, in account order, whose note is not in this list}}
"sentences": fixed sentences the engine speaks. Use the brief's exact wording where it gives one. Call variables may be used in double braces.
  {"opening": the first line of the call: everything the brief wants in the first sentence, then the question that asks for the customer by name,
   "identity_failed": what to say when the security check has failed (what the brief tells the customer to do instead), ending with the goodbye,
   "after_callback": said after a callback is booked, ending with the goodbye, "after_transfer": said after a transfer is arranged, ending with the goodbye,
   "verified_ack": one short sentence after the security check is passed,
   "debt_intro": the sentence that says who is calling and why, as the brief wants the debt introduced,
   "product_statement": one sentence that states one late product with everything the brief wants stated; tokens <product>, <amount>, <days_late>, <days> (the word "day" or "days"),
   "first_ask_single": the first question after the debt is stated, for one product, "first_ask_multi": the same for several products,
   "confirm_question": the question that ends the read-back, "promise_recorded": what to say once the promise is recorded, including any sentence the brief requires after a recorded promise,
   "promise_failed": what to say when it could not be recorded, "change_later": what to say when the customer wants to change or cancel a recorded promise,
   "account_error": what to say when the account cannot be read, "rest_overdue": the sentence the brief wants added whenever less than the full amount is offered (empty if none), "next_product": a short lead-in when the engine moves on to the next product, with the token <product>, for example "Now your <product>.", "ask_product": a short question that asks when the customer can pay the product just named, "anything_else": a short neutral question for after a recorded promise when nothing else is open, "goodbye": the thanks and goodbye that end every call}
"phrases": ONLY when the agent speaks a language other than English; leave the key out for English. The engine's own sentence patterns, written in the agent's language, natural and polite as the brief's own examples sound. Keep every token in angle brackets exactly as it is; put it where it belongs in that language's word order.
  {"weekdays": the seven day names, Monday first, "months": the twelve month names, January first,
   "date": how a date is said, with the tokens <weekday> <day> <month> <year>, for example "<day> <month> <year> <weekday>",
   "amount": how an amount of money is said, with the token <n> for the number and the currency as the brief names it, "decimal_comma": true when the language writes 1250,50, "day" and "days": the word for one day and for several days,
   "full_amount": "the full amount of <amount>" in that language, "floor_amount": "the <floor_name> of <amount>" in that language,
   "offer": the question "Could you pay <what> for your <product> by <date>?" in that language, "offer_no_date": "Could you pay <what> for your <product>?",
   "readback_item": "<amount> for your <product> on <date>", "readback": "To confirm: you will pay <items>." (the confirm question follows it), "and": what joins two items, with its spaces, for example " and ",
   "capped": " (the latest possible date for this product)" with a leading space, "concerns": "This concerns your <products>.", "and_your": what joins two products there, with its spaces,
   "thanks": "Thank you.", "say_again": "I am sorry, could you say that again?"}
"note_lines": {<note reason>: the sentence the brief requires the agent to say when a product is settled without a promise for that reason} (only when notes are enabled; only reasons for which the brief prescribes a sentence; the engine says it, once per call).
"closing_lines": {"<outcome>/<reason>" or "<outcome>": a sentence the brief requires at the very end of a call with that outcome, spoken by the engine before the goodbye}. Only where the brief prescribes a sentence that is the last thing said. Usually one or two entries, often none.

Rules for the JSON: exact values of the tool API file for every outcome, reason, queue, field name and product type. Use null where a pair has no reason. No comments. No keys other than these."""

PROMPT_TASK = """Now write the step instructions for the dialogue model. The dialogue model is a small, fast model: it follows explicit, ordered, literal instructions well and vague ones badly.

Return three sections in these tags and nothing else:

<global_rules>
One rule per line. Rules of the brief that hold in every step: what must never be offered or promised, the answer to "are you a robot / an AI", the answer to "is this a scam", what to say when asked something the bank's data does not answer. Give the exact sentence to say in quotes.
</global_rules>

<opening>
The instructions for the OPENING step. Use this structure:
- First, what must not be said or revealed before the customer is verified, to anyone, with the forbidden words of the brief listed, and what to answer when asked what the call is about (one answer for the customer, one for anyone else).
- A line: You already said: "<the opening sentence>"
- PART 1 - WHO IS ON THE LINE. Lettered cases, each ending in a concrete action: what counts as confirmation and what does not; neither confirmed nor denied: write "If the person asked a question, answer it first with its fixed sentence. Then CALL no_answer(who_is_speaking). The tool counts the asks: its answer tells you what to say, or it ends the call." and nothing about how often; wrong number; the customer has died; someone else answered (what may be said, what must not, the callback).
  For the callback write: the placeholder {{callback_facts}} on its own line (the engine puts the allowed slots there), then: "As soon as the person names a day, CALL schedule_callback with it, whatever the day is, and with the clock time if one was said (otherwise time \"unknown\"). The tool checks the day and the time itself: if it refuses with a RULE error, do exactly what the error says. Do not ask for a clock time yourself before calling it." Then the brief's rule for a first and a second offer outside the window.
- PART 2 - SECURITY QUESTIONS. The questions in order with their exact sentences; "Each time the customer gives an answer, CALL verify_identity" with the field value for each question; how each answer is formatted before it is sent (the brief's rules, with one example each); "The tool result tells you what to do next. Do exactly that."; never reveal which part was wrong; what to do when the customer refuses to answer or asks something instead of answering (every case the brief counts as declining): write "CALL no_answer(security_question). The tool counts: its answer tells you what to say, or it ends the call." and do NOT write the explanation sentence, a first time or a second time into the instructions; a customer who does not want to talk (if the brief counts it together with declining, it is the same CALL). State that small talk or an unfinished sentence instead of an answer is not a refusal and is not counted: the model just asks the question again.
- AT ANY POINT IN THIS STEP: requests the brief allows before verification (for example a human).
</opening>

<negotiation>
The instructions for the NEGOTIATION step. In this step the model only listens, answers questions and reports with tools; the system words every offer and every read-back. Use this structure:
- WHAT YOU WANT: the goal, and what the model must never ask or offer. State that the system makes every offer and the model never states an amount, a date or an offer of its own.
- ONE PRODUCT: which question the system just asked. SEVERAL PRODUCTS (only if the brief covers customers with several products): the question the system just asked; yes to all -> CALL check_terms(product_id "all", amount "full", date of today); one day named for everything -> CALL check_terms("all", "full", that day); a plain no to paying all of them -> CALL customer_refused(<first open product>, flat_refusal); the customer may settle several products in one message: CALL the fitting tool for each of them in the same message; the system leads from product to product in the order of the FACTS and reads all agreed promises back together for one confirmation.
- Then: "For the product you are talking about, read the customer's last message and apply the FIRST rule that fits." followed by numbered rules R1, R2, ... in priority order, one per situation of the brief: already paid, dispute, hardship, new plan / restructuring, human, the customer names a day (exact day, vague period), the customer names an amount, the full amount is too much, flat refusal or non-answer, yes, does not want to talk. Add a rule for every other situation the brief names. If the brief gives one rule priority over others, say so in that rule.
  Each rule says which tool to CALL, and what the model itself says only where the brief prescribes a sentence the engine does not speak.
- AFTER THE READ-BACK: a clear yes -> CALL customer_confirmed; a changed day or amount -> CALL check_terms again; what to do after the promise is recorded (when the customer has nothing more: CALL wrap_up with the promise outcome); requests that still transfer the call after a promise.
</negotiation>

How to write the rules:
- Counting. The dialogue model counts badly. The two limits of the opening are counted by the no_answer tool, the persuasion attempts by customer_refused: never restate those counts. For any other limit of the brief (something to be said or offered once), write what happens the first time and what happens the second time as two separate lines, and in the second line say what must NOT be repeated.
- Every line that ends a call or transfers it says exactly what the model says in that same message: either one given short sentence in quotes, or "say nothing else". Never leave it open, or the model repeats its last sentence.
- A sentence the brief requires in a situation (for example a sentence of sympathy) must be said in EVERY branch of that situation, also when the customer names a day or an amount in the same message. Write it as the first step of the rule, before the branches.
- Priority. When the brief says one rule comes before another, write it in BOTH rules: in the winning rule ("this rule comes before R4 and R10") and in the losing rules ("not if the customer mentioned <the winning situation> in this call: then R3"). A customer message that fits two situations is decided by this.
- The engine shows the model these FACTS in the NEGOTIATION step; refer to them by these names and never restate their numbers: for each product FULL (the full past-due amount), FLOOR (with its name), DEADLINE, the PERSUASION ATTEMPTS; a DATE TABLE that says for every day up to the deadline whether it is allowed; WHAT THE CUSTOMER'S WORDS MEAN (today, tomorrow, this/next weekday); and CALL STATE (what is agreed, recorded, settled, open).
- A day or an amount the customer names: CALL check_terms with it. The tool checks it; if it refuses, its message says what to tell the customer. Do not make the model judge dates or amounts itself. If the customer names an amount but no day, the model asks for the day first. A vague period is the exception: give the brief's rule for it (how often to ask for the exact day, and what happens then; when the brief says to propose the deadline, the model says the DEADLINE and, if the customer accepts, CALLs check_terms with it; if they refuse, CALL customer_refused).
- Persuasion is counted and worded by the engine. For every case the brief counts as a flat refusal or a non-answer (name them: a no with no day and no amount, a no to an offer, a refusal of the floor, a refusal of the deadline, ...) write: CALL customer_refused(<product>, flat_refusal). For "the full amount is too much" with no amount named write: CALL customer_refused(<product>, full_amount_too_much). Do not restate what the attempts are, do not tell the model to count, and do not tell it to say an offer. When the attempts are used up the engine ends the product itself; with notes enabled do NOT add skip_product(<product>, <refused reason>) for it.
- With notes enabled, a product that ends without a promise for a reason other than a plain refusal (already paid, dispute, hardship declined, ...) is settled with CALL skip_product(<product>, <reason>) and the call goes on with the other products by itself; skip_product("all", <reason>) settles every open product at once. Never add wrap_up after it: when the last product is settled with nothing agreed, the engine ends the call. Without notes, such a call ends with CALL wrap_up(<outcome>, <reason>) using the exact values of the policy.
- The engine speaks these itself, so never tell the model to say them: the opening sentence, the debt statement and first question, every persuasion offer and the floor offer, the lead-in to the next product, the read-back, the sentence after a recorded promise, the sentence after a failed recording, the sentences after a transfer or a booked callback, the sentence after a failed security check, the `note_lines` sentences, the closing lines, the goodbye. Never tell the model to say goodbye or thank-you-goodbye.
- Sentences that belong to a situation in the middle of a call and are not in that list (a sentence of sympathy, "I understand.", the question that offers the support team, the answer to a request for a human) the model says itself: put them in the rule, in quotes. In a message in which the model CALLs check_terms, customer_refused or skip_product it says nothing or one short acknowledgement.
- Tools are written as: CALL verify_identity, CALL schedule_callback, CALL transfer_to_agent(queue <name>), CALL check_terms(...), CALL customer_refused(<product>, <kind>), CALL skip_product(<product>, <reason>), CALL customer_confirmed, CALL wrap_up(<outcome>, <reason>). A tool whose "tools" entry in the configuration is null does not exist: never mention it, and write the rule for its situation without it (for example no callback is offered when there is no schedule_callback; leave out the {{callback_facts}} line too). A service of "extra_tools" is written as CALL <its name>(<its fields>), only in the step its entry names, with the words of its "when".
- Call variables may be used in double braces (for example {{title}} {{last_name}}). Use no other double braces except {{callback_facts}}.
- Cover every rule of the brief that concerns the conversation. Add nothing the brief does not say. Keep each rule short and literal."""

REVIEW_TASK = """Below are step instructions that were written for the dialogue model from the brief. Check them against the brief, rule by rule.

Look for: a rule of the brief that is missing; a rule that says something the brief does not say or contradicts it; a wrong outcome, reason, queue or field value; a wrong order of priority between rules; a sentence the engine already speaks (above all an offer, a read-back or a `note_lines` sentence); an instruction to say goodbye; a rule that makes the model judge a date or an amount that check_terms checks, count persuasion attempts or word an offer.

Return the corrected instructions, complete, in the same three tags (<global_rules>, <opening>, <negotiation>). Change only what is wrong or missing and keep everything else word for word. Before the tags, list each change in one line starting with "CHANGE:". If nothing needs changing, write "CHANGE: none" and return the instructions unchanged."""

def material(briefs, api_text):
    parts = [f"=== BRIEF FILE {i + 1}: {name} ===\n{text}" for i, (name, text) in enumerate(briefs)]
    if len(briefs) > 1: parts.append("(These files belong together. A later file adds to or replaces rules of an earlier one.)")
    return "\n\n".join(parts) + "\n\n=== TOOL API FILE (OpenAPI) ===\n" + api_text

API_TASK = """The documents below describe a bank's services that a phone agent calls (a service contract, an interface description or the like).
Write the OpenAPI 3 description of exactly these services as one JSON object, and nothing that the documents do not say:
- "servers": [{"url": the base address if the documents give one, otherwise ""}]
- "paths": one entry per service, "/<name of the service as the documents write it>", each with a "post" (or the method the documents give) that has
  "summary", "requestBody" -> "content" -> "application/json" -> "schema" (type object, "properties" with type, "enum" where the documents list the allowed values, "description"; "required"),
  and "responses" -> "200" -> "content" -> "application/json" -> "schema" with the response "properties" (for a list of objects: type array with "items" and their "properties").
- Field names, service names and allowed values exactly as written in the documents, including their spelling and case. No "$ref".
Return the JSON object in one ```json block."""

async def tool_api(trace, briefs):
    """The tool API as OpenAPI, written from the documents when no OpenAPI file came with them."""
    mat = "\n\n".join(f"=== DOCUMENT {i + 1}: {name} ===\n{text}" for i, (name, text) in enumerate(briefs))
    api = await ask_json(trace, "write the tool API (OpenAPI) from the service description in the documents", API_TASK + "\n\n" + mat)
    if not isinstance(api.get("paths"), dict) or not api["paths"]: raise ValueError("the documents gave no service description the builder could turn into a tool API")
    trace.log("tool API written from the documents: " + ", ".join(sorted(api["paths"])))
    return api

async def ask_json(trace, purpose, prompt, tries=3, notes=None):
    """A model call whose answer must hold one JSON object. An answer that cannot be read is asked for again."""
    for attempt in range(1, tries + 1):
        text = await llm.ask(trace, purpose, SYSTEM, prompt)
        try:
            obj = llm.json_of(text)
            if isinstance(obj, dict):
                said = " ".join(text[:text.find("```")].split()) if notes and "```" in text else ""
                if said: trace.log(f"{notes}: {said[:900]}")
                return obj
            why = "the JSON is not an object"
        except ValueError as e: why = str(e)[:120]
        trace.log(f"the answer to '{purpose}' holds no readable JSON object ({why}), try {attempt} of {tries}")
    raise ValueError(f"no readable JSON object in {tries} answers to '{purpose}'")

async def policy_once(trace, n, mat):
    return await ask_json(trace, f"read the brief and the tool API file into the policy configuration (independent reading {n})",
                          ENGINE + "\n" + SCHEMA + "\n\n" + mat + "\n\nReturn the JSON object in one ```json block. Before it, in a few lines, note any rule of the brief you could not express in this configuration.",
                          notes=f"reading {n}, on rules of the brief it could not express in the configuration")

def differences(a, b, path=""):
    """Paths at which two policies differ. Sentences are compared too: a different sentence is a difference to settle."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)): out += differences(a.get(k), b.get(k), path + "/" + str(k))
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        out = []
        for i, (x, y) in enumerate(zip(a, b)): out += differences(x, y, path + "/" + str(i))
        return out
    return [] if a == b else [(path, a, b)]

async def settle(trace, mat, a, b, diffs):
    listing = "\n".join(f"- {p}\n    reading 1: {json.dumps(x)}\n    reading 2: {json.dumps(y)}" for p, x, y in diffs)
    return await ask_json(trace, f"settle {len(diffs)} differences between the two readings of the brief",
                         ENGINE + "\n" + SCHEMA + "\n\n" + mat + "\n\nTwo independent readings of this material produced configurations that differ at these places:\n" + listing +
                         "\n\nReading 1 in full:\n```json\n" + json.dumps(a, indent=1) + "\n```\n\nFor each difference decide from the brief which value is right (it may be neither). "
                         "Differences in wording between two sentences that mean the same: keep the one closer to the brief's own words. Return the final configuration, complete, in one ```json block.")

OPTIONAL = "optional setting: "

def floor_ok(f, depth=3):
    if not isinstance(f, dict): return False
    many = f.get("greatest_of") or f.get("least_of")
    if many is not None: return depth > 0 and isinstance(many, list) and len(many) >= 1 and all(floor_ok(x, depth - 1) for x in many)
    return bool(f.get("field")) or isinstance(f.get("percent_of_full"), (int, float)) or isinstance(f.get("amount"), (int, float))

def cap_ok(c):
    return isinstance(c, dict) and bool(c) and set(c) <= {"total", "per_question"} and all(isinstance(v, int) and v >= 1 for v in c.values())

def without_optional(spec):
    """Takes out every optional setting whose form the engine could not use. A floor that cannot be read is taken out too: the engine then records the full amount only."""
    if spec["calendar"].get("non_business_day") not in (None, "previous", "next"): spec["calendar"].pop("non_business_day")
    d = spec.get("dates") or {}
    if d.get("today_until") is not None and not re.match(r"^\d{1,2}:\d{2}$", str(d["today_until"])): d.pop("today_until")
    o = (spec.get("product") or {}).get("order")
    if o is not None and not (isinstance(o, dict) and o.get("field") and o.get("direction") in ("ascending", "descending")): spec["product"].pop("order")
    for v in (((spec.get("product") or {}).get("types")) or {}).values():
        if isinstance(v, dict) and v.get("floor") is not None and not floor_ok(v["floor"]): v.pop("floor")
    if (spec.get("product") or {}).get("confirm") not in (None, "each", "together"): spec["product"].pop("confirm")
    if (spec.get("identity") or {}).get("max_wrong") is not None and not cap_ok(spec["identity"]["max_wrong"]): spec["identity"].pop("max_wrong")

def check(spec, openapi):
    """Problems in a policy that can be seen without a model: missing keys, values the tool API does not know."""
    bad, api = [], read_api(openapi)
    need = ["bank_name", "language", "address", "call_variables", "now_variable", "calendar", "callback", "identity", "product", "bands", "attempt_offers", "tools", "outcomes", "notes", "sentences"]
    bad += ["missing key: " + k for k in need if k not in spec]
    if bad: return bad
    R, out = spec["tools"], spec["outcomes"]
    for t, v in R.items():
        if v is None and t not in OPTIONAL_ROLES: bad.append(f"tools.{t} is null, but the engine cannot work without this service")
        try: s = service(api, R, t) if isinstance(v, dict) else t
        except ValueError as e: bad.append(str(e)); continue
        if isinstance(v, dict) and v.get("service") is not None and s not in api: bad.append(f"tools.{t}.service: the tool API has no service '{s}' (it has {sorted(k for k, x in api.items() if 'url' in x)})")
    try: used = role_services(api, R, bool(spec["notes"].get("enabled")))
    except ValueError as e: used = {}; bad += [str(e)] if str(e) not in bad else []
    if spec["notes"].get("enabled") and "add_note" in R and R["add_note"] is None: bad.append("notes.enabled is true but tools.add_note is null")
    for name, e in (spec.get("extra_tools") or {}).items():
        if not isinstance(e, dict) or not str(e.get("when") or "").strip(): bad.append(f"extra_tools.{name}: needs a 'when' text"); continue
        if e.get("step") not in (None, "opening", "negotiation", "both"): bad.append(f"extra_tools.{name}.step must be opening, negotiation or both")
        if "url" not in (api.get(name) or {}): bad.append(f"extra_tools.{name}: the tool API has no service of that name" + (" (several paths end with it: use the full path)" if "ambiguous" in (api.get(name) or {}) else ""))
        elif any(api[name] is api[s] for s in used.values()): bad.append(f"extra_tools.{name}: this service already plays one of the seven roles")
    def enum(tool, role, default):
        if tool in R and R[tool] is None: return None
        try: s = service(api, R, tool)
        except ValueError: return None
        f = (R.get(tool) or {}).get(role, default); p = (api.get(s) or {}).get("props", {})
        if s in api and f not in p: bad.append(f"tools.{tool}.{role}: the tool API has no body field '{f}' (it has {sorted(p)})")
        return (p.get(f) or {}).get("enum")
    for t, roles in (("verify_identity", ("question", "answer")), ("create_promise", ("product", "amount", "date")), ("schedule_callback", ("date", "time")), ("transfer_to_agent", ("queue",)), ("close_call", ("outcome", "reason"))):
        for r in roles: enum(t, r, {"question": "field", "product": "product_id"}.get(r, r))
    e = enum("close_call", "outcome", "outcome")
    for o in out.get("table", {}):
        if e and o not in e: bad.append(f"outcomes.table: '{o}' is not an outcome of the tool API {e}")
    def pair_ok(name, p):
        if not (isinstance(p, list) and len(p) == 2): bad.append(f"outcomes.{name}: must be [outcome, reason or null]"); return
        o, r = p; t = out.get("table", {})
        if o not in t: bad.append(f"outcomes.{name}: unknown outcome '{o}'")
        elif (t[o] and r not in t[o]) or (not t[o] and r): bad.append(f"outcomes.{name}: reason '{r}' does not fit outcome '{o}' (allowed: {t[o] or 'none'})")
    for k in ("promise_recorded", "identity_failed", "callback_booked", "promise_service_error", "refused", "fallback_before_verification", "fallback_after_verification"):
        if k in out: pair_ok(k, out[k])
        else: bad.append("outcomes." + k + " is missing")
    for k in ("before_verification", "after_verification"):
        for i, p in enumerate(out.get(k) or []): pair_ok(f"{k}[{i}]", p)
        if not out.get(k): bad.append("outcomes." + k + " is empty")
    q = enum("transfer_to_agent", "queue", "queue") or []
    for x in q:
        if x not in (out.get("transfer") or {}): bad.append(f"outcomes.transfer: no entry for queue '{x}'")
    for x, p in (out.get("transfer") or {}).items():
        if q and x not in q: bad.append(f"outcomes.transfer: '{x}' is not a queue of the tool API {q}")
        pair_ok("transfer." + x, p)
    e = enum("verify_identity", "question", "field") or []
    for i, x in enumerate(spec["identity"].get("questions") or []):
        if e and x.get("field") not in e: bad.append(f"identity.questions[{i}].field '{x.get('field')}' is not in the tool API {e}")
        if not x.get("ask"): bad.append(f"identity.questions[{i}].ask is empty")
        if x.get("kind") not in ("date", "digits", "text"): bad.append(f"identity.questions[{i}].kind must be date, digits or text")
    if not spec["identity"].get("questions"): bad.append("identity.questions is empty")
    for k in ("who_is_speaking", "security_question"):
        L = (spec.get("opening_limits") or {}).get(k)
        if not isinstance(L, dict): bad.append(f"opening_limits.{k} is missing"); continue
        if not isinstance(L.get("times"), int) or L["times"] < 0: bad.append(f"opening_limits.{k}.times must be a whole number")
        if not (L.get("say") or "").strip(): bad.append(f"opening_limits.{k}.say is empty")
        pair_ok(f"opening_limits.{k}.close", L.get("close"))
        if isinstance(L.get("close"), list) and L["close"] not in (out.get("before_verification") or []): bad.append(f"opening_limits.{k}.close must be one of outcomes.before_verification")
    n = spec["notes"]
    if n.get("enabled"):
        e = enum("add_note", "reason", "reason") or []
        for x in n.get("reasons") or []:
            if e and x not in e: bad.append(f"notes.reasons: '{x}' is not in the tool API {e}")
        for k in ("service_error_reason", "refused_reason"):
            if n.get(k) not in (n.get("reasons") or []): bad.append(f"notes.{k} must be one of notes.reasons")
        cf = n.get("close_from_notes") or {}
        for k, p in (cf.get("all") or {}).items(): pair_ok("close_from_notes.all." + k, p)
        if cf.get("else_outcome") not in out.get("table", {}): bad.append("notes.close_from_notes.else_outcome is not an outcome")
    for i, b in enumerate(spec["bands"]):
        d = b.get("deadline") or {}
        if d.get("unit") not in ("business_days", "calendar_days") or not isinstance(d.get("n"), (int, float)): bad.append(f"bands[{i}].deadline needs unit and n")
        if not isinstance(b.get("attempts"), int): bad.append(f"bands[{i}].attempts must be a whole number")
        if b.get("attempts", 0) > len(spec["attempt_offers"]): bad.append(f"bands[{i}] allows {b['attempts']} attempts but attempt_offers has {len(spec['attempt_offers'])}")
    for i, a in enumerate(spec["attempt_offers"]):
        if a.get("amount") not in ("full", "floor", "full_or_floor"): bad.append(f"attempt_offers[{i}].amount must be full, floor or full_or_floor")
        if a.get("date") not in ("last_business_day_of_week", "deadline", "next_business_day", "today", "", None): bad.append(f"attempt_offers[{i}].date is not one of the allowed kinds")
    for h in spec["calendar"].get("holidays") or []:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(h)): bad.append(f"calendar.holidays: '{h}' is not YYYY-MM-DD")
    if spec["calendar"].get("non_business_day") not in (None, "previous", "next"): bad.append(OPTIONAL + 'calendar.non_business_day must be "previous" or left out')
    until = (spec.get("dates") or {}).get("today_until")
    if until is not None and not re.match(r"^\d{1,2}:\d{2}$", str(until)): bad.append(OPTIONAL + "dates.today_until must be HH:MM or left out")
    order = (spec.get("product") or {}).get("order")
    if order is not None and not (isinstance(order, dict) and order.get("field") and order.get("direction") in ("ascending", "descending")): bad.append(OPTIONAL + 'product.order needs "field" and "direction" ("ascending" or "descending"), or is left out')
    lang = str(spec.get("language") or "English").strip().lower()
    phr = spec.get("phrases")
    if lang not in ("english", "en", "") and not isinstance(phr, dict): bad.append('phrases: the agent speaks ' + str(spec.get("language")) + ', so the key "phrases" is required with every pattern in that language')
    if isinstance(phr, dict):
        need_tokens = {"date": ["<day>", "<month>"], "amount": ["<n>"], "full_amount": ["<amount>"], "floor_amount": ["<floor_name>", "<amount>"], "offer": ["<what>", "<product>", "<date>"], "offer_no_date": ["<what>", "<product>"],
                       "readback_item": ["<amount>", "<product>", "<date>"], "readback": ["<items>"], "concerns": ["<products>"]}
        for k, toks in need_tokens.items():
            if not isinstance(phr.get(k), str) or [t for t in toks if t not in phr[k]]: bad.append(f"phrases.{k} must be a sentence pattern that holds {' '.join(toks)}")
        if not (isinstance(phr.get("weekdays"), list) and len(phr["weekdays"]) == 7): bad.append("phrases.weekdays must list seven day names, Monday first")
        for k in ("day", "days", "and", "thanks", "say_again"):
            if not isinstance(phr.get(k), str) or not phr[k].strip(): bad.append(f"phrases.{k} is missing")
        for k in ("next_product", "ask_product", "anything_else", "account_error"):
            if not str((spec.get("sentences") or {}).get(k) or "").strip(): bad.append(f"sentences.{k} is required when the agent does not speak English (the engine's own wording is English)")
        if not (isinstance(phr.get("months"), list) and len(phr["months"]) == 12): bad.append("phrases.months must list twelve month names, January first")
    if (spec.get("identity") or {}).get("max_wrong") is not None and not cap_ok(spec["identity"]["max_wrong"]): bad.append(OPTIONAL + 'identity.max_wrong must be {"total": whole number} or {"per_question": whole number}, or left out')
    if (spec.get("product") or {}).get("confirm") not in (None, "each", "together"): bad.append(OPTIONAL + 'product.confirm must be "each" or left out')
    for t, v in (((spec.get("product") or {}).get("types")) or {}).items():
        if isinstance(v, dict) and v.get("floor") is not None and not floor_ok(v["floor"]):
            bad.append(OPTIONAL + f'product.types.{t}.floor is not one of the allowed forms: {{"field": ...}}, {{"percent_of_full": number, optional "round"}}, {{"amount": number}}, or {{"greatest_of": [several of these]}} / {{"least_of": [...]}}')
    for k in ("opening", "identity_failed", "after_callback", "after_transfer", "verified_ack", "debt_intro", "product_statement", "first_ask_single", "confirm_question", "promise_recorded", "promise_failed", "change_later", "goodbye"):
        if not (spec["sentences"].get(k) or "").strip(): bad.append("sentences." + k + " is empty")
    cv = set(spec["call_variables"])
    for k, s in spec["sentences"].items():
        for v in re.findall(r"\{\{\s*(\w+)\s*\}\}", str(s)):
            if v not in cv: bad.append(f"sentences.{k} uses {{{{{v}}}}}, which is not a call variable")
    if spec["now_variable"] not in cv: bad.append("now_variable is not a call variable")
    return bad

def check_prompts(prm, spec):
    bad, cv = [], set(spec["call_variables"]) | {"callback_facts"}
    for k in ("opening", "negotiation"):
        if not (prm.get(k) or "").strip(): bad.append(k + " is empty"); continue
        for v in re.findall(r"\{\{\s*([\w.]+)\s*\}\}", prm[k]):
            if v not in cv: bad.append(f"{k} uses {{{{{v}}}}}, which is not a call variable")
    off = [t for t in OPTIONAL_ROLES if t in (spec.get("tools") or {}) and spec["tools"][t] is None]
    if "{{callback_facts}}" not in (prm.get("opening") or "") and "schedule_callback" not in off: bad.append("opening lacks the {{callback_facts}} placeholder")
    for tool, where in (("verify_identity", "opening"), ("schedule_callback", "opening"), ("wrap_up", "opening"), ("no_answer", "opening"), ("check_terms", "negotiation"), ("customer_refused", "negotiation"), ("customer_confirmed", "negotiation"), ("transfer_to_agent", "negotiation")):
        if tool not in (prm.get(where) or "") and tool not in off: bad.append(f"{where} never mentions {tool}")
    for tool in off:
        for where in ("opening", "negotiation"):
            if tool in (prm.get(where) or ""): bad.append(f"{where} mentions {tool} although the bank has no such service (tools.{tool} is null)")
    if spec["notes"].get("enabled") and "skip_product" not in (prm.get("negotiation") or ""): bad.append("negotiation never mentions skip_product although notes are enabled")
    if not spec["notes"].get("enabled") and "skip_product" in (prm.get("negotiation") or ""): bad.append("negotiation mentions skip_product although notes are not enabled")
    return bad

def parse_prompts(text):
    g = llm.tag_of(text, "global_rules") or ""
    return {"global_rules": [re.sub(r"^[-*\d.\s]+", "", l).strip() for l in g.splitlines() if l.strip()],
            "opening": llm.tag_of(text, "opening") or "", "negotiation": llm.tag_of(text, "negotiation") or ""}

def prompts_text(prm):
    return "<global_rules>\n" + "\n".join(prm["global_rules"]) + "\n</global_rules>\n\n<opening>\n" + prm["opening"] + "\n</opening>\n\n<negotiation>\n" + prm["negotiation"] + "\n</negotiation>"

async def extract(trace, briefs, openapi, api_text):
    """briefs: [(file name, text)]. Returns the full spec."""
    mat = material(briefs, api_text)
    a, b = await asyncio.gather(policy_once(trace, 1, mat), policy_once(trace, 2, mat))
    diffs = differences(a, b)
    wording = ("/sentences/", "/guidance/", "/outcomes/meaning/", "/closing_lines/", "/test_variables/", "/hints/", "/ask", "/text", "/wrong_sentence", "/floor_name", "/words", "/bank_name", "/address")
    hard = [d for d in diffs if not any(w in d[0] for w in wording)]
    trace.log(f"the two readings differ at {len(diffs)} places, {len(hard)} of them in rules or values" + ("" if not hard else ": " + ", ".join(p for p, _, _ in hard[:40])))
    spec = await settle(trace, mat, a, b, hard) if hard else a
    for attempt in range(2):
        bad = check(spec, openapi)
        if not bad: break
        trace.log("policy check found: " + "; ".join(bad))
        spec = await ask_json(trace, "repair the policy configuration after the check against the tool API file",
                             ENGINE + "\n" + SCHEMA + "\n\n" + mat + "\n\nThis configuration was produced:\n```json\n" + json.dumps(spec, indent=1) + "\n```\n\nA check found these problems:\n- " +
                             "\n- ".join(bad) + "\n\nReturn the corrected configuration, complete, in one ```json block.")
    bad = check(spec, openapi)
    soft = [x for x in bad if x.startswith(OPTIONAL)]
    if soft:                                   # an optional setting that still has the wrong form is taken out: the engine then does what it does without it
        without_optional(spec); trace.log("optional settings left out, the engine's standard behaviour applies: " + "; ".join(soft)); bad = check(spec, openapi)
    if bad: raise ValueError("the policy still fails the check: " + "; ".join(bad))
    trace.log("policy accepted: " + json.dumps({k: spec[k] for k in ("calendar", "callback", "bands", "attempt_offers", "notes")})[:1500])

    base = ENGINE + "\n\n" + mat + "\n\n=== THE POLICY CONFIGURATION (already extracted; use its exact values and sentences) ===\n```json\n" + json.dumps(spec, indent=1) + "\n```\n\n"
    prm = parse_prompts(await llm.ask(trace, "write the step instructions for the dialogue model from the brief", SYSTEM, base + PROMPT_TASK))
    for attempt in range(2):
        bad = check_prompts(prm, spec)
        if not bad: break
        trace.log("instruction check found: " + "; ".join(bad))
        prm = parse_prompts(await llm.ask(trace, "repair the step instructions after the check", SYSTEM, base + PROMPT_TASK + "\n\nThese instructions were produced:\n\n" + prompts_text(prm) +
                                          "\n\nA check found these problems:\n- " + "\n- ".join(bad) + "\n\nReturn the corrected instructions, complete, in the three tags."))
    review = await llm.ask(trace, "review the step instructions against the brief, rule by rule", SYSTEM, base + "=== INSTRUCTION WRITING RULES ===\n" + PROMPT_TASK + "\n\n=== THE INSTRUCTIONS TO CHECK ===\n" + prompts_text(prm) + "\n\n" + REVIEW_TASK)
    changes = [l.strip() for l in review.splitlines() if l.strip().startswith("CHANGE:")]
    trace.log("review: " + (" | ".join(changes) or "no change lines")[:1500])
    new = parse_prompts(review)
    if new["opening"] and new["negotiation"] and not check_prompts(new, spec): prm = new
    else: trace.log("the reviewed instructions failed the check and were not used")
    bad = check_prompts(prm, spec)
    if bad: raise ValueError("the instructions still fail the check: " + "; ".join(bad))
    spec["prompts"] = prm
    return spec
