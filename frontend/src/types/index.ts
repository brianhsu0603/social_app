export interface User {
  id: number;
  email?: string;
  username: string;
  display_name: string;
  avatar_url?: string | null;
  bio?: string | null;
  created_at?: string;
}

export interface Media {
  id?: number;
  url: string;
  media_type: "image" | "video";
  position?: number;
}

export interface Post {
  id: number;
  content: string;
  created_at: string;
  author: User;
  media: Media[];
  like_count: number;
  comment_count: number;
  liked_by_me: boolean;
}

export interface Comment {
  id: number;
  post_id: number;
  content: string;
  created_at: string;
  author: User;
}

export interface ChatRoom {
  id: number;
  name: string | null;
  is_group: boolean;
  created_by: number;
  created_at: string;
  members: User[];
  unread_count: number;
}

export interface ChatMessage {
  id: string;
  room_id: number;
  sender_id: number;
  content: string;
  media_url?: string | null;
  media_type?: "image" | "video" | null;
  created_at: string;
}

export interface Notification {
  id: number;
  type: "like" | "comment";
  post_id: number;
  read: boolean;
  created_at: string;
  actor: User;
}

export interface NotificationList {
  notifications: Notification[];
  unread_count: number;
}

export interface FriendRequest {
  id: number;
  requester: User;
  addressee: User;
  status: "pending" | "accepted" | "blocked";
  created_at: string;
}
