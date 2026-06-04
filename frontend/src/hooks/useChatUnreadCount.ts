import { useEffect, useState } from "react";
import { chat } from "@/api/endpoints";

export function useChatUnreadCount() {
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    const fetchUnreadCount = async () => {
      try {
        const rooms = await chat.listRooms();
        const total = rooms.reduce((sum, room) => sum + room.unread_count, 0);
        setUnreadCount(total);
      } catch (error) {
        console.error("Failed to fetch unread count:", error);
      }
    };

    fetchUnreadCount();
    // Poll every 5 seconds for unread counts
    const interval = setInterval(fetchUnreadCount, 5000);
    return () => clearInterval(interval);
  }, []);

  return unreadCount;
}
