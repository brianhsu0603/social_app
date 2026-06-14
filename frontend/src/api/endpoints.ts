import { api } from "./client";
import type { ChatMessage, ChatRoom, Comment, FriendRequest, Media, NotificationList, Post, User } from "@/types";

export const auth = {
  async register(body: { email: string; username: string; display_name: string; password: string }) {
    const { data } = await api.post<{ access_token: string }>("/auth/register", body);
    return data;
  },
  async login(emailOrUsername: string, password: string) {
    const form = new URLSearchParams();
    form.set("username", emailOrUsername);
    form.set("password", password);
    const { data } = await api.post<{ access_token: string }>("/auth/login", form);
    return data;
  },
  async me() {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },
};

export const users = {
  async search(q: string) {
    const { data } = await api.get<User[]>("/users/search", { params: { q } });
    return data;
  },
  async get(id: number) {
    const { data } = await api.get<User>(`/users/${id}`);
    return data;
  },
  async updateMe(body: Partial<Pick<User, "display_name" | "bio" | "avatar_url">>) {
    const { data } = await api.patch<User>("/users/me", body);
    return data;
  },
};

export const posts = {
  async create(content: string, media: Media[]) {
    const { data } = await api.post<Post>("/posts", { content, media });
    return data;
  },
  async get(id: number) {
    const { data } = await api.get<Post>(`/posts/${id}`);
    return data;
  },
  async forUser(userId: number) {
    const { data } = await api.get<Post[]>(`/posts/user/${userId}`);
    return data;
  },
  async update(id: number, content: string) {
    const { data } = await api.patch<Post>(`/posts/${id}`, { content });
    return data;
  },
  async remove(id: number) {
    await api.delete(`/posts/${id}`);
  },
};

export const feed = {
  async get(beforeId?: number) {
    const { data } = await api.get<Post[]>("/feed", { params: { before_id: beforeId } });
    return data;
  },
};

export const likes = {
  async like(postId: number) {
    await api.post(`/posts/${postId}/like`);
  },
  async unlike(postId: number) {
    await api.delete(`/posts/${postId}/like`);
  },
};

export const comments = {
  async list(postId: number) {
    const { data } = await api.get<Comment[]>(`/posts/${postId}/comments`);
    return data;
  },
  async add(postId: number, content: string) {
    const { data } = await api.post<Comment>(`/posts/${postId}/comments`, { content });
    return data;
  },
  async update(commentId: number, content: string) {
    const { data } = await api.patch<Comment>(`/comments/${commentId}`, { content });
    return data;
  },
  async remove(commentId: number) {
    await api.delete(`/comments/${commentId}`);
  },
};

export const friends = {
  async list() {
    const { data } = await api.get<User[]>("/friends");
    return data;
  },
  async incoming() {
    const { data } = await api.get<FriendRequest[]>("/friends/requests/incoming");
    return data;
  },
  async send(userId: number) {
    const { data } = await api.post<FriendRequest>(`/friends/requests/${userId}`);
    return data;
  },
  async accept(requestId: number) {
    const { data } = await api.post<FriendRequest>(`/friends/requests/${requestId}/accept`);
    return data;
  },
  async remove(requestId: number) {
    await api.delete(`/friends/requests/${requestId}`);
  },
};

export const media = {
  async upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    const { data } = await api.post<{ url: string; media_type: "image" | "video" }>("/media/upload", form);
    return data;
  },
};

export const notifications = {
  async list() {
    const { data } = await api.get<NotificationList>("/notifications");
    return data;
  },
  async markOneRead(id: number) {
    await api.patch(`/notifications/${id}/read`);
  },
  async markAllRead() {
    await api.post("/notifications/read-all");
  },
};

export const chat = {
  async listRooms() {
    const { data } = await api.get<ChatRoom[]>("/chat/rooms");
    return data;
  },
  async createRoom(memberIds: number[], name?: string) {
    const { data } = await api.post<ChatRoom>("/chat/rooms", { member_ids: memberIds, name });
    return data;
  },
  async history(roomId: number, beforeId?: string) {
    const { data } = await api.get<ChatMessage[]>(`/chat/rooms/${roomId}/messages`, {
      params: { before_id: beforeId },
    });
    return data;
  },
};
