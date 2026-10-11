// Mock of Freya Bank's statement services for the final case (see bank.js). Stateless: every answer comes from the
// bank's list of test customers. The last requests are kept in one Durable Object, only so that we can see what the
// phone agent sent; nothing an answer depends on is stored.
import { handle, serviceOf } from "./bank.js";

export class Bank {
  constructor(state) { this.state = state; }
  async fetch(request) {
    const store = this.state.storage;
    const log = (await store.get("log")) || [];
    if (request.method === "GET") return Response.json({ calls: log.slice(-80) });
    log.push(await request.json());
    await store.put("log", log.slice(-300));
    return Response.json({ ok: true });
  }
}

const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8" } });

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const log = env.BANK.get(env.BANK.idFromName("log"));
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) return json(200, { ok: true, service: "Freya Bank statement services (test environment mock)" });
    if (request.method === "GET" && url.pathname === "/_calls") return log.fetch("https://log/");
    if (url.pathname === "/oauth2/token") return json(200, { access_token: "test-environment-token", token_type: "Bearer", expires_in: 1800 });   // the test environment does not check it
    if (!serviceOf(url.pathname)) return json(404, { error: "no such service: " + url.pathname });
    if (request.method !== "POST") return json(405, { error: "every service is POST" });
    let body;
    try { body = await request.json(); } catch (e) { body = null; }
    if (body === null || typeof body !== "object") return json(400, { result: { guid: null, returnCode: "INVALID_ARGUMENTS_ERROR", messageText: "request body must be JSON", code: "INVALID_ARGUMENTS_ERROR", message: "request body must be JSON", type: "ERROR", details: { guid: null, rootCause: "InvalidArgumentsException", errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } });
    const out = await handle(url.pathname, body);
    ctx.waitUntil(log.fetch("https://log/", { method: "POST", body: JSON.stringify({ at: new Date().toISOString(), path: url.pathname, data: body.data, status: out.status, code: (out.json.result || {}).returnCode }) }).catch(() => {}));
    return json(out.status, out.json);
  },
};
