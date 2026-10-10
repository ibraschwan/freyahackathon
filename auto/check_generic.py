"""Fails when builder/ contains something taken from a brief: a date, a name, a value or a sentence.

The builder must read a brief, not know one. Checked: holiday dates, the outcome / reason / queue / product-type /
field names of every known tool API file and brief, and the bank names. Words that are also plain English or part
of the engine's own vocabulary are listed in ALLOWED with the reason.

    python3 auto/check_generic.py
"""
import json, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = {p.name: p.read_text() for p in (ROOT / "builder").glob("*.py")}
BRIEFS = [ROOT / "briefs" / "brief-a.md", ROOT / "briefs" / "brief-b.md", ROOT / "tests" / "variants" / "variant-c.md"]
APIS = [ROOT / "tools" / "openapi.json", ROOT / "tests" / "variants" / "variant-c.openapi.json"]
# tokens of a tool API that the engine may name itself
ALLOWED = {
    "the seven tool names stay the same in every brief (README)": {"verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call"},
    "role names of the spec schema, plain English": {"outcome", "reason", "queue", "date", "time", "amount", "answer", "question", "product", "products", "error", "hint", "ok", "done", "field", "type", "kind", "text", "day", "value",
                                                   "code", "result", "detail", "items", "ref", "comment", "match", "passed", "verified", "team", "slot", "agent"},
    "keys of the spec schema that happen to be values in a brief": {"refused"},
    "default field names used only when a spec names none; every one can be overridden by the spec": {"customer_id", "product_id", "past_due", "days_late", "wrong_answers_left", "all_verified"},
}
ok_words = set().union(*ALLOWED.values())

def api_tokens(api):
    out = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k == "properties" and isinstance(v, dict): out.update(v.keys())
                if k == "enum" and isinstance(v, list): out.update(str(e) for e in v)
                walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(api); return out

bad = []
for f in APIS:
    for tok in sorted(api_tokens(json.load(open(f))) - ok_words):
        if len(tok) < 4: continue
        for name, text in SRC.items():
            # as a quoted value, in code or in an instruction text. The bare word in a sentence ("a promise", "already paid")
            # is English, not a value of the brief, and is not flagged.
            for m in re.finditer(r"""(?<![A-Za-z0-9_])(\\?["'])""" + re.escape(tok) + r"""\1""", text):
                line = text[:m.start()].count("\n") + 1
                bad.append(f"{name}:{line}: {m.group(0)} is a value or field of {f.name}")
for f in BRIEFS:
    text = f.read_text()
    for d in sorted(set(re.findall(r"\b20\d\d-\d\d-\d\d\b", text))):
        for name, src in SRC.items():
            if d in src: bad.append(f"{name}: the date {d} comes from {f.name}")
    for bank in re.findall(r"\b(Freya Bank|Nordbank)\b", text)[:1]:
        for name, src in SRC.items():
            if bank in src: bad.append(f"{name}: the bank name '{bank}' comes from {f.name}")
    # sentences the brief puts in quotes must not be in the builder
    for q in sorted(set(re.findall(r'"([^"\n]{18,})"', text))):
        for name, src in SRC.items():
            if q in src: bad.append(f"{name}: the sentence \"{q[:50]}...\" comes from {f.name}")
if bad:
    print("builder/ is NOT brief-agnostic:"); print("\n".join("  " + b for b in sorted(set(bad)))); sys.exit(1)
print(f"builder/ holds nothing from the briefs ({len(SRC)} files checked against {len(BRIEFS)} briefs and {len(APIS)} tool API files)")
