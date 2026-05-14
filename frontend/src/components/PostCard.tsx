import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { comments as commentsApi, likes as likesApi } from "@/api/endpoints";
import type { Post } from "@/types";

export function PostCard({ post }: { post: Post }) {
  const qc = useQueryClient();
  const [showComments, setShowComments] = useState(false);
  const [draft, setDraft] = useState("");
  const [liked, setLiked] = useState(post.liked_by_me);
  const [likeCount, setLikeCount] = useState(post.like_count);

  const commentsQ = useQuery({
    queryKey: ["comments", post.id],
    queryFn: () => commentsApi.list(post.id),
    enabled: showComments,
  });

  const addComment = useMutation({
    mutationFn: () => commentsApi.add(post.id, draft),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["comments", post.id] });
    },
  });

  async function toggleLike() {
    const next = !liked;
    setLiked(next);
    setLikeCount((c) => c + (next ? 1 : -1));
    try {
      if (next) await likesApi.like(post.id);
      else await likesApi.unlike(post.id);
    } catch {
      setLiked(!next);
      setLikeCount((c) => c + (next ? -1 : 1));
    }
  }

  return (
    <article className="bg-white rounded-lg shadow border border-slate-200">
      <header className="flex items-center gap-3 p-3 border-b">
        <div className="w-9 h-9 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 font-semibold">
          {post.author.display_name.charAt(0).toUpperCase()}
        </div>
        <div>
          <Link to={`/profile/${post.author.id}`} className="font-semibold hover:underline">
            {post.author.display_name}
          </Link>
          <div className="text-xs text-slate-500">{new Date(post.created_at).toLocaleString()}</div>
        </div>
      </header>

      {post.content && <p className="px-4 pt-3 whitespace-pre-wrap">{post.content}</p>}

      {post.media.length > 0 && (
        <div className="px-4 pt-3 grid grid-cols-1 gap-2">
          {post.media.map((m, i) =>
            m.media_type === "image" ? (
              <img key={i} src={m.url} className="rounded max-h-[480px] object-cover w-full" />
            ) : (
              <video key={i} src={m.url} controls className="rounded max-h-[480px] w-full" />
            ),
          )}
        </div>
      )}

      <div className="px-4 py-3 flex gap-4 text-sm border-t mt-3">
        <button onClick={toggleLike} className={liked ? "text-blue-600 font-semibold" : "text-slate-700"}>
          {liked ? "♥ Liked" : "♡ Like"} ({likeCount})
        </button>
        <button onClick={() => setShowComments((v) => !v)} className="text-slate-700">
          💬 Comments ({post.comment_count})
        </button>
      </div>

      {showComments && (
        <div className="px-4 pb-4 border-t pt-3 space-y-2">
          {commentsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
          {commentsQ.data?.map((c) => (
            <div key={c.id} className="text-sm">
              <Link to={`/profile/${c.author.id}`} className="font-semibold hover:underline">
                {c.author.display_name}
              </Link>{" "}
              <span>{c.content}</span>
            </div>
          ))}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) addComment.mutate();
            }}
            className="flex gap-2 pt-2"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="flex-1 border rounded px-3 py-1 text-sm"
              placeholder="Write a comment…"
            />
            <button className="px-3 py-1 bg-blue-600 text-white rounded text-sm">Post</button>
          </form>
        </div>
      )}
    </article>
  );
}
