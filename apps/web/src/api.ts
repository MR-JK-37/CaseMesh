import { createApiClient } from "@icm/api-client";

// baseUrl has no /api/v1 suffix: the generated paths (from the backend's
// real OpenAPI schema) already include it, since FastAPI registers every
// router with that prefix. A baseUrl that also had it would silently
// double it (http://.../api/v1/api/v1/...), a real 404 caught while
// driving the sign-in flow end-to-end, not anticipated in advance.
export const api = createApiClient(import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000");
