// The services themselves. Filled in from the service contract of the final case.
export async function handle(path, body, customer, rec) {
  return { status: 404, json: { ok: false, error: "unknown service " + path } };
}
