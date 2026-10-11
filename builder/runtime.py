"""Python that runs INSIDE the phone agent: code steps, code tools and hooks.

Every snippet is LIB (helpers, with the policy spec embedded as JSON) plus a short body. Nothing here knows a
brief: all numbers, names and sentences come from the spec the builder extracted.

Rules for this file (the platform's, see docs/tools-and-code.md): no double braces anywhere in the code, a snippet
never raises by accident, and a deliberate `raise Exception('RULE: ...')` is how a tool refuses a call and tells
the dialogue model what to do instead. Booleans are never used for routing, only strings.
"""

LIB = r'''
import json, re, datetime
S = json.loads(SPEC_TEXT)
ONE = datetime.timedelta(days=1)
WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MO = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
CAL = S.get('calendar') or dict()
HOL = set(CAL.get('holidays') or [])
WK = set(CAL.get('weekend_days') if CAL.get('weekend_days') is not None else [5, 6])
SEN = S.get('sentences') or dict()
OUT = S.get('outcomes') or dict()
NOTES = S.get('notes') or dict()
LB = chr(123) * 2
RB = chr(125) * 2
def isbd(d):
    return d.weekday() not in WK and d.isoformat() not in HOL
def nextbd(d):
    d = d + ONE
    n = 0
    while not isbd(d) and n < 400:
        d = d + ONE
        n += 1
    return d
#@cal
def addbd(d, n):
    for _ in range(int(n)):
        d = nextbd(d)
    return d
#@core
def say(d):
    return WD[d.weekday()] + ' ' + str(d.day) + ' ' + MO[d.month - 1] + ' ' + str(d.year)
def tag(d):
    return say(d) + ' [' + d.isoformat() + ']'
def why(d):
    if d.isoformat() in HOL:
        return 'a bank holiday'
    if d.weekday() in WK:
        return 'a weekend day'
    return ''
def num(x):
    try:
        return float(x)
    except Exception:
        return None
def money(x):
    return format(float(x), '.2f')
def iso(s):
    return datetime.date.fromisoformat(str(s)[:10])
def hm(m):
    return '%02d:%02d' % (int(m) // 60, int(m) % 60)
def mins_of(s):
    m = re.match(r'^\s*(\d{1,2})(?:[:.h](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?\s*$', str(s).strip().lower())
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2) or 0)
    ap = (m.group(3) or '').replace('.', '')
    if ap == 'pm' and h < 12:
        h += 12
    if ap == 'am' and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi
def today_of(v):
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?', str(v.get(S.get('now_variable') or 'now') or ''))
    return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), int(m.group(4) or 0) * 60 + int(m.group(5) or 0)
def base(v):
    try:
        st = json.loads(str(v.get('st_json') or ''))
        if isinstance(st, dict) and st.get('stage'):
            return st
    except Exception:
        pass
    return dict(stage='opening', id='open', idv=[], products=[], plan=dict(), pnotes=dict(), promises=dict(), tries=dict(), perr=[], notes=dict(), ntries=dict(), transfer='', callback='', closed='', pend='', npend='',
                prop=dict(), toomuch=[], floored=[], given=[], said=[], mo='', mr='', fin='')
def pending(v):
    out = []
    try:
        for k in sorted(str(x) for x in v.keys()):
            if k.startswith('ev_') and v.get(k):
                try:
                    out.append((k, json.loads(str(v.get(k)))))
                except Exception:
                    pass
    except Exception:
        pass
    return out
def fold(st, evs):
    """Apply what the dialogue model reported since the last checkpoint. Two tools called in one message run side by
    side and cannot see each other, so the order is settled here: a note or an exact agreement for a product wins over
    an agreement made for "all" in the same batch. Returns the reported refusals and the new notes, in order."""
    flat = [e for k, es in evs for e in es]
    noted = set(e[1] for e in flat if e[0] == 'note')
    exact = set(e[1] for e in flat if e[0] == 'plan' and not e[5])
    ref = []
    new = []
    for e in flat:
        if e[0] == 'plan':
            i = e[1]
            if i in st['promises'] or (e[5] and (i in noted or i in exact)):
                continue
            st['plan'][i] = dict(amount=e[2], date=e[3], capped=e[4])
            st['pnotes'].pop(i, None)
            if i in st['given']:
                st['given'].remove(i)
        elif e[0] == 'note':
            i = e[1]
            if i in st['promises']:
                continue
            st['pnotes'][i] = e[2]
            st['plan'].pop(i, None)
            new.append((i, e[2]))
        elif e[0] == 'refuse':
            ref.append(e)
        elif e[0] == 'finish':
            st['mo'] = e[1]
            st['mr'] = e[2]
    return ref, new
def gst(v):
    st = base(v)
    evs = pending(v)
    st['_keys'] = [k for k, es in evs]
    st['_ref'], st['_new'] = fold(st, evs)
    return st
def pst(v, st):
    """Write the checkpoint. Only code the engine runs one at a time calls this; the model's own tools use emit()."""
    keys = st.pop('_keys', [])
    st.pop('_ref', None)
    st.pop('_new', None)
    s = json.dumps(st)
    while RB in s:
        s = s.replace(RB, chr(125) + ' ' + chr(125))
    while LB in s:
        s = s.replace(LB, chr(123) + ' ' + chr(123))
    v['st_json'] = s
    for k in keys:
        v[k] = ''
    try:
        v['live_state'] = live(st)
    except Exception:
        pass
def emit(v, evs):
    """Report something from a tool of the dialogue model. Each call writes its own variable, so two tools in one
    message cannot overwrite each other. The engine merges the reports right after (the sync step)."""
    v['ev_' + datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S%f') + '_' + str(id(evs) % 997)] = json.dumps(evs)
    v['dirty'] = '1'
def fill(v, s):
    def rep(m):
        return str(v.get(m.group(1)) or '')
    return re.sub(r'<<(\w+)>>', rep, str(s or ''))
def pair(x):
    if isinstance(x, (list, tuple)) and x:
        return str(x[0]), (str(x[1]) if len(x) > 1 and x[1] not in (None, '') else '')
    return '', ''
def set_final(v, o, r, line):
    v['final_outcome'] = o
    v['final_reason'] = r or ''
    v['final_line'] = fill(v, line or SEN.get('goodbye') or 'Thank you, goodbye.')
def closing_line(o, r, said=None):
    cl = S.get('closing_lines') or dict()
    x = cl.get(o + '/' + r) or cl.get(o) or ''
    if x and said and x in said:
        x = ''
    return (x + ' ' if x else '') + (SEN.get('goodbye') or 'Thank you, goodbye.')
#@cal
def cb_slots(today, mins):
    C = S.get('callback') or dict()
    lo = mins_of(C.get('from') or '00:00') or 0
    hi = mins_of(C.get('to') or '23:59') or 1439
    days = []
    if C.get('include_today', True):
        days.append(today)
    d = today
    for _ in range(int(C.get('business_days_ahead', 1))):
        d = nextbd(d)
        days.append(d)
    out = []
    for d in days:
        a = lo
        if d == today and C.get('after_now', True):
            a = max(lo, mins + 1)
        if a <= hi:
            out.append((d, a, hi))
    return out
def lastbd_week(d):
    mon = d - datetime.timedelta(days=d.weekday())
    x = mon + datetime.timedelta(days=6)
    while x >= mon and not isbd(x):
        x = x - ONE
    return x if x >= mon else None
def pick_date(kind, today, dl):
    x = None
    if kind == 'deadline':
        x = dl
    elif kind == 'today':
        x = today if isbd(today) else nextbd(today)
    elif kind == 'next_business_day':
        x = nextbd(today)
    elif kind == 'last_business_day_of_week':
        x = lastbd_week(today)
        if x is None or x <= today:
            x = lastbd_week(today + datetime.timedelta(days=7 - today.weekday()))
        if x is None:
            x = nextbd(today)
    if x is not None and dl is not None and x > dl:
        x = dl
    return x
#@terms
def terms(p, today):
    P = S.get('product') or dict()
    typ = str(p.get(P.get('type_field') or 'type') or '')
    T = (P.get('types') or dict()).get(typ) or (P.get('types') or dict()).get('*') or dict()
    words = str(T.get('words') or typ.replace('_', ' ') or 'product')
    for k in p:
        words = words.replace('<' + str(k) + '>', str(p.get(k)))
    full = num(p.get(P.get('full_field') or 'past_due')) or 0.0
    F = T.get('floor') or dict()
    floor = None
    if F.get('field'):
        floor = num(p.get(F.get('field')))
    elif F.get('percent_of_full') is not None:
        floor = round(full * float(F.get('percent_of_full')) / 100.0, 2)
    elif F.get('amount') is not None:
        floor = float(F.get('amount'))
    if floor is None or floor > full or floor <= 0:
        floor = full
    late = int(num(p.get(P.get('days_late_field') or 'days_late')) or 0)
    bands = S.get('bands') or []
    band = None
    for b in bands:
        if (b.get('min') is None or late >= b.get('min')) and (b.get('max') is None or late <= b.get('max')):
            band = b
            break
    if band is None and bands:
        band = bands[-1] if late > (bands[-1].get('max') or 0) else bands[0]
    band = band or dict()
    D = band.get('deadline') or dict()
    dl = None
    if D.get('n') is not None:
        if D.get('unit') == 'calendar_days':
            dl = today + datetime.timedelta(days=int(D.get('n')))
            while not isbd(dl):
                dl = dl - ONE if D.get('roll') == 'previous' else dl + ONE
        else:
            dl = addbd(today, D.get('n'))
    offers = []
    k = int(band.get('attempts') if band.get('attempts') is not None else 0)
    for a in (S.get('attempt_offers') or [])[:k]:
        x = pick_date(a.get('date'), today, dl)
        offers.append(dict(amount=str(a.get('amount') or 'full'), date=x.isoformat() if x else '', text=str(a.get('text') or '')))
    return dict(id=str(p.get(P.get('id_field') or 'product_id')), type=typ, words=words, full=round(full, 2), floor=round(floor, 2), floor_name=str(T.get('floor_name') or 'minimum amount'),
                late=late, band=str(band.get('name') or ''), deadline=dl.isoformat() if dl else '', attempts=k, offers=offers)
def amount_text(a, p):
    if a == 'floor':
        return 'the ' + p['floor_name'] + ' of ' + money(p['floor'])
    if a == 'full_or_floor':
        return 'the full amount ' + money(p['full']) + ' (but the ' + p['floor_name'] + ' of ' + money(p['floor']) + ' if the customer already said the full amount is too much)'
    return 'the full amount ' + money(p['full'])
#@core
def open_ids(st):
    return [p['id'] for p in st['products'] if p['id'] not in st['promises'] and p['id'] not in st['plan'] and p['id'] not in st['pnotes'] and p['id'] not in st['perr'] and p['id'] not in st['given']]
def prod(st, i):
    for p in st['products']:
        if p['id'] == i:
            return p
    return None
def offer_line(st, p, k):
    """The sentence for persuasion attempt k (0-based) of product p."""
    o = p['offers'][k]
    kind = o['amount']
    if kind == 'floor' or (kind == 'full_or_floor' and p['id'] in st['toomuch']):
        am = 'the ' + p['floor_name'] + ' of ' + money(p['floor'])
        extra = (' ' + SEN.get('rest_overdue')) if SEN.get('rest_overdue') else ''
    else:
        am = 'the full amount of ' + money(p['full'])
        extra = ''
    return 'Could you pay ' + am + ' for your ' + p['words'] + (' by ' + say(iso(o['date'])) if o['date'] else '') + '?' + extra
#@live
def readback(st):
    parts = []
    for p in st['products']:
        x = st['plan'].get(p['id'])
        if x and p['id'] not in st['promises']:
            parts.append(money(x['amount']) + ' for your ' + p['words'] + ' on ' + say(iso(x['date'])) + (' (the latest possible date for this product)' if x.get('capped') else ''))
    return 'To confirm: you will pay ' + ', and '.join(parts) + '. ' + (SEN.get('confirm_question') or 'Do you confirm?')
def live(st):
    L = []
    if st['stage'] != 'verified':
        L.append('Security questions passed so far: ' + (', '.join(st['idv']) or 'none') + '.')
        return '\n'.join(L)
    planned = False
    for p in st['products']:
        i = p['id']
        if i in st['promises']:
            x = st['promises'][i]
            t = 'PROMISE RECORDED at the bank: ' + money(x['amount']) + ' on ' + say(iso(x['date'])) + '. It cannot be changed or cancelled in this call.'
        elif i in st['perr']:
            t = 'the promise could NOT be recorded (service failure). Do not try again.'
        elif i in st['plan']:
            x = st['plan'][i]
            planned = True
            t = 'AGREED, not recorded yet: ' + money(x['amount']) + ' on ' + say(iso(x['date'])) + (' (moved to this product\'s latest possible date)' if x.get('capped') else '')
        elif i in st['pnotes'] or i in st['given']:
            t = 'settled without a promise' + (': ' + str(st['pnotes'][i]) if i in st['pnotes'] else '')
        else:
            n = int(st['prop'].get(i) or 0)
            t = 'OPEN' + ('; persuasion offers made so far: ' + str(n) + ' of ' + str(p['attempts']) if n else '')
        L.append('- ' + p['words'] + ' [' + i + ']: ' + t)
    op = open_ids(st)
    if op:
        L.append('The product in discussion now: ' + (prod(st, op[0]) or dict(words=''))['words'] + ' [' + op[0] + '].')
    elif planned:
        L.append('The system has read the agreement back. A clear yes -> CALL customer_confirmed. A changed day or amount -> CALL check_terms again.')
    else:
        L.append('Nothing is open. Answer what the customer still asks. When they have nothing more, CALL wrap_up.')
    return '\n'.join(L)
#@decide
def decide(st, mo, mr, strict):
    """The outcome and reason this call must be closed with. `strict` refuses a close the records do not support."""
    mo = str(mo or '').strip()
    mr = str(mr or '').strip()
    if mr.lower() in ('none', 'null', '-'):
        mr = ''
    T = OUT.get('table') or dict()
    def ok(o, r):
        return o in T and ((not T[o] and not r) or (r in T[o]))
    if st['transfer']:
        return pair((OUT.get('transfer') or dict()).get(st['transfer']) or [mo, mr])
    if st['callback'] == 'booked':
        return pair(OUT.get('callback_booked'))
    if st['stage'] != 'verified':
        if st['id'] == 'failed':
            return pair(OUT.get('identity_failed'))
        allowed = [pair(x) for x in (OUT.get('before_verification') or [])]
        if (mo, mr) in allowed:
            return mo, mr
        same = [x for x in allowed if x[0] == mo]
        if len(same) == 1:
            return same[0]
        byr = [x for x in allowed if mr and x[1] == mr]
        if len(byr) == 1:
            return byr[0]
        if strict:
            raise Exception('RULE: the customer is not verified, so the call can only end as one of: ' + '; '.join(o + (' / ' + r if r else '') for o, r in allowed) + '. CALL finish again with the pair that fits what happened.')
        return same[0] if same else pair(OUT.get('fallback_before_verification') or (allowed[-1] if allowed else [mo, mr]))
    if st['promises']:
        return pair(OUT.get('promise_recorded'))
    prods = st['products']
    if NOTES.get('enabled') and prods:
        CF = NOTES.get('close_from_notes') or dict()
        reasons = [st['pnotes'].get(p['id']) or st['notes'].get(p['id']) or '' for p in prods]
        if all(reasons):
            for k, val in (CF.get('all') or dict()).items():
                if all(x == k for x in reasons):
                    return pair(val)
            skip = CF.get('else_reason_from_first_note_not_in') or []
            for x in reasons:
                if x not in skip:
                    return str(CF.get('else_outcome') or mo), x
            return str(CF.get('else_outcome') or mo), reasons[0]
    if st['perr']:
        return pair(OUT.get('promise_service_error'))
    allowed = [pair(x) for x in (OUT.get('after_verification') or [])]
    if (mo, mr) in allowed:
        return mo, mr
    same = [x for x in allowed if x[0] == mo]
    if len(same) == 1:
        return same[0]
    byr = [x for x in allowed if mr and x[1] == mr]
    if len(byr) == 1:
        return byr[0]
    if strict:
        raise Exception('RULE: no promise is recorded, so the call can only end as one of: ' + '; '.join(o + (' / ' + r if r else '') for o, r in allowed) + '. CALL finish again with the pair that fits what happened.')
    return same[0] if same else pair(OUT.get('fallback_after_verification') or (allowed[0] if allowed else [mo, mr]))
#@core
def body_of(config):
    b = config.get('body') if isinstance(config, dict) else None
    return b if isinstance(b, dict) else dict()
def data_of(result):
    d = result.get('data') if isinstance(result, dict) else None
    if not isinstance(d, dict):
        d = dict()
        if isinstance(result, dict):
            result['data'] = d
    return d
def good(result, d):
    """True when the bank carried the action out."""
    if not isinstance(result, dict) or str(result.get('status')) != 'success':
        return False
    okf = (S.get('response') or dict()).get('ok') or 'ok'
    return d.get(okf) is True or str(d.get(okf)).lower() == 'true'
'''

# ------------------------------------------------------------------ code steps
SETUP = r'''
try:
    today, mins = today_of(vars)
    st = gst(vars)
    slots = cb_slots(today, mins)
    L = ['Now: ' + tag(today) + ', time ' + hm(mins) + '.', 'A callback may only be booked inside one of these slots (both ends included):']
    for d, a, b in slots:
        L.append('- ' + tag(d) + (' (today)' if d == today else '') + ': from ' + hm(a) + ' to ' + hm(b))
    if not slots:
        L.append('- (no slot is left)')
    L.append('Every other day and every other time is OUTSIDE the window.')
    tom = today + ONE
    okd = [d for d, a, b in slots]
    L.append('"Tomorrow" is ' + tag(tom) + (': inside the window.' if tom in okd else ': OUTSIDE the window' + (' (it is ' + why(tom) + ').' if why(tom) else '.')))
    L.append('Clock times: "around eleven in the morning" = 11:00, "noon" = 12:00, "half past two in the afternoon" = 14:30, "5 pm" = 17:00, "nine in the evening" = 21:00.')
    vars['callback_facts'] = '\n'.join(L)
    pst(vars, st)
except Exception as e:
    vars['callback_facts'] = 'Now: ' + str(vars.get('now')) + '.'
    vars['live_state'] = ''
vars['id_state'] = 'open'
vars['account_facts'] = '(not loaded yet)'
vars['debt_line'] = ''
vars['enter_line'] = ''
vars['dirty'] = '0'
vars['sync_state'] = ''
vars['final_line'] = fill(vars, SEN.get('goodbye') or 'Thank you, goodbye.')
'''

PREPARE = r'''
def _run(vars):
    today, mins = today_of(vars)
    st = gst(vars)
    raw = vars.get('products_json')
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict):
        raw = [raw[k] for k in sorted(raw)]
    ps = [terms(p, today) for p in raw]
    if not ps:
        raise Exception('no products')
    st['products'] = ps
    st['stage'] = 'verified'
    st['id'] = 'verified'
    many = len(ps) > 1
    L = ['TODAY: ' + tag(today) + '.', '']
    for n, p in enumerate(ps):
        L.append('PRODUCT ' + str(n + 1) + ': ' + p['words'] + '   (product_id ' + p['id'] + ')')
        L.append('- FULL past-due amount: ' + money(p['full']) + '. Days late: ' + str(p['late']) + '.')
        L.append('- FLOOR (the ' + p['floor_name'] + ', the lowest amount that can be recorded): ' + money(p['floor']) + '. Recordable amounts: ' + money(p['floor']) + ' to ' + money(p['full']) + ', both included.')
        if p['deadline']:
            L.append('- DEADLINE (the latest date that can be recorded): ' + tag(iso(p['deadline'])) + '.')
        L.append('- PERSUASION ATTEMPTS allowed for this product: ' + str(p['attempts']) + '.')
        for k, o in enumerate(p['offers']):
            L.append('  ATTEMPT ' + str(k + 1) + ': propose ' + amount_text(o['amount'], p) + (' on ' + tag(iso(o['date'])) if o['date'] else '') + '.' + (' ' + o['text'] if o['text'] else ''))
        L.append('  After ATTEMPT ' + str(p['attempts']) + ' is refused: stop, this product ends without a promise.' if p['attempts'] else '  No persuasion attempt exists for this product: after a flat refusal it ends without a promise.')
        L.append('')
    dls = [iso(p['deadline']) for p in ps if p['deadline']]
    if dls:
        last = max(dls)
        L.append('DATE TABLE (every day from today to the last deadline; look the customer\'s day up here, never calculate a date yourself):')
        d = today
        n = 0
        while d <= last and n < 70:
            lab = '- ' + tag(d) + (' (today)' if d == today else '') + ': '
            if not isbd(d):
                nb = nextbd(d)
                lab += 'NOT allowed, it is ' + why(d) + ' -> the next business day is ' + tag(nb)
            elif many:
                okp = [str(i + 1) for i, p in enumerate(ps) if p['deadline'] and d <= iso(p['deadline'])]
                bad = [str(i + 1) for i, p in enumerate(ps) if p['deadline'] and d > iso(p['deadline'])]
                lab += 'ALLOWED for product ' + ', '.join(okp) + ('; AFTER the deadline of product ' + ', '.join(bad) if bad else '')
            else:
                lab += 'ALLOWED'
            L.append(lab)
            d = d + ONE
            n += 1
        L.append('- any later day: NOT allowed, it is after the deadline.')
        L.append('- any day before today: NOT allowed, it is in the past.')
        L.append('')
    L.append('WHAT THE CUSTOMER\'S WORDS MEAN:')
    L.append('- "today" = ' + tag(today) + '; "tomorrow" = ' + tag(today + ONE) + '; "the day after tomorrow" = ' + tag(today + ONE + ONE))
    monday = today - datetime.timedelta(days=today.weekday())
    follow = ((S.get('dates') or dict()).get('next_weekday') or 'following_week') == 'following_week'
    for i in range(7):
        t = monday + datetime.timedelta(days=i)
        c = today + datetime.timedelta(days=(i - today.weekday()) % 7)
        nx = t + datetime.timedelta(days=7) if follow else (c if c > today else c + datetime.timedelta(days=7))
        L.append('- "this ' + WD[i] + '" = ' + tag(t) + ('' if t >= today else ' (already past)') + '; "next ' + WD[i] + '" = ' + tag(nx) + '; plain "' + WD[i] + '" or "on ' + WD[i] + '" = ' + tag(c))
    L.append('- a day of the month with no month ("the 26th") = that day in this month if it is still to come, otherwise in the next month.')
    vars['account_facts'] = '\n'.join(L)
    def stmt(p):
        s = SEN.get('product_statement') or 'Your <product> has a past-due amount of <amount> and is <days_late> <days> late.'
        return s.replace('<product>', p['words']).replace('<amount>', money(p['full'])).replace('<days_late>', str(p['late'])).replace('<days>', 'day' if p['late'] == 1 else 'days')
    line = [SEN.get('verified_ack') or '', SEN.get('debt_intro') or '']
    line += [stmt(p) for p in ps]
    line.append((SEN.get('first_ask_multi') if many else SEN.get('first_ask_single')) or '')
    vars['debt_line'] = fill(vars, ' '.join(x for x in line if x))
    vars['enter_line'] = vars['debt_line']
    vars['account_state'] = 'ok'
    pst(vars, st)
try:
    _run(vars)
except Exception as e:
    st = gst(vars)
    st['stage'] = 'verified'
    o, r = pair(OUT.get('account_error') or OUT.get('promise_service_error'))
    set_final(vars, o, r, (SEN.get('account_error') or 'I am sorry, I cannot reach your account details right now.') + ' ' + (SEN.get('goodbye') or 'Thank you, goodbye.'))
    vars['account_state'] = 'error'
    vars['account_facts'] = '(unavailable)'
    pst(vars, st)
'''

# merges what the dialogue model's tools reported, works the persuasion ladder and words the next sentence
SYNC = r'''
def _run(vars):
    st = gst(vars)
    G = S.get('guidance') or dict()
    NL = S.get('note_lines') or dict()
    pre = []
    line = ''
    for i, r in st.get('_new') or []:
        x = NL.get(r)
        if x and x not in pre and x not in st['said']:
            pre.append(x)
    if st.get('_keys') and vars.get('stalled') != '1':
        st['stall'] = 0
    vars['stalled'] = '0'
    seen = []
    for e in st.get('_ref') or []:
        i = e[1]
        p = prod(st, i)
        if p is None or i in seen or i in st['promises'] or i in st['pnotes'] or i in st['perr'] or i in st['given']:
            continue
        st['plan'].pop(i, None)
        op = open_ids(st)
        if not op or op[0] != i:
            continue
        seen.append(i)
        if e[2] == 'full_amount_too_much':
            if i not in st['toomuch']:
                st['toomuch'].append(i)
            if i not in st['floored'] and p['floor'] < p['full'] - 0.005:
                st['floored'].append(i)
                line = str(G.get('too_much') or 'You could pay the <floor_name> of <floor>.').replace('<floor_name>', p['floor_name']).replace('<floor>', money(p['floor'])).replace('<product>', p['words'])
                continue
        used = int(st['prop'].get(i) or 0)
        if used < len(p['offers']):
            st['prop'][i] = used + 1
            line = offer_line(st, p, used)
        else:
            line = ''
            if NOTES.get('enabled') and NOTES.get('refused_reason'):
                st['pnotes'][i] = str(NOTES.get('refused_reason'))
            else:
                st['given'].append(i)
    fin = False
    if not line:
        op = open_ids(st)
        if op:
            p = prod(st, op[0])
            n = int(st['prop'].get(p['id']) or 0)
            started = len(op) < len(st['products'])
            if started and n == 0 and p['offers']:
                st['prop'][p['id']] = 1
                line = str(SEN.get('next_product') or 'Now your <product>.').replace('<product>', p['words']) + ' ' + offer_line(st, p, 0)
            elif n > 0 and p['offers']:
                line = offer_line(st, p, n - 1)
            elif started:
                line = str(SEN.get('next_product') or 'Now your <product>.').replace('<product>', p['words']) + ' ' + str(SEN.get('ask_product') or 'When can you pay it?')
            else:
                line = str((SEN.get('first_ask_multi') if len(st['products']) > 1 else SEN.get('first_ask_single')) or SEN.get('say_again') or 'I am sorry, could you say that again?')
        elif [i for i in st['plan'] if i not in st['promises']]:
            line = readback(st)
        elif st['promises']:
            line = str(SEN.get('anything_else') or 'Is there anything else?')
        else:
            fin = True
    st['said'] = st['said'] + pre
    if fin:
        if NOTES.get('enabled') or not st['given']:
            o, r = decide(st, '', '', False)
        else:
            o, r = pair(OUT.get('refused') or OUT.get('fallback_after_verification'))
        set_final(vars, o, r, ' '.join(pre + [closing_line(o, r, st['said'])]))
        st['fin'] = 'set'
        vars['sync_state'] = 'fin'
    else:
        vars['enter_line'] = fill(vars, ' '.join(pre + [line]))
        vars['sync_state'] = 'talk'
    vars['dirty'] = '0'
    pst(vars, st)
try:
    _run(vars)
except Exception as e:
    vars['dirty'] = '0'
    vars['sync_state'] = 'talk'
    vars['enter_line'] = 'I am sorry, could you say that again?'
'''

# the payment step got several customer messages in a row and no tool was called: the engine treats the last one as a non-answer
STALL = r'''
try:
    st = gst(vars)
    n = int(st.get('stall') or 0) + 1
    op = open_ids(st)
    # The first time the engine only says the question on the table again: the last message may have been an answer
    # the model failed to report, and then the customer simply repeats it. Only a second stall in a row, with nothing
    # reported in between, counts as a non-answer for the product in discussion.
    hit = n >= 2 and st['stage'] == 'verified' and bool(op)
    st['stall'] = 0 if hit else n
    pst(vars, st)
    if hit:
        emit(vars, [['refuse', op[0], 'flat_refusal']])
    vars['stalled'] = '1'
    vars['dirty'] = '1'
except Exception as e:
    vars['dirty'] = '1'
'''

# picks the next agreed promise to send to the bank, or ends the loop
REC_NEXT = r'''
try:
    st = gst(vars)
    if st.get('pend'):
        i = st['pend']
        st['tries'][i] = int(st['tries'].get(i) or 0) + 1
        if st['tries'][i] >= 2 and i not in st['perr']:
            st['perr'].append(i)
        st['pend'] = ''
    nxt = None
    for p in st['products']:
        i = p['id']
        if i in st['plan'] and i not in st['promises'] and i not in st['perr']:
            nxt = i
            break
    if nxt:
        x = st['plan'][nxt]
        vars['cur_pid'] = nxt
        vars['cur_amount'] = x['amount']
        vars['cur_date'] = x['date']
        st['pend'] = nxt
        vars['rec_state'] = 'call'
    else:
        done = [i for i in st['plan'] if i in st['promises']]
        failed = [i for i in st['plan'] if i in st['perr']]
        for i in list(st['plan'].keys()):
            st['plan'].pop(i, None)
        if failed and NOTES.get('enabled') and NOTES.get('service_error_reason'):
            for i in failed:
                st['pnotes'][i] = str(NOTES.get('service_error_reason'))
        names = dict((p['id'], p['words']) for p in st['products'])
        ok_line = SEN.get('promise_recorded') or 'Your promise is recorded.'
        bad_line = SEN.get('promise_failed') or 'I am sorry, I could not record your promise.'
        if done and not failed:
            vars['enter_line'] = fill(vars, ok_line)
            vars['rec_state'] = 'talk'
        elif done:
            vars['enter_line'] = fill(vars, ok_line + ' ' + bad_line + ' This concerns your ' + ' and your '.join(names.get(i, i) for i in failed) + '.')
            vars['rec_state'] = 'talk'
        elif failed and open_ids(st):
            vars['enter_line'] = fill(vars, bad_line)
            vars['rec_state'] = 'talk'
        elif failed:
            o, r = decide(st, '', '', False)
            set_final(vars, o, r, bad_line + ' ' + (SEN.get('goodbye') or 'Thank you, goodbye.'))
            st['fin'] = 'set'
            vars['rec_state'] = 'close'
        else:
            vars['enter_line'] = fill(vars, SEN.get('anything_else') or 'Is there anything else?')
            vars['rec_state'] = 'talk'
    vars['commit_state'] = 'idle'
    vars['dirty'] = '0'
    pst(vars, st)
except Exception as e:
    vars['rec_state'] = 'talk'
    vars['commit_state'] = 'idle'
    vars['enter_line'] = 'Thank you.'
'''

# decides how the call ends (once), then writes the notes one by one
NOTE_NEXT = r'''
try:
    st = gst(vars)
    if st.get('npend'):
        i = st['npend']
        st['ntries'][i] = int(st['ntries'].get(i) or 0) + 1
        st['npend'] = ''
    if not st.get('fin'):
        for i in list(st['plan'].keys()):
            if i not in st['promises']:
                st['plan'].pop(i, None)
        o, r = decide(st, st.get('mo'), st.get('mr'), False)
        pre = []
        NL = S.get('note_lines') or dict()
        for i, x in st.get('_new') or []:
            y = NL.get(x)
            if y and y not in pre and y not in st['said']:
                pre.append(y)
        st['said'] = st['said'] + pre
        set_final(vars, o, r, ' '.join(pre + [closing_line(o, r, st['said'])]))
        st['fin'] = 'set'
    nxt = None
    if NOTES.get('enabled') and not st['transfer'] and st['stage'] == 'verified':
        for p in st['products']:
            i = p['id']
            if i in st['pnotes'] and i not in st['notes'] and i not in st['promises'] and int(st['ntries'].get(i) or 0) < 2:
                nxt = i
                break
    if nxt:
        vars['cur_pid'] = nxt
        vars['cur_reason'] = st['pnotes'][nxt]
        st['npend'] = nxt
        vars['note_state'] = 'call'
    else:
        vars['note_state'] = 'done'
    vars['fin_state'] = 'idle'
    vars['dirty'] = '0'
    pst(vars, st)
except Exception as e:
    vars['note_state'] = 'done'
    vars['fin_state'] = 'idle'
'''

# ------------------------------------------------------------------ code tools the dialogue model calls. They check and report; they never write the state.
SET_PROMISE = r'''
st = gst(vars)
today, mins = today_of(vars)
if st['stage'] != 'verified' or not st['products']:
    raise Exception('RULE: no account is loaded. An agreement can only be noted after the security check.')
G = S.get('guidance') or dict()
pid = str(params.get('product_id') or '').strip()
ps = st['products']
ids = [p['id'] for p in ps]
allmode = False
if len(ps) == 1:
    targets = ps
elif pid.lower() in ('all', 'every', 'everything', 'both', ''):
    targets = [p for p in ps if p['id'] not in st['promises'] and p['id'] not in st['pnotes'] and p['id'] not in st['perr'] and p['id'] not in st['given']]
    allmode = True
elif pid in ids:
    targets = [p for p in ps if p['id'] == pid]
else:
    raise Exception('RULE: unknown product_id "' + pid + '". Use one of: ' + ', '.join(ids) + ', or "all".')
if not targets:
    raise Exception('RULE: there is no open product left.')
raw = str(params.get('amount') if params.get('amount') is not None else 'full').strip().lower().replace(',', '')
try:
    dt = iso(params.get('date'))
except Exception:
    raise Exception('RULE: the date must be YYYY-MM-DD. Copy the date in square brackets from the FACTS.')
evs = []
for p in targets:
    i = p['id']
    if i in st['promises']:
        if allmode:
            continue
        raise Exception('RULE: the promise for the ' + p['words'] + ' is already recorded at the bank and cannot be changed or cancelled in this call. Say: "' + (SEN.get('change_later') or 'It can be changed later.') + '"')
    if raw in ('full', 'all', 'full amount', 'total', 'whole'):
        am = p['full']
    elif raw in ('floor', 'minimum', 'min', 'smallest'):
        am = p['floor']
    else:
        am = num(re.sub(r'[^0-9.]', '', raw))
        if am is None:
            raise Exception('RULE: amount must be "full", "floor" or a number.')
        am = round(am, 2)
    if am < p['floor'] - 0.005:
        raise Exception('RULE: ' + money(am) + ' is below the floor for the ' + p['words'] + ' and cannot be recorded. Nothing was noted. ' + str(G.get('below_floor') or 'Say that this amount cannot be recorded and offer the floor of <floor> once.').replace('<floor>', money(p['floor'])).replace('<floor_name>', p['floor_name']) + ' If the customer accepts, CALL check_terms with amount "floor". If not, CALL customer_refused.')
    if am > p['full'] + 0.005:
        am = p['full']
    if dt < today:
        raise Exception('RULE: ' + say(dt) + ' is in the past. Look the day up in the FACTS.')
    dl = iso(p['deadline']) if p['deadline'] else None
    late = str(G.get('after_deadline') or 'Say that the latest date you can record is <deadline> and offer it.')
    if not isbd(dt):
        if dl is not None and dt > dl:
            raise Exception('RULE: ' + say(dt) + ' is after the deadline for the ' + p['words'] + '. Nothing was noted. ' + late.replace('<deadline>', say(dl)) + ' If the customer accepts, CALL check_terms with ' + dl.isoformat() + '. If not, CALL customer_refused.')
        nb = nextbd(dt)
        if dl is not None and nb > dl:
            nb = dl
        raise Exception('RULE: ' + say(dt) + ' is ' + why(dt) + ', not a business day. Nothing was noted. ' + str(G.get('not_business_day') or 'Offer the next business day, <next>.').replace('<next>', say(nb)) + ' If the customer accepts, CALL check_terms with ' + nb.isoformat() + '.')
    use = dt
    capped = 0
    if dl is not None and dt > dl:
        if allmode and len(targets) > 1 and any((not q['deadline']) or dt <= iso(q['deadline']) for q in targets):
            use = dl
            capped = 1
        else:
            raise Exception('RULE: ' + say(dt) + ' is after the deadline for the ' + p['words'] + '. Nothing was noted. ' + late.replace('<deadline>', say(dl)) + ' If the customer accepts, CALL check_terms with ' + dl.isoformat() + '. If not, CALL customer_refused.')
    evs.append(['plan', i, am, use.isoformat(), capped, 1 if allmode else 0])
if not evs:
    raise Exception('RULE: there is no open product left.')
emit(vars, evs)
'''

SET_NOTE = r'''
st = gst(vars)
if st['stage'] != 'verified' or not st['products']:
    raise Exception('RULE: no account is loaded. This tool is for after the security check.')
if not NOTES.get('enabled'):
    raise Exception('RULE: this tool is not used on this call. To end the call, CALL wrap_up.')
pid = str(params.get('product_id') or '').strip()
reason = str(params.get('reason') or '').strip()
allowed = NOTES.get('reasons') or []
if allowed and reason not in allowed:
    raise Exception('RULE: reason must be one of: ' + ', '.join(allowed) + '.')
ps = st['products']
ids = [p['id'] for p in ps]
if len(ps) == 1:
    targets = ps
elif pid.lower() in ('all', 'every', 'everything', 'both', ''):
    targets = [p for p in ps if p['id'] not in st['promises'] and p['id'] not in st['plan'] and p['id'] not in st['pnotes']]
elif pid in ids:
    targets = [p for p in ps if p['id'] == pid]
else:
    raise Exception('RULE: unknown product_id "' + pid + '". Use one of: ' + ', '.join(ids) + ', or "all".')
evs = []
for p in targets:
    if p['id'] in st['promises']:
        if len(targets) == 1:
            raise Exception('RULE: the ' + p['words'] + ' already has a recorded promise, so it cannot be settled without one.')
        continue
    evs.append(['note', p['id'], reason])
if not evs:
    raise Exception('RULE: there is no open product left.')
emit(vars, evs)
'''

REFUSAL = r'''
st = gst(vars)
if st['stage'] != 'verified' or not st['products']:
    raise Exception('RULE: no account is loaded yet.')
ps = st['products']
ids = [p['id'] for p in ps]
pid = str(params.get('product_id') or '').strip()
op = open_ids(st)
if len(ps) == 1:
    pid = ids[0]
elif pid not in ids or (pid not in op and pid not in st['plan']):
    pid = op[0] if op else ''
p = prod(st, pid)
if p is None or pid in st['promises']:
    raise Exception('RULE: there is no open product to refuse. Look at CALL STATE.')
if pid in st['pnotes'] or pid in st['perr'] or pid in st['given']:
    raise Exception('RULE: the ' + p['words'] + ' is already settled without a promise. Make no further offer for it.')
kind = str(params.get('kind') or 'flat_refusal').strip()
emit(vars, [['refuse', pid, kind if kind == 'full_amount_too_much' else 'flat_refusal']])
'''

CONFIRM = r'''
st = gst(vars)
todo = [i for i in st['plan'] if i not in st['promises']]
if st['stage'] != 'verified' or not todo:
    raise Exception('RULE: nothing is agreed yet, so there is nothing to record. First CALL check_terms for each product the customer agreed to pay. The system then reads it back. Only after a clear yes CALL customer_confirmed.')
vars['commit_state'] = 'go'
'''

FINISH = r'''
st = gst(vars)
mo = str(params.get('outcome') or '').strip()
mr = str(params.get('reason') or '').strip()
evs = []
if st['stage'] == 'verified' and st['products']:
    planned = [i for i in st['plan'] if i not in st['promises']]
    PR = pair(OUT.get('promise_recorded'))[0]
    if planned and mo == PR:
        raise Exception('RULE: the agreed promise is not recorded yet. If the customer gave a clear yes to the read-back, CALL customer_confirmed now. If not, wait for their answer.')
    for i in planned:
        st['plan'].pop(i, None)
    if NOTES.get('enabled'):
        op = open_ids(st)
        if op:
            allowed = NOTES.get('reasons') or []
            guess = mr if mr in allowed else ((NOTES.get('reason_for_outcome') or dict()).get(mo) or '')
            if guess:
                for i in op:
                    st['pnotes'][i] = guess
                    evs.append(['note', i, guess])
            else:
                names = dict((p['id'], p['words']) for p in st['products'])
                raise Exception('RULE: before the call can end, every product needs a recorded promise or a reason for having none. CALL skip_product for: ' + ', '.join(names[i] + ' [' + i + ']' for i in op) + ' with one of the reasons: ' + ', '.join(allowed) + '.')
decide(st, mo, mr, True)
emit(vars, evs + [['finish', mo, mr]])
vars['fin_state'] = 'go'
'''

# ------------------------------------------------------------------ hooks on the bank's tools
VERIFY_PRE = r'''
st = gst(vars)
if st['id'] == 'failed':
    raise Exception('RULE: the security check is over. Do not ask again.')
if st['stage'] == 'verified':
    raise Exception('RULE: identity is already verified. Do not ask security questions again.')
try:
    A = (S.get('tools') or dict()).get('verify_identity') or dict()
    fq = A.get('question') or 'field'
    fa = A.get('answer') or 'answer'
    b = body_of(config)
    kind = ''
    tf = []
    for q in (S.get('identity') or dict()).get('questions') or []:
        if q.get('field') == b.get(fq):
            kind = q.get('kind') or ''
            tf = q.get('transform') or []
    a = str(b.get(fa) or '').strip()
    if 'remove_spaces' in tf:
        a = re.sub(r'\s+', '', a)
    if 'uppercase' in tf:
        a = a.upper()
    if 'lowercase' in tf:
        a = a.lower()
    if tf:
        b[fa] = a
    if kind == 'digits':
        dg = re.sub(r'\D', '', a)
        if dg:
            b[fa] = dg
    elif kind == 'date' and not re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', a):
        low = a.lower()
        mon = None
        for i in range(12):
            if re.search(r'\b' + MO[i][:3].lower(), low):
                mon = i + 1
        nums = re.findall(r'\d+', low)
        y = dd = None
        if mon and len(nums) == 2:
            for n in nums:
                if len(n) == 4:
                    y = int(n)
                else:
                    dd = int(n)
        elif not mon and len(nums) == 3 and not re.search(r'[a-z]', low):
            order = str((S.get('identity') or dict()).get('numeric_date_order') or 'DMY')
            if len(nums[0]) == 4:
                y, mon, dd = int(nums[0]), int(nums[1]), int(nums[2])
            elif order == 'MDY':
                mon, dd, y = int(nums[0]), int(nums[1]), int(nums[2])
            else:
                dd, mon, y = int(nums[0]), int(nums[1]), int(nums[2])
        if y and mon and dd:
            b[fa] = '%04d-%02d-%02d' % (y, mon, dd)
    elif kind == 'date':
        p3 = a.split('-')
        b[fa] = '%04d-%02d-%02d' % (int(p3[0]), int(p3[1]), int(p3[2]))
    vars['cur_question'] = str(b.get(fq) or '')
except Exception:
    pass
'''

VERIFY_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    I = S.get('identity') or dict()
    R = I.get('response') or dict()
    qs = I.get('questions') or []
    asked = str(vars.get('cur_question') or '')
    def flag(k, dflt):
        x = d.get(R.get(k) or dflt)
        return x is True or str(x).lower() == 'true'
    left = d.get(R.get('left') or 'wrong_answers_left')
    hint = str(d.get(R.get('hint') or 'hint') or '')
    def ask_of(f):
        for q in qs:
            if q.get('field') == f:
                return str(q.get('ask') or '')
        return ''
    if flag('verified', 'verified') and asked and asked not in st['idv']:
        st['idv'].append(asked)
    todo = [q.get('field') for q in qs if q.get('field') not in st['idv']]
    if flag('all_verified', 'all_verified') or (qs and not todo and flag('verified', 'verified')):
        st['id'] = 'verified'
        d['id_state'] = 'verified'
        d['what_to_do_next'] = 'All security answers are correct. Identity is verified. Say nothing about it yet.'
    elif hint and hint in (I.get('hints') or dict()):
        d['id_state'] = 'open'
        d['what_to_do_next'] = str((I.get('hints') or dict()).get(hint)) + ' Then CALL verify_identity with the new answer.'
    elif flag('verified', 'verified'):
        d['id_state'] = 'open'
        d['what_to_do_next'] = 'Correct (do not say so). Say "Thank you." and ask the next security question: "' + ask_of(todo[0] if todo else '') + '"'
    elif d.get(R.get('verified') or 'verified') is not None and str(left) == '0':
        st['id'] = 'failed'
        d['id_state'] = 'failed'
        d['what_to_do_next'] = 'The security check has failed and is over. Do not ask again and say nothing about the account.'
        o, r = pair(OUT.get('identity_failed'))
        d['final_outcome'] = o
        d['final_reason'] = r
        d['final_line'] = SEN.get('identity_failed') or closing_line(o, r)
        set_final(vars, o, r, d['final_line'])
    elif d.get(R.get('verified') or 'verified') is not None and good(result, d):
        d['id_state'] = 'open'
        d['what_to_do_next'] = 'That answer is WRONG. Do not go on to the next question. Say: "' + (I.get('wrong_sentence') or 'I am sorry, that does not match our records.') + '" and ask the SAME question once more: "' + ask_of(asked) + '" Never say which part was wrong.' + (' Wrong answers left: ' + str(left) + '.' if left is not None else '')
    else:
        d['id_state'] = 'open'
        d['what_to_do_next'] = 'The service could not read this answer. It does NOT count as a wrong answer. If the format was wrong, send it again in the right format; otherwise ask the customer to repeat the answer and CALL verify_identity again.'
    vars['id_state'] = d['id_state']
    pst(vars, st)
except Exception:
    pass
'''

CALLBACK_PRE = r'''
st = gst(vars)
if st['stage'] == 'verified' or st['idv']:
    raise Exception('RULE: a callback is only for someone else who answered the phone, not for the customer.')
A = (S.get('tools') or dict()).get('schedule_callback') or dict()
b = body_of(config)
try:
    today, mins = today_of(vars)
    slots = cb_slots(today, mins)
except Exception:
    today, mins, slots = None, 0, None
def allowed_text():
    return '; '.join(say(d) + ' from ' + hm(a) + ' to ' + hm(c) for d, a, c in slots) or 'none'
try:
    dt = iso(b.get(A.get('date') or 'date'))
except Exception:
    dt = None
try:
    tm = mins_of(b.get(A.get('time') or 'time'))
except Exception:
    tm = None
if slots is not None:
    if dt is None:
        raise Exception('RULE: nothing was booked. Ask on which day the customer can be reached, then CALL schedule_callback with that day as YYYY-MM-DD.')
    day_ok = any(d == dt for d, a, c in slots)
    if day_ok and tm is None:
        raise Exception('RULE: nothing was booked. ' + say(dt) + ' is possible, but a clock time is missing. Ask at what time on that day, then CALL schedule_callback again with the time as HH:MM (24 hour).')
    if not day_ok or not any(d == dt and a <= tm <= c for d, a, c in slots):
        n = int(st.get('cb_bad') or 0) + 1
        st['cb_bad'] = n
        pst(vars, st)
        G = (S.get('guidance') or dict())
        what = say(dt) + (' at ' + hm(tm) if tm is not None else '')
        if n == 1:
            raise Exception('RULE: ' + what + ' is OUTSIDE the callback window. Nothing was booked. Allowed: ' + allowed_text() + '. ' + G.get('callback_outside_first', 'Ask once for another time.'))
        raise Exception('RULE: ' + what + ' is again OUTSIDE the callback window. Nothing was booked. ' + G.get('callback_outside_second', 'Do not schedule a callback. End the call.'))
if slots is not None:
    b[A.get('time') or 'time'] = hm(tm)
    b[A.get('date') or 'date'] = dt.isoformat()
'''

CALLBACK_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    if good(result, d):
        st['callback'] = 'booked'
        o, r = pair(OUT.get('callback_booked'))
        d['auto_state'] = 'go'
        d['final_outcome'] = o
        d['final_reason'] = r
        d['final_line'] = SEN.get('after_callback') or closing_line(o, r)
        set_final(vars, o, r, d['final_line'])
        vars['auto_state'] = 'go'
        d['what_to_do_next'] = 'The callback is booked. Say nothing more.'
    else:
        n = int(st.get('cb_fail') or 0) + 1
        st['cb_fail'] = n
        d['what_to_do_next'] = 'The callback was NOT booked. Do not say it is booked. ' + ('CALL schedule_callback once more with the same date and time.' if n < 2 else 'Do not try again. Say that you could not book the callback and CALL wrap_up.')
    pst(vars, st)
except Exception:
    pass
'''

TRANSFER_PRE = r'''
st = gst(vars)
A = (S.get('tools') or dict()).get('transfer_to_agent') or dict()
b = body_of(config)
fq = A.get('queue') or 'queue'
TR = S.get('transfer') or dict()
if st['stage'] != 'verified':
    pre = TR.get('before_verification') or []
    if pre and b.get(fq) not in pre:
        if len(pre) == 1:
            b[fq] = pre[0]
        else:
            raise Exception('RULE: before the security check only these queues are possible: ' + ', '.join(pre) + '.')
vars['cur_queue'] = str(b.get(fq) or '')
'''

TRANSFER_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    q = str(vars.get('cur_queue') or '')
    if good(result, d):
        st['transfer'] = q or 'done'
        for i in list(st['plan'].keys()):
            st['plan'].pop(i, None)
        o, r = pair((OUT.get('transfer') or dict()).get(q))
        d['auto_state'] = 'go'
        d['final_outcome'] = o
        d['final_reason'] = r
        d['final_line'] = SEN.get('after_transfer') or closing_line(o, r)
        set_final(vars, o, r, d['final_line'])
        vars['auto_state'] = 'go'
        d['what_to_do_next'] = 'The transfer is arranged. Say nothing more.'
    else:
        n = int(st.get('tr_fail') or 0) + 1
        st['tr_fail'] = n
        d['what_to_do_next'] = 'The transfer did NOT work. Do not say you are connecting them. ' + ('CALL transfer_to_agent once more with the same queue.' if n < 2 else 'Do not try again. Say that you could not connect them right now and go on as your rules say.')
    pst(vars, st)
except Exception:
    pass
'''

ACCOUNT_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    f = ((S.get('product') or dict()).get('list_field')) or 'products'
    if isinstance(d.get(f), list):
        vars['products_json'] = json.dumps(d.get(f))
except Exception:
    pass
'''

# engine-run bank calls: the values were checked when they were noted, the hooks only keep the books
PROMISE_PRE = r'''
try:
    A = (S.get('tools') or dict()).get('create_promise') or dict()
    b = body_of(config)
    fa = A.get('amount') or 'amount'
    b[fa] = round(float(b.get(fa)), 2)
except Exception:
    pass
'''

PROMISE_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    i = st.get('pend') or str(vars.get('cur_pid') or '')
    if good(result, d) or 'already' in str(d.get('error') or ''):
        st['promises'][i] = dict(st['plan'].get(i) or dict(amount=vars.get('cur_amount'), date=vars.get('cur_date')))
        st['pend'] = ''
    pst(vars, st)
except Exception:
    pass
'''

NOTE_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    i = st.get('npend') or str(vars.get('cur_pid') or '')
    if good(result, d):
        st['notes'][i] = str(vars.get('cur_reason') or '')
        st['npend'] = ''
    pst(vars, st)
except Exception:
    pass
'''

CLOSE_PRE = r'''
try:
    A = (S.get('tools') or dict()).get('close_call') or dict()
    b = body_of(config)
    fr = A.get('reason') or 'reason'
    if not str(b.get(fr) or '').strip() or LB in str(b.get(fr)):
        b.pop(fr, None)
except Exception:
    pass
'''

CLOSE_POST = r'''
try:
    result.pop('header', None)
    d = data_of(result)
    st = gst(vars)
    if good(result, d) or 'already closed' in str(d.get('error') or ''):
        st['closed'] = 'yes'
    pst(vars, st)
except Exception:
    pass
'''

# safety net at the end of every call: closes it from the books if the normal path did not
FALLBACK_PRE = r'''
st = gst(vars)
if st['closed'] == 'yes':
    raise Exception('already closed')
A = (S.get('tools') or dict()).get('close_call') or dict()
b = body_of(config)
fo = A.get('outcome') or 'outcome'
fr = A.get('reason') or 'reason'
mo = str(b.get(fo) or '')
mr = str(b.get(fr) or '')
if LB in mo:
    mo = ''
if LB in mr:
    mr = ''
if str(vars.get('final_outcome') or '') and (st['transfer'] or st['callback'] or st['id'] == 'failed' or st['promises']):
    o, r = str(vars.get('final_outcome')), str(vars.get('final_reason') or '')
    if st['promises'] and not st['transfer']:
        o, r = pair(OUT.get('promise_recorded'))
else:
    o, r = decide(st, mo, mr, False)
b[fo] = o
if r:
    b[fr] = r
else:
    b.pop(fr, None)
'''

CORE_KEYS = ["now_variable", "calendar", "sentences", "closing_lines", "outcomes", "notes", "response", "tools"]
# snippet: (source, helper sections besides core, spec keys besides CORE_KEYS)
ALL = dict(
    SETUP=(SETUP, ["cal", "live"], ["callback"]), PREPARE=(PREPARE, ["cal", "terms", "live"], ["product", "bands", "attempt_offers", "dates"]),
    SYNC=(SYNC, ["live", "decide"], ["guidance", "note_lines"]), STALL=(STALL, [], []), REC_NEXT=(REC_NEXT, ["live", "decide"], []), NOTE_NEXT=(NOTE_NEXT, ["live", "decide"], ["note_lines"]),
    SET_PROMISE=(SET_PROMISE, [], ["guidance"]), SET_NOTE=(SET_NOTE, [], []), REFUSAL=(REFUSAL, [], []), CONFIRM=(CONFIRM, [], []), FINISH=(FINISH, ["decide"], []),
    VERIFY_PRE=(VERIFY_PRE, [], ["identity"]), VERIFY_POST=(VERIFY_POST, ["live"], ["identity"]),
    CALLBACK_PRE=(CALLBACK_PRE, ["cal"], ["callback", "guidance"]), CALLBACK_POST=(CALLBACK_POST, [], []),
    TRANSFER_PRE=(TRANSFER_PRE, [], ["transfer"]), TRANSFER_POST=(TRANSFER_POST, ["live"], []), ACCOUNT_POST=(ACCOUNT_POST, [], ["product"]),
    PROMISE_PRE=(PROMISE_PRE, [], []), PROMISE_POST=(PROMISE_POST, ["live"], []), NOTE_POST=(NOTE_POST, [], []),
    CLOSE_PRE=(CLOSE_PRE, [], []), CLOSE_POST=(CLOSE_POST, [], []), FALLBACK_PRE=(FALLBACK_PRE, ["decide"], []))

def sections():
    out, cur = [], "core"
    for line in LIB.split("\n"):
        if line.startswith("#@"): cur = line[2:].strip(); continue
        out.append((cur, line))
    return out

def embed(spec):
    """The source of every snippet: the helpers it needs and its part of the spec, as JSON text. Fails on double braces."""
    import json, re
    lines, out = sections(), {}
    for name, (body, libs, keys) in ALL.items():
        sub = {k: spec[k] for k in CORE_KEYS + keys if k in spec}
        text = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"<<\1>>", json.dumps(sub, separators=(",", ":"), ensure_ascii=True))
        while "}}" in text: text = text.replace("}}", "} }")
        while "{{" in text: text = text.replace("{{", "{ {")
        lib = "\n".join(l for sec, l in lines if sec == "core" or sec in libs)
        code = "SPEC_TEXT = " + repr(text) + "\n" + lib + "\n" + body
        if "{{" in code or "}}" in code: raise ValueError("double braces in " + name)
        compile(code, name, "exec")
        out[name] = code
    return out
