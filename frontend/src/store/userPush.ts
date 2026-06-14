import { create } from "zustand";

interface UserPushState {
  notificationUnreadCount: number;
  chatUnreadCount: number;
  onChatPage: boolean;
  setNotificationUnreadCount: (n: number) => void;
  incrementNotificationCount: () => void;
  setChatUnreadCount: (n: number) => void;
  incrementChatCount: () => void;
  setOnChatPage: (v: boolean) => void;
}

export const useUserPush = create<UserPushState>((set) => ({
  notificationUnreadCount: 0,
  chatUnreadCount: 0,
  onChatPage: false,
  setNotificationUnreadCount: (n) => set({ notificationUnreadCount: n }),
  incrementNotificationCount: () =>
    set((s) => ({ notificationUnreadCount: s.notificationUnreadCount + 1 })),
  setChatUnreadCount: (n) => set({ chatUnreadCount: n }),
  incrementChatCount: () =>
    set((s) => ({ chatUnreadCount: s.chatUnreadCount + 1 })),
  setOnChatPage: (v) => set({ onChatPage: v }),
}));
