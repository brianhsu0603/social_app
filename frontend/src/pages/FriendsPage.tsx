import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { chat as chatApi, friends as friendsApi, users as usersApi } from "@/api/endpoints";

export default function FriendsPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const friendsQ = useQuery({ queryKey: ["friends"], queryFn: friendsApi.list });
  const incomingQ = useQuery({ queryKey: ["friends", "incoming"], queryFn: friendsApi.incoming });
  const searchQ = useQuery({
    queryKey: ["users", "search", q],
    queryFn: () => usersApi.search(q),
    enabled: q.length >= 2,
  });

  const sendReq = useMutation({
    mutationFn: (uid: number) => friendsApi.send(uid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["friends"] }),
  });
  const acceptReq = useMutation({
    mutationFn: (rid: number) => friendsApi.accept(rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["friends"] }),
  });
  const rejectReq = useMutation({
    mutationFn: (rid: number) => friendsApi.remove(rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["friends"] }),
  });

  async function startChat(userId: number) {
    const room = await chatApi.createRoom([userId]);
    navigate(`/chat/${room.id}`);
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <section className="bg-white rounded-lg shadow border p-4">
        <h2 className="font-semibold mb-3">Find people</h2>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by username or name"
          className="w-full border rounded px-3 py-2"
        />
        <ul className="mt-3 divide-y">
          {searchQ.data?.map((u) => (
            <li key={u.id} className="flex items-center justify-between py-2">
              <Link to={`/profile/${u.id}`} className="hover:underline">
                {u.display_name} <span className="text-slate-500 text-sm">@{u.username}</span>
              </Link>
              <button
                onClick={() => sendReq.mutate(u.id)}
                className="text-sm px-2 py-1 bg-blue-600 text-white rounded"
              >
                Add friend
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="bg-white rounded-lg shadow border p-4">
        <h2 className="font-semibold mb-3">Incoming requests</h2>
        {incomingQ.data?.length === 0 && <p className="text-slate-500 text-sm">Nothing pending.</p>}
        <ul className="divide-y">
          {incomingQ.data?.map((r) => (
            <li key={r.id} className="flex items-center justify-between py-2">
              <span>{r.requester.display_name} <span className="text-slate-500 text-sm">@{r.requester.username}</span></span>
              <div className="flex gap-2">
                <button onClick={() => acceptReq.mutate(r.id)} className="text-sm px-2 py-1 bg-green-600 text-white rounded">Accept</button>
                <button onClick={() => rejectReq.mutate(r.id)} className="text-sm px-2 py-1 bg-slate-300 rounded">Reject</button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="bg-white rounded-lg shadow border p-4">
        <h2 className="font-semibold mb-3">Your friends</h2>
        {friendsQ.data?.length === 0 && <p className="text-slate-500 text-sm">No friends yet.</p>}
        <ul className="divide-y">
          {friendsQ.data?.map((u) => (
            <li key={u.id} className="flex items-center justify-between py-2">
              <Link to={`/profile/${u.id}`} className="hover:underline">
                {u.display_name} <span className="text-slate-500 text-sm">@{u.username}</span>
              </Link>
              <button onClick={() => startChat(u.id)} className="text-sm px-2 py-1 bg-blue-600 text-white rounded">
                Message
              </button>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
