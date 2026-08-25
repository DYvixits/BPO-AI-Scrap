import { useEffect, useRef, useState } from "react";

import { WS_BASE_URL } from "@/services/api";
import { useAuthStore } from "@/stores/authStore";
import type { ResearchEvent } from "@/types/api";

/** Live progress feed for one research job over the WebSocket the backend
 * exposes at /research/{id}/ws. Falls back gracefully — if the socket never
 * connects (e.g. worker/redis not running in this environment), the page
 * still works via polling in the page component; this hook only adds the
 * "arrives instantly" behavior on top. */
export function useResearchEvents(jobId: string | undefined) {
  const [events, setEvents] = useState<ResearchEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const accessToken = useAuthStore((s) => s.accessToken);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId || !accessToken) return undefined;

    const socket = new WebSocket(`${WS_BASE_URL}/research/${jobId}/ws?token=${accessToken}`);
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (message) => {
      try {
        const parsed = JSON.parse(message.data) as { kind: string; payload: Record<string, unknown> };
        setEvents((prev) => [...prev, { kind: parsed.kind, payload: parsed.payload, created_at: new Date().toISOString() }]);
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [jobId, accessToken]);

  return { events, connected };
}
