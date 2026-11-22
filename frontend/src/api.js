// Thin client for the FastAPI backend. One function per endpoint.
const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request(path, options = {}) {
  // Spread options first so its `headers` can't replace the merged headers below
  // (losing Content-Type makes fetch send text/plain, which FastAPI rejects with 422).
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  listEntities: () => request("/entities"),
  listLabJobs: () => request("/lab-jobs"),
  pedigree: (id, depth = 5) => request(`/entities/${id}/pedigree?depth=${depth}`),
  // A fresh Idempotency-Key per submit; a network retry of the same submit reuses it.
  createEntity: (entity, idempotencyKey = crypto.randomUUID()) =>
    request("/entities", {
      method: "POST",
      body: JSON.stringify(entity),
      headers: { "Idempotency-Key": idempotencyKey },
    }),
};
