import { useEffect, useState } from "react";
import { api } from "./api";
import { useAuth } from "./AuthContext";

interface RealtimeEvent {
  id: string;
  channel: string;
  event_type: string;
  payload: Record<string, unknown>;
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Section 6.4's SSE fallback, consumed from the browser (Section 9.7's
 * real-time toast). Deliberately minimal: one ticket, one EventSource,
 * no reconnect-with-backoff loop yet (Section 6.4(b)'s jittered
 * backoff is unbuilt — see docs/limitations.md) — this is enough to
 * demonstrate the real pipeline end to end in the UI, not the full
 * resilience story. */
export function useRealtimeToast() {
  const { user } = useAuth();
  const [latest, setLatest] = useState<RealtimeEvent | null>(null);

  useEffect(() => {
    if (!user) return;
    let source: EventSource | null = null;
    let cancelled = false;

    (async () => {
      const { data } = await api.POST("/api/v1/realtime/ticket", {});
      if (cancelled || !data) return;
      source = new EventSource(`${API_BASE}/api/v1/realtime/sse?ticket=${data.ticket}`);
      source.addEventListener("alert_raised", (e) => {
        const parsed = JSON.parse((e as MessageEvent).data) as RealtimeEvent;
        setLatest(parsed);
      });
      source.addEventListener("case_updated", (e) => {
        const parsed = JSON.parse((e as MessageEvent).data) as RealtimeEvent;
        setLatest(parsed);
      });
    })();

    return () => {
      cancelled = true;
      source?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.userId]);

  return latest;
}
