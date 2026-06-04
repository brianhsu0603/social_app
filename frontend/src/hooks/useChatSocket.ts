import { useEffect, useRef, useState } from "react";
import { WS_URL } from "@/api/client";
import type { ChatMessage } from "@/types";

export interface TypingUser {
  user_id: number;
  timestamp: number;
}

export function useChatSocket(
  roomId: number | null,
  onMessage: (m: ChatMessage) => void,
  onTyping?: (users: TypingUser[]) => void
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [ready, setReady] = useState(false);
  const typingTimeoutRef = useRef<NodeJS.Timeout>();

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
        const data = JSON.parse(e.data);
        if (data.type === "typing") {
          // Handle typing event
          if (onTyping) {
            onTyping([{ user_id: data.user_id, timestamp: Date.now() }]);
          }
        } else {
          // Handle regular message
          onMessage(data as ChatMessage);
        }
      } catch {
        /* ignore malformed frames */
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [roomId, onMessage, onTyping]);

  function send(content: string, media?: { url: string; media_type: "image" | "video" }) {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(
      JSON.stringify({
        type: "message",
        content,
        media_url: media?.url ?? null,
        media_type: media?.media_type ?? null,
      }),
    );
    return true;
  }

  function sendTyping() {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: "typing" }));
    return true;
  }

  return { ready, send, sendTyping };
}
