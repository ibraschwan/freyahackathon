// The bank's seven statement services for the final case, as the service contract of 1 October 2026 describes them
// (POST <base>/voice/v1/<service>, request {data, call}, response {data, result}), answered from the bank's own list of
// test customers: status code and body exactly as test-environment/test-customers.json lists them.
import pack from "./test-customers.json";

const SERVICES = ["cards.list", "cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change", "contact.email.get", "statement.pdf.send"];
const BY_CUSTOMER = new Map(pack.customers.map((c) => [String(c.customerNo), c.services]));
const BY_CARD = new Map();                              // service -> card number as cards.list gives it -> entry
for (const c of pack.customers)
  for (const svc of ["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"])
    for (const [card, node] of Object.entries(c.services[svc] || {})) { if (!BY_CARD.has(svc)) BY_CARD.set(svc, new Map()); BY_CARD.get(svc).set(card, node); }

// the 404 the contract gives a service (section 4); a service without one answers 400 INVALID_ARGUMENTS_ERROR (section 6)
const NOT_FOUND = {
  "cards.list": ["FB_IVR_CHANNEL_102", "Müşteriye ait geçerli kart bilgisi bulunamadı."],
  "cards.balance": ["FB_IVR_CHANNEL_120", "Kart bakiye servisi hatası: kart bulunamadı"],
  "statement.week.get": ["FB_IVR_CHANNEL_121", "Kart bulunamadı"],
  "statement.pdf.send": ["FB_IVR_CHANNEL_107", "Pdf dokümanı bulunamadı"],
};

function error(http, code, text, type, rootCause) {
  const guid = crypto.randomUUID().replace(/-/g, "");
  return { status: http, json: { result: { guid, returnCode: code, messageText: text, code, message: text, type, details: { guid, rootCause, errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } } };
}
const invalid = (text) => error(400, "INVALID_ARGUMENTS_ERROR", text, "ERROR", "InvalidArgumentsException");
const missing = (svc, what) => (NOT_FOUND[svc] ? error(404, NOT_FOUND[svc][0], NOT_FOUND[svc][1], "WARNING", "NotFoundException") : invalid(what + " is not valid"));
const given = (v) => v !== undefined && v !== null && String(v).trim() !== "";

export function serviceOf(path) {
  const p = path.replace(/^\/+|\/+$/g, "");
  return SERVICES.find((s) => p === "voice/v1/" + s || p === s) || null;
}

export async function handle(path, body) {
  const svc = serviceOf(path);
  if (!svc) return { status: 404, json: { error: "no such service: " + path } };
  const data = body && typeof body.data === "object" && body.data !== null ? body.data : {};
  let node;
  if (svc === "cards.list" || svc === "contact.email.get" || svc === "statement.pdf.send") {
    if (!given(data.customerNo)) return invalid("customerNo cannot be empty");
    if (svc === "contact.email.get" && !given(data.intAddressInfoType)) return invalid("intAddressInfoType cannot be empty");
    if (svc === "statement.pdf.send") for (const f of ["cardNumber", "currencyType", "statementDate", "emailAddress"]) if (!given(data[f])) return invalid((f === "cardNumber" ? "card number" : f) + " cannot be empty");
    node = (BY_CUSTOMER.get(String(data.customerNo).trim()) || {})[svc];
    if (!node) return missing(svc, "customerNo");
  } else {
    if (!given(data.cardNumber)) return invalid("card number cannot be empty");
    node = (BY_CARD.get(svc) || new Map()).get(String(data.cardNumber).trim());
    if (!node) return missing(svc, "cardNumber");
    if (svc === "statement.week.decide" || svc === "statement.week.change") {
      if (!given(data.newStatementWeek)) return invalid("newStatementWeek cannot be empty");
      if (!given(data.statementDay)) return invalid("statementDay cannot be empty");
      node = node[String(data.newStatementWeek).trim()];
      if (!node) return missing(svc, "newStatementWeek");           // the card's current week, or a week that does not exist
    }
  }
  if (Number(node.delaySeconds) > 0) await new Promise((r) => setTimeout(r, Number(node.delaySeconds) * 1000));
  return { status: node.http, json: node.response };
}
