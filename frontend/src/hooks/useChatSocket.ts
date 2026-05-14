import { useEffect, useRef, useState } from "react";
import { WS_URL } from "@/api/client";
import type { ChatMessage } from "@/types";

export function useChatSocket(roomId: number | null, onMessage: (m: ChatMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (roomId == null) return;
    const token = localStorage.getItem("token");
    if (!token) return;

    const url = `${WS_URL}/chat/ws/${roomId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setReady(true);
    ws.onclose = () => setReady(false);
    ws.onerror = () => setReady(false);
    ws.onmessage = (e) => {
      try {
        onMessage(JSON.parse(e.data) as ChatMessage);
      } catch {
        /* ignore malformed frames */
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [roomId, onMessage]);

  function send(content: string, media?: { url: string; media_type: "image" | "video" }) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(
      JSON.stringify({
        content,
        media_url: media?.url ?? null,
        media_type: media?.media_type ?? null,
      }),
    );
    return true;
  }

  return { ready, send };
}
