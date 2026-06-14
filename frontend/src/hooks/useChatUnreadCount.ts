import { useEffect, useRef } from "react";
import { chat } from "@/api/endpoints";
import { useUserPush } from "@/store/userPush";

export function useChatUnreadCount() {
  const { chatUnreadCount, setChatUnreadCount } = useUserPush();
  const initialized = useRef(false);

  // Fetch the accurate count once on mount; WebSocket increments handle updates.
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    chat.listRooms().then((rooms) => {
      const total = rooms.reduce((sum, r) => sum + r.unread_count, 0);
      setChatUnreadCount(total);
    }).catch(() => {});
  }, [setChatUnreadCount]);

  return chatUnreadCount;
}
