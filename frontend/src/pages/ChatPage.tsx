import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chat as chatApi, friends as friendsApi, media as mediaApi } from "@/api/endpoints";
import { useChatSocket, type TypingUser } from "@/hooks/useChatSocket";
import { useAuth } from "@/store/auth";
import { useUserPush } from "@/store/userPush";
import type { ChatMessage } from "@/types";

export default function ChatPage() {
  const { roomId } = useParams();
  const rid = roomId ? Number(roomId) : null;
  const me = useAuth((s) => s.user);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { setChatUnreadCount, setOnChatPage } = useUserPush();

  // Immediately clear the nav badge and suppress further increments while here.
  useEffect(() => {
    setOnChatPage(true);
    setChatUnreadCount(0);
    return () => setOnChatPage(false);
  }, [setOnChatPage, setChatUnreadCount]);

  const roomsQ = useQuery({ queryKey: ["chat", "rooms"], queryFn: chatApi.listRooms });
  const historyQ = useQuery({
    queryKey: ["chat", "history", rid],
    queryFn: () => chatApi.history(rid!),
    enabled: rid != null,
  });
  const friendsQ = useQuery({ queryKey: ["friends"], queryFn: friendsApi.list });

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [uploading, setUploading] = useState(false);
  const [typingUsers, setTypingUsers] = useState<Set<number>>(new Set());
  const [showGroupModal, setShowGroupModal] = useState(false);
  const [selectedMembers, setSelectedMembers] = useState<Set<number>>(new Set());
  const [groupName, setGroupName] = useState("");
  const typingTimeoutRef = useRef<NodeJS.Timeout>();
  const lastTypingTimeRef = useRef<number>(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Mongo returns newest-first; render oldest-first.
  useEffect(() => {
    if (historyQ.data) setMessages([...historyQ.data].reverse());
  }, [historyQ.data]);

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    };
  }, []);

  const onWsMessage = useCallback((m: ChatMessage) => {
    setMessages((prev) => (prev.some((p) => p.id === m.id) ? prev : [...prev, m]));
  }, []);
  
  const onTyping = useCallback((users: TypingUser[]) => {
    setTypingUsers((prev) => {
      const updated = new Set(prev);
      users.forEach((u) => {
        // Filter out current user's typing events
        if (u.user_id !== me?.id) {
          updated.add(u.user_id);
        }
      });
      return updated;
    });
    
    // Clear typing indicator after 3 seconds of inactivity
    if (typingTimeoutRef.current) clearTimeout(typingTimeoutRef.current);
    typingTimeoutRef.current = setTimeout(() => {
      setTypingUsers(new Set());
    }, 3000);
  }, [me?.id]);
  
  const { ready, send, sendTyping } = useChatSocket(rid, onWsMessage, onTyping);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages.length, typingUsers.size]);

  async function sendMessage(payload: { content: string; media?: { url: string; media_type: "image" | "video" } }) {
    if (!rid || !me) return;
    
    // Create an optimistic message with a temporary ID
    const tempId = `temp-${Date.now()}`;
    const optimisticMessage: ChatMessage = {
      id: tempId,
      room_id: rid,
      sender_id: me.id,
      content: payload.content,
      media_url: payload.media?.url ?? null,
      media_type: payload.media?.media_type ?? null,
      created_at: new Date().toISOString(),
    };
    
    // Add optimistic message immediately
    setMessages((prev) => [...prev, optimisticMessage]);
    
    // Try to send via WebSocket first
    if (ready && send(payload.content, payload.media)) return;
    
    // Fallback to REST when the socket isn't open yet.
    try {
      const m = await fetch(`${import.meta.env.VITE_API_URL}/chat/rooms/${rid}/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${localStorage.getItem("token")}`,
        },
        body: JSON.stringify({
          room_id: rid,
          content: payload.content,
          media_url: payload.media?.url ?? null,
          media_type: payload.media?.media_type ?? null,
        }),
      }).then((r) => r.json());
      
      // Replace optimistic message with actual message from server
      setMessages((prev) => prev.map((msg) => (msg.id === tempId ? m : msg)));
    } catch (error) {
      console.error("Failed to send message:", error);
      // Remove optimistic message on error
      setMessages((prev) => prev.filter((msg) => msg.id !== tempId));
    }
  }

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const m = await mediaApi.upload(file);
      await sendMessage({ content: "", media: m });
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  const newDirect = useMutation({
    mutationFn: (uid: number) => chatApi.createRoom([uid]),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["chat", "rooms"] });
      navigate(`/chat/${room.id}`);
    },
  });

  const newGroup = useMutation({
    mutationFn: (memberIds: number[]) => chatApi.createRoom(memberIds, groupName || undefined),
    onSuccess: (room) => {
      qc.invalidateQueries({ queryKey: ["chat", "rooms"] });
      navigate(`/chat/${room.id}`);
      setShowGroupModal(false);
      setSelectedMembers(new Set());
      setGroupName("");
    },
  });

  const currentRoom = roomsQ.data?.find((r) => r.id === rid) ?? null;

  return (
    <main className="max-w-5xl mx-auto px-4 py-6 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4 h-[calc(100vh-7rem)]">
      <aside className="bg-white rounded-lg shadow border p-3 overflow-y-auto">
        <h2 className="font-semibold mb-2 text-sm">Conversations</h2>
        <ul className="space-y-1 mb-4">
          {roomsQ.data?.map((r) => {
            const others = r.members.filter((u) => u.id !== me?.id);
            const label = r.name ?? (others.map((u) => u.display_name).join(", ") || "Chat");
            return (
              <li key={r.id}>
                <button
                  onClick={() => navigate(`/chat/${r.id}`)}
                  className={`w-full text-left px-2 py-1.5 rounded text-sm ${
                    r.id === rid ? "bg-blue-100 text-blue-700" : "hover:bg-slate-100"
                  }`}
                >
                  {label}
                </button>
              </li>
            );
          })}
        </ul>
        <h3 className="font-semibold mb-2 text-sm">Start new</h3>
        <div className="space-y-2 mb-4">
          <button
            onClick={() => setShowGroupModal(true)}
            className="w-full px-2 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
          >
            ➕ New Group
          </button>
        </div>
        <ul className="space-y-1">
          {friendsQ.data?.map((u) => (
            <li key={u.id}>
              <button
                onClick={() => newDirect.mutate(u.id)}
                className="w-full text-left px-2 py-1.5 rounded text-sm hover:bg-slate-100"
              >
                {u.display_name}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <section className="bg-white rounded-lg shadow border flex flex-col">
        <header className="border-b px-4 py-2 text-sm flex justify-between items-center">
          <span className="font-semibold">
            {currentRoom
              ? currentRoom.name ??
                currentRoom.members.filter((u) => u.id !== me?.id).map((u) => u.display_name).join(", ")
              : "Select a conversation"}
          </span>
          {rid && <span className={`text-xs ${ready ? "text-green-600" : "text-slate-400"}`}>{ready ? "● live" : "○ offline"}</span>}
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2">
          {rid == null && <p className="text-slate-500 text-sm">Pick a friend on the left to start chatting.</p>}
          {messages.map((m) => {
            const mine = m.sender_id === me?.id;
            return (
              <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${mine ? "bg-blue-600 text-white" : "bg-slate-100"}`}>
                  {m.content && <div className="whitespace-pre-wrap">{m.content}</div>}
                  {m.media_url && m.media_type === "image" && (
                    <img src={m.media_url} className="mt-1 rounded max-w-xs" />
                  )}
                  {m.media_url && m.media_type === "video" && (
                    <video src={m.media_url} controls className="mt-1 rounded max-w-xs" />
                  )}
                </div>
              </div>
            );
          })}
          {typingUsers.size > 0 && (
            <div className="flex justify-start">
              <div className="text-slate-500 text-xs italic px-3 py-1">
                {Array.from(typingUsers)
                  .filter((uid) => uid !== me?.id)
                  .map((uid) => {
                    const user = currentRoom?.members.find((m) => m.id === uid);
                    return user?.display_name || "Someone";
                  })
                  .join(", ")} {Array.from(typingUsers).filter((uid) => uid !== me?.id).length === 1 ? "is" : "are"} typing...
              </div>
            </div>
          )}
        </div>

        {rid != null && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!draft.trim()) return;
              sendMessage({ content: draft });
              setDraft("");
            }}
            className="border-t p-2 flex gap-2"
          >
            <label className="px-2 py-1 cursor-pointer text-sm text-slate-600 hover:text-blue-600">
              <input type="file" accept="image/*,video/*" className="hidden" onChange={onPick} />
              {uploading ? "…" : "📎"}
            </label>
            <input
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                // Throttle typing events to once per second
                const now = Date.now();
                if (now - lastTypingTimeRef.current > 1000) {
                  sendTyping();
                  lastTypingTimeRef.current = now;
                }
              }}
              placeholder="Message…"
              className="flex-1 border rounded px-3 py-1.5 text-sm"
            />
            <button className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm">Send</button>
          </form>
        )}
      </section>

      {showGroupModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-lg p-6 w-96 max-h-[90vh] flex flex-col">
            <h2 className="text-lg font-semibold mb-4">Create Group Chat</h2>
            
            <input
              type="text"
              placeholder="Group name (optional)"
              value={groupName}
              onChange={(e) => setGroupName(e.target.value)}
              className="w-full border rounded px-3 py-2 mb-4 text-sm"
            />

            <div className="flex-1 overflow-y-auto border rounded mb-4 p-2">
              <p className="text-xs text-slate-500 mb-2">Select members:</p>
              {friendsQ.data?.map((friend) => (
                <label key={friend.id} className="flex items-center gap-2 p-2 hover:bg-slate-50 rounded cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedMembers.has(friend.id)}
                    onChange={(e) => {
                      const updated = new Set(selectedMembers);
                      if (e.target.checked) {
                        updated.add(friend.id);
                      } else {
                        updated.delete(friend.id);
                      }
                      setSelectedMembers(updated);
                    }}
                    className="rounded"
                  />
                  <span className="text-sm">{friend.display_name}</span>
                </label>
              ))}
            </div>

            <div className="flex gap-2 justify-end">
              <button
                onClick={() => {
                  setShowGroupModal(false);
                  setSelectedMembers(new Set());
                  setGroupName("");
                }}
                className="px-3 py-1.5 border rounded text-sm hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (selectedMembers.size > 0) {
                    newGroup.mutate(Array.from(selectedMembers));
                  }
                }}
                disabled={selectedMembers.size === 0 || newGroup.isPending}
                className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {newGroup.isPending ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
