import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { comments as commentsApi, likes as likesApi, posts as postsApi } from "@/api/endpoints";
import { useAuth } from "@/store/auth";
import type { Comment, Post } from "@/types";

export function PostCard({ post }: { post: Post }) {
  const qc = useQueryClient();
  const currentUser = useAuth((s) => s.user);
  const isPostOwner = currentUser?.id === post.author.id;

  const [showComments, setShowComments] = useState(false);
  const [draft, setDraft] = useState("");
  const [liked, setLiked] = useState(post.liked_by_me);
  const [likeCount, setLikeCount] = useState(post.like_count);

  // Local content state so the UI updates immediately on save without waiting for refetch
  const [displayedContent, setDisplayedContent] = useState(post.content);
  const [editingPost, setEditingPost] = useState(false);
  const [postDraft, setPostDraft] = useState(post.content);

  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [commentDraft, setCommentDraft] = useState("");

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

  const updatePost = useMutation({
    mutationFn: (content: string) => postsApi.update(post.id, content),
    onSuccess: (_, content) => {
      setDisplayedContent(content);
      setEditingPost(false);
      qc.invalidateQueries({ queryKey: ["feed"] });
      qc.invalidateQueries({ queryKey: ["posts"] });
    },
  });

  const deletePost = useMutation({
    mutationFn: () => postsApi.remove(post.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed"] });
      qc.invalidateQueries({ queryKey: ["posts"] });
    },
  });

  const updateComment = useMutation({
    mutationFn: ({ id, content }: { id: number; content: string }) =>
      commentsApi.update(id, content),
    onSuccess: (updated) => {
      setEditingCommentId(null);
      // Update the comment in cache immediately so the new content shows right away
      qc.setQueryData(["comments", post.id], (old: Comment[] | undefined) =>
        old?.map((c) => (c.id === updated.id ? updated : c)) ?? [],
      );
    },
  });

  const deleteComment = useMutation({
    mutationFn: (id: number) => commentsApi.remove(id),
    onSuccess: (_, id) => {
      qc.setQueryData(["comments", post.id], (old: Comment[] | undefined) =>
        old?.filter((c) => c.id !== id) ?? [],
      );
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
        <div className="flex-1">
          <Link to={`/profile/${post.author.id}`} className="font-semibold hover:underline">
            {post.author.display_name}
          </Link>
          <div className="text-xs text-slate-500">{new Date(post.created_at).toLocaleString()}</div>
        </div>
        {isPostOwner && !editingPost && (
          <div className="flex gap-2 text-sm">
            <button
              onClick={() => { setEditingPost(true); setPostDraft(displayedContent); }}
              className="text-slate-500 hover:text-blue-600"
            >
              Edit
            </button>
            <button
              onClick={() => { if (confirm("Delete this post?")) deletePost.mutate(); }}
              className="text-slate-500 hover:text-red-600"
            >
              Delete
            </button>
          </div>
        )}
      </header>

      {editingPost ? (
        <div className="px-4 pt-3 pb-2 space-y-2">
          <textarea
            value={postDraft}
            onChange={(e) => setPostDraft(e.target.value)}
            className="w-full border rounded px-3 py-2 text-sm resize-none"
            rows={3}
          />
          {updatePost.isError && (
            <p className="text-xs text-red-500">Failed to save. Please try again.</p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => updatePost.mutate(postDraft)}
              disabled={updatePost.isPending}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm disabled:opacity-50"
            >
              {updatePost.isPending ? "Saving…" : "Save"}
            </button>
            <button
              onClick={() => setEditingPost(false)}
              className="px-3 py-1 border rounded text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        displayedContent && <p className="px-4 pt-3 whitespace-pre-wrap">{displayedContent}</p>
      )}

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
              {editingCommentId === c.id ? (
                <div className="space-y-1">
                  <input
                    value={commentDraft}
                    onChange={(e) => setCommentDraft(e.target.value)}
                    className="w-full border rounded px-2 py-1 text-sm"
                  />
                  {updateComment.isError && (
                    <p className="text-xs text-red-500">Failed to save. Please try again.</p>
                  )}
                  <div className="flex gap-2">
                    <button
                      onClick={() => updateComment.mutate({ id: c.id, content: commentDraft })}
                      disabled={updateComment.isPending}
                      className="px-2 py-0.5 bg-blue-600 text-white rounded text-xs disabled:opacity-50"
                    >
                      {updateComment.isPending ? "Saving…" : "Save"}
                    </button>
                    <button
                      onClick={() => setEditingCommentId(null)}
                      className="px-2 py-0.5 border rounded text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex items-start gap-2 group">
                  <span className="flex-1">
                    <Link to={`/profile/${c.author.id}`} className="font-semibold hover:underline">
                      {c.author.display_name}
                    </Link>{" "}
                    <span>{c.content}</span>
                  </span>
                  {currentUser?.id === c.author.id && (
                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => { setEditingCommentId(c.id); setCommentDraft(c.content); }}
                        className="text-slate-400 hover:text-blue-600 text-xs"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => deleteComment.mutate(c.id)}
                        className="text-slate-400 hover:text-red-600 text-xs"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              )}
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
