import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { posts as postsApi, users as usersApi } from "@/api/endpoints";
import { PostCard } from "@/components/PostCard";
import { useAuth } from "@/store/auth";

export default function ProfilePage() {
  const { userId } = useParams();
  const id = Number(userId);
  const me = useAuth((s) => s.user);

  const userQ = useQuery({ queryKey: ["user", id], queryFn: () => usersApi.get(id), enabled: !!id });
  const postsQ = useQuery({ queryKey: ["posts", "user", id], queryFn: () => postsApi.forUser(id), enabled: !!id });

  if (userQ.isLoading) return <p className="text-center mt-8 text-slate-500">Loading…</p>;
  if (!userQ.data) return <p className="text-center mt-8 text-slate-500">User not found</p>;

  const u = userQ.data;
  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <div className="bg-white rounded-lg shadow border p-6 mb-4">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-full bg-slate-200 flex items-center justify-center text-2xl font-bold text-slate-600">
            {u.display_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <h1 className="text-2xl font-bold">{u.display_name}</h1>
            <p className="text-slate-500">@{u.username}</p>
            {u.bio && <p className="mt-2">{u.bio}</p>}
          </div>
        </div>
        {me?.id === u.id && <p className="text-xs text-slate-400 mt-3">This is your profile.</p>}
      </div>

      <div className="space-y-4">
        {postsQ.data?.map((p) => <PostCard key={p.id} post={p} />)}
        {postsQ.data && postsQ.data.length === 0 && (
          <p className="text-slate-500 text-center">No posts yet.</p>
        )}
      </div>
    </main>
  );
}
