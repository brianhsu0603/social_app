import { useQuery } from "@tanstack/react-query";
import { feed as feedApi } from "@/api/endpoints";
import { Composer } from "@/components/Composer";
import { PostCard } from "@/components/PostCard";

export default function FeedPage() {
  const { data, isLoading } = useQuery({ queryKey: ["feed"], queryFn: () => feedApi.get() });
  return (
    <main className="max-w-2xl mx-auto px-4 py-6">
      <Composer />
      {isLoading && <p className="text-slate-500">Loading feed…</p>}
      <div className="space-y-4">
        {data?.map((p) => <PostCard key={p.id} post={p} />)}
        {data && data.length === 0 && (
          <p className="text-slate-500 text-center">
            No posts yet. Add some friends or share something!
          </p>
        )}
      </div>
    </main>
  );
}
