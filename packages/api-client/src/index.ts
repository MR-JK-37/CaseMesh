import createClient from "openapi-fetch";
import type { paths } from "./schema";

/**
 * Section 10: one generated TypeScript client from the backend's real
 * OpenAPI schema (src/schema.ts, regenerated via `pnpm generate` against
 * a running backend — never hand-written endpoint bindings).
 *
 * `credentials: "include"` sends the HttpOnly session cookies (Section
 * 7.4) on every request. CSRF: the backend's double-submit cookie
 * (`icm_csrf`, readable by JS) is echoed back as `X-CSRF-Token` on every
 * state-changing request — enforced here in one place so callers never
 * have to remember it.
 */
function readCsrfCookie(): string | undefined {
  if (typeof document === "undefined") return undefined;
  const match = document.cookie.match(/(?:^|; )icm_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : undefined;
}

export function createApiClient(baseUrl: string) {
  const client = createClient<paths>({ baseUrl, credentials: "include" });

  client.use({
    onRequest({ request }) {
      if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
        const csrf = readCsrfCookie();
        if (csrf) request.headers.set("X-CSRF-Token", csrf);
      }
      return request;
    },
  });

  return client;
}

export type { paths };
