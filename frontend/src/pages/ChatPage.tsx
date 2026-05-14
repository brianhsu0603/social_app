import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chat as chatApi, friends as friendsApi, media as mediaApi } from "@/api/endpoints";
import { useChatSocket } from "@/hooks/useChatSocket";
import { useAuth } from "@/store/auth";
import type { ChatMessage } from "@/types";

export default function ChatPage() {
  const { roomId } = useParams();
  const rid = roomId ? Number(roomId) : null;
  const me = useAuth((s) => s.user);
  const navigate = useNavigate();
  const qc = useQueryClient();

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
  const scrollRef = useRef<HTMLDivElement>(null);

  // Mongo returns newest-first; render oldest-first.
  useEffect(() => {
    if (historyQ.data) setMessages([...historyQ.data].reverse());
  }, [historyQ.data]);

  const onWsMessage = useCallback((m: ChatMessage) => {
    setMessages((prev) => (prev.some((p) => p.id === m.id) ? prev : [...prev, m]));
  }, []);
  const { ready, send } = useChatSocket(rid, onWsMessage);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages.length]);

  async function sendMessage(payload: { content: string; media?: { url: string; media_type: "image" | "video" } }) {
    if (!rid) return;
    if (ready && send(payload.content, payload.media)) return;
    // Fallback to REST when the socket isn't open yet.
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
    onWsMessage(m);
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
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Message…"
              className="flex-1 border rounded px-3 py-1.5 text-sm"
            />
            <button className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm">Send</button>
          </form>
        )}
      </section>
    </main>
  );
}
