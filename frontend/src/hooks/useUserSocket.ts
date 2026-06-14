import { useEffect } from "react";
import { WS_URL } from "@/api/client";
import { useUserPush } from "@/store/userPush";

export function useUserSocket(token: string | null) {
  const { setNotificationUnreadCount, incrementNotificationCount, incrementChatCount } =
    useUserPush();

  useEffect(() => {
    if (!token) return;

    const ws = new WebSocket(
      `${WS_URL}/ws/user?token=${encodeURIComponent(token)}`
    );

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === "init") {
          setNotificationUnreadCount(data.notification_unread ?? 0);
        } else if (data.type === "new_notification") {
          incrementNotificationCount();
        } else if (data.type === "new_chat_message") {
          // Skip badge increment while the user is on the chat page — they are
          // already seeing the conversation, so the nav badge should stay at 0.
          if (!useUserPush.getState().onChatPage) {
            incrementChatCount();
          }
        }
      } catch {
        /* ignore malformed frames */
      }
    };

    return () => ws.close();
  }, [token, setNotificationUnreadCount, incrementNotificationCount, incrementChatCount]);
}
