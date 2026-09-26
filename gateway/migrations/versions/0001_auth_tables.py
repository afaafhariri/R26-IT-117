"""Auth tables: accounts, users, sessions, email tokens and rate limits.

Revision ID: 0001
Revises:
Create Date: 2026-09-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamp(name: str, *, nullable: bool = False, now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.func.now() if now else None,
    )


def upgrade() -> None:
    # citext is a trusted extension, so authdb's owner can install it without
    # superuser rights.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext SCHEMA public")

    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _timestamp("created_at", now=True),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        _timestamp("email_verified_at", nullable=True),
        _timestamp("created_at", now=True),
        _timestamp("updated_at", now=True),
        _timestamp("last_login_at", nullable=True),
    )
    op.create_index("ix_users_account_id", "users", ["account_id"])

    op.create_table(
        "sessions",
        sa.Column("id_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("remember_me", sa.Boolean(), nullable=False),
        _timestamp("created_at"),
        _timestamp("last_seen_at"),
        _timestamp("idle_expires_at"),
        _timestamp("absolute_expires_at"),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_absolute_expires_at", "sessions", ["absolute_expires_at"])

    op.create_table(
        "email_tokens",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(32), nullable=False),
        _timestamp("created_at"),
        _timestamp("expires_at"),
        _timestamp("used_at", nullable=True),
        sa.CheckConstraint(
            "purpose IN ('verify_email', 'reset_password')", name="email_tokens_purpose_check"
        ),
    )
    op.create_index("ix_email_tokens_user_purpose", "email_tokens", ["user_id", "purpose"])

    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rate_limits")
    op.drop_table("email_tokens")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_table("accounts")
