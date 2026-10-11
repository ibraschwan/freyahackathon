// Mock of the bank's services for the final case. One Durable Object per customer keeps that customer's records,
// so every request about a customer sees what the earlier ones wrote.
import { handle } from "./bank.js";

export class Bank {
  constructor(state) { this.state = state; }
  async fetch(request) {
    const { path, body, customer } = await request.json();
    const store = this.state.storage;
    const rec = (await store.get("rec")) || { calls: [] };
    const out = await handle(path, body, customer, rec);
    rec.calls.push({ at: new Date().toISOString(), path, body, status: out.status, result: out.json });
    await store.put("rec", rec);
    return Response.json(out.json, { status: out.status });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) return Response.json({ ok: true, service: "bank mock" });
    let body = {};
    if (request.method !== "GET") { try { body = await request.json(); } catch (e) { return Response.json({ ok: false, error: "the body is not JSON" }, { status: 400 }); } }
    else body = Object.fromEntries(url.searchParams);
    const customer = String(body.customer_id || body.customerId || url.searchParams.get("customer_id") || "unknown");
    const stub = env.BANK.get(env.BANK.idFromName(customer));
    return stub.fetch("https://bank/", { method: "POST", body: JSON.stringify({ path: url.pathname, body, customer }) });
  },
};
