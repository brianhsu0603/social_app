"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.String(512)),
        sa.Column("bio", sa.String(512)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "posts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_posts_author_id", "posts", ["author_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "post_media",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(1024), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_post_media_post_id", "post_media", ["post_id"])

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comments_post_id", "comments", ["post_id"])
    op.create_index("ix_comments_author_id", "comments", ["author_id"])

    op.create_table(
        "likes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("post_id", sa.Integer, sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("post_id", "user_id", name="uq_like_post_user"),
    )
    op.create_index("ix_likes_post_id", "likes", ["post_id"])
    op.create_index("ix_likes_user_id", "likes", ["user_id"])

    friendship_status = sa.Enum("pending", "accepted", "blocked", name="friendship_status")
    friendship_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "friendships",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("requester_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("addressee_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", friendship_status, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
        sa.CheckConstraint("requester_id <> addressee_id", name="ck_friendship_not_self"),
    )
    op.create_index("ix_friendships_requester_id", "friendships", ["requester_id"])
    op.create_index("ix_friendships_addressee_id", "friendships", ["addressee_id"])

    op.create_table(
        "chat_rooms",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128)),
        sa.Column("is_group", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "chat_room_members",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("room_id", sa.Integer, sa.ForeignKey("chat_rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("room_id", "user_id", name="uq_room_member"),
    )
    op.create_index("ix_chat_room_members_room_id", "chat_room_members", ["room_id"])
    op.create_index("ix_chat_room_members_user_id", "chat_room_members", ["user_id"])


def downgrade() -> None:
    op.drop_table("chat_room_members")
    op.drop_table("chat_rooms")
    op.drop_table("friendships")
    sa.Enum(name="friendship_status").drop(op.get_bind(), checkfirst=True)
    op.drop_table("likes")
    op.drop_table("comments")
    op.drop_table("post_media")
    op.drop_table("posts")
    op.drop_table("users")
