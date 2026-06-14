import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { notifications as notificationsApi } from "@/api/endpoints";
import { useUserPush } from "@/store/userPush";
import type { Notification } from "@/types";

export function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const { notificationUnreadCount, setNotificationUnreadCount } = useUserPush();

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await notificationsApi.list();
      setItems(data.notifications);
      setNotificationUnreadCount(data.unread_count);
    } catch {
      // ignore — fail silently on network errors
    }
  }, [setNotificationUnreadCount]);

  // Fetch once on mount for the initial list + accurate count.
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Refetch the list whenever a new notification is pushed via WebSocket.
  const prevCountRef = useRef(notificationUnreadCount);
  useEffect(() => {
    if (notificationUnreadCount > prevCountRef.current) {
      fetchNotifications();
    }
    prevCountRef.current = notificationUnreadCount;
  }, [notificationUnreadCount, fetchNotifications]);

  // Close dropdown when clicking outside.
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleOpen = () => {
    setOpen((prev) => {
      if (!prev) fetchNotifications(); // always fetch fresh list on open
      return !prev;
    });
  };

  const handleMarkAllRead = async () => {
    await notificationsApi.markAllRead();
    setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    setNotificationUnreadCount(0);
  };

  const handleNotificationClick = async (n: Notification) => {
    if (!n.read) {
      try {
        await notificationsApi.markOneRead(n.id);
        setItems((prev) =>
          prev.map((item) => (item.id === n.id ? { ...item, read: true } : item))
        );
        setNotificationUnreadCount(Math.max(0, notificationUnreadCount - 1));
      } catch {
        // navigate anyway even if the mark-read call fails
      }
    }
    setOpen(false);
    navigate(`/posts/${n.post_id}`);
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={handleOpen}
        className="relative p-1 hover:text-blue-600 transition-colors"
        aria-label="Notifications"
      >
        {/* Bell SVG */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="w-5 h-5"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {notificationUnreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center leading-none">
            {notificationUnreadCount > 99 ? "99+" : notificationUnreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-8 w-80 bg-white border border-slate-200 rounded-lg shadow-lg z-50">
          <div className="flex items-center justify-between px-4 py-2 border-b border-slate-100">
            <span className="font-semibold text-sm">Notifications</span>
            {notificationUnreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs text-blue-600 hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>

          {items.length === 0 ? (
            <p className="px-4 py-6 text-sm text-slate-400 text-center">No notifications yet</p>
          ) : (
            <ul className="max-h-80 overflow-y-auto divide-y divide-slate-50">
              {items.map((n) => (
                <li
                  key={n.id}
                  onClick={() => handleNotificationClick(n)}
                  className={`px-4 py-3 flex items-start gap-3 cursor-pointer hover:bg-slate-50 transition-colors ${
                    !n.read ? "bg-blue-50" : ""
                  }`}
                >
                  {n.actor.avatar_url ? (
                    <img
                      src={n.actor.avatar_url}
                      alt={n.actor.display_name}
                      className="w-8 h-8 rounded-full object-cover flex-shrink-0"
                    />
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center flex-shrink-0 text-xs font-bold text-slate-600">
                      {n.actor.display_name[0]?.toUpperCase()}
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">
                      <span className="font-medium">{n.actor.display_name}</span>{" "}
                      {n.type === "like" ? "liked your post" : "commented on your post"}
                    </p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      {new Date(n.created_at).toLocaleString()}
                    </p>
                  </div>
                  {!n.read && (
                    <span className="w-2 h-2 rounded-full bg-blue-500 flex-shrink-0 mt-1.5" />
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
