import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { media as mediaApi, posts as postsApi } from "@/api/endpoints";
import type { Media } from "@/types";

export function Composer() {
  const [content, setContent] = useState("");
  const [media, setMedia] = useState<Media[]>([]);
  const [uploading, setUploading] = useState(false);
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: () => postsApi.create(content, media),
    onSuccess: () => {
      setContent("");
      setMedia([]);
      qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  async function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    setUploading(true);
    try {
      const uploaded = await Promise.all(files.map((f) => mediaApi.upload(f)));
      setMedia((m) => [...m, ...uploaded]);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div className="bg-white rounded-lg shadow border border-slate-200 p-4 mb-4">
      <textarea
        rows={3}
        value={content}
        onChange={(e) => setContent(e.target.value)}
        className="w-full border rounded p-2 resize-none"
        placeholder="What's on your mind?"
      />
      {media.length > 0 && (
        <div className="flex gap-2 mt-2 flex-wrap">
          {media.map((m, i) => (
            <div key={i} className="relative">
              {m.media_type === "image" ? (
                <img src={m.url} className="w-24 h-24 object-cover rounded" />
              ) : (
                <video src={m.url} className="w-24 h-24 object-cover rounded" />
              )}
              <button
                onClick={() => setMedia(media.filter((_, j) => j !== i))}
                className="absolute -top-2 -right-2 bg-slate-700 text-white rounded-full w-5 h-5 text-xs"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between mt-2">
        <label className="text-sm text-slate-600 cursor-pointer hover:text-blue-600">
          <input type="file" multiple accept="image/*,video/*" className="hidden" onChange={onPick} />
          {uploading ? "Uploading…" : "📎 Add photo/video"}
        </label>
        <button
          disabled={create.isPending || (!content.trim() && media.length === 0)}
          onClick={() => create.mutate()}
          className="px-4 py-1.5 bg-blue-600 text-white rounded disabled:opacity-50"
        >
          Post
        </button>
      </div>
    </div>
  );
}
