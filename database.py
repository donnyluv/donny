from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Dict, Iterable, List, Optional, Set, Tuple

from datetime import datetime

DB_PATH = Path("data/bot.db")


def get_connection() -> sqlite3.Connection:
    """Создает соединение с базой данных и при необходимости создает файл."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _ensure_system_colours_table(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_colours (
            guild_id INTEGER PRIMARY KEY,
            colour INTEGER NOT NULL
        )
        """
    )


def load_system_embed_colours() -> Dict[int, int]:
    """Возвращает словарь с сохраненными цветами системных сообщений по серверам."""

    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_system_colours_table(cursor)
        cursor.execute("SELECT guild_id, colour FROM system_colours")
        rows = cursor.fetchall()

    return {int(guild_id): int(colour) for guild_id, colour in rows}


def set_system_embed_colour(guild_id: int, colour: Optional[int]) -> None:
    """Сохраняет выбранный цвет системных сообщений для указанного сервера."""

    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_system_colours_table(cursor)

        if colour is None:
            cursor.execute("DELETE FROM system_colours WHERE guild_id = ?", (guild_id,))
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO system_colours (guild_id, colour) VALUES (?, ?)",
                (guild_id, colour),
            )

        connection.commit()


def get_system_embed_colour(guild_id: int) -> Optional[int]:
    """Возвращает сохраненный цвет системных сообщений для сервера."""

    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_system_colours_table(cursor)
        cursor.execute("SELECT colour FROM system_colours WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()

    if row is None:
        return None

    return int(row[0])


# ---------------------------------------------------------------------------
# Idea management helpers


def _ensure_ideas_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            channel_id INTEGER,
            message_id INTEGER,
            thread_id INTEGER,
            admin_id INTEGER,
            rejection_reason TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS idea_ratings (
            idea_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            PRIMARY KEY (idea_id, user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS idea_settings (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS idea_admin_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )
        """
    )


def load_idea_channels() -> Dict[int, int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute("SELECT guild_id, channel_id FROM idea_settings")
        rows = cursor.fetchall()

    return {
        int(guild_id): int(channel_id)
        for guild_id, channel_id in rows
        if channel_id is not None
    }


def set_idea_channel(guild_id: int, channel_id: Optional[int]) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)

        if channel_id is None:
            cursor.execute(
                "DELETE FROM idea_settings WHERE guild_id = ?",
                (guild_id,),
            )
        else:
            cursor.execute(
                "INSERT OR REPLACE INTO idea_settings (guild_id, channel_id) VALUES (?, ?)",
                (guild_id, channel_id),
            )

        connection.commit()


def get_idea_channel(guild_id: int) -> Optional[int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT channel_id FROM idea_settings WHERE guild_id = ?", (guild_id,)
        )
        row = cursor.fetchone()

    if row is None:
        return None

    channel_id = row[0]
    return int(channel_id) if channel_id is not None else None


def load_idea_admin_roles() -> Dict[int, Set[int]]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute("SELECT guild_id, role_id FROM idea_admin_roles")
        rows = cursor.fetchall()

    roles: Dict[int, Set[int]] = {}
    for guild_id, role_id in rows:
        roles.setdefault(int(guild_id), set()).add(int(role_id))
    return roles


def set_idea_admin_roles(guild_id: int, role_ids: Iterable[int]) -> None:
    role_set = {int(role_id) for role_id in role_ids}

    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "DELETE FROM idea_admin_roles WHERE guild_id = ?",
            (guild_id,),
        )
        if role_set:
            cursor.executemany(
                "INSERT INTO idea_admin_roles (guild_id, role_id) VALUES (?, ?)",
                [(guild_id, role_id) for role_id in role_set],
            )
        connection.commit()


def get_idea_admin_roles(guild_id: int) -> Set[int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT role_id FROM idea_admin_roles WHERE guild_id = ?",
            (guild_id,),
        )
        rows = cursor.fetchall()

    return {int(role_id) for (role_id,) in rows}


def create_idea(
    guild_id: int,
    author_id: int,
    content: str,
    *,
    created_at: Optional[datetime] = None,
) -> int:
    timestamp = (created_at or datetime.utcnow()).isoformat()
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            INSERT INTO ideas (
                guild_id,
                author_id,
                content,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?)
            """,
            (guild_id, author_id, content, timestamp, timestamp),
        )
        idea_id = cursor.lastrowid
        connection.commit()

    return int(idea_id)


def store_idea_message(
    idea_id: int,
    *,
    channel_id: Optional[int],
    message_id: Optional[int],
    thread_id: Optional[int],
) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            UPDATE ideas
            SET channel_id = ?, message_id = ?, thread_id = ?, updated_at = updated_at
            WHERE id = ?
            """,
            (channel_id, message_id, thread_id, idea_id),
        )
        connection.commit()


def update_idea_status(
    idea_id: int,
    *,
    status: str,
    admin_id: Optional[int],
    rejection_reason: Optional[str],
    updated_at: Optional[datetime] = None,
) -> None:
    timestamp = (updated_at or datetime.utcnow()).isoformat()
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            UPDATE ideas
            SET status = ?, admin_id = ?, rejection_reason = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, admin_id, rejection_reason, timestamp, idea_id),
        )
        connection.commit()


def delete_idea(idea_id: int) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute("DELETE FROM idea_ratings WHERE idea_id = ?", (idea_id,))
        cursor.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        connection.commit()


IdeaRow = Dict[str, object]


def get_idea(idea_id: int) -> Optional[IdeaRow]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            SELECT
                id,
                guild_id,
                author_id,
                content,
                status,
                created_at,
                updated_at,
                channel_id,
                message_id,
                thread_id,
                admin_id,
                rejection_reason
            FROM ideas
            WHERE id = ?
            """,
            (idea_id,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    keys = [
        "id",
        "guild_id",
        "author_id",
        "content",
        "status",
        "created_at",
        "updated_at",
        "channel_id",
        "message_id",
        "thread_id",
        "admin_id",
        "rejection_reason",
    ]
    return {key: row[index] for index, key in enumerate(keys)}


def list_user_ideas(
    guild_id: int,
    author_id: int,
    *,
    limit: int,
    offset: int,
) -> List[IdeaRow]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            SELECT
                id,
                guild_id,
                author_id,
                content,
                status,
                created_at,
                updated_at,
                channel_id,
                message_id,
                thread_id,
                admin_id,
                rejection_reason
            FROM ideas
            WHERE guild_id = ? AND author_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, author_id, limit, offset),
        )
        rows = cursor.fetchall()

    keys = [
        "id",
        "guild_id",
        "author_id",
        "content",
        "status",
        "created_at",
        "updated_at",
        "channel_id",
        "message_id",
        "thread_id",
        "admin_id",
        "rejection_reason",
    ]

    return [
        {key: row[index] for index, key in enumerate(keys)}
        for row in rows
    ]


def list_server_ideas(
    guild_id: int,
    *,
    limit: int,
    offset: int,
) -> List[IdeaRow]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            SELECT
                id,
                guild_id,
                author_id,
                content,
                status,
                created_at,
                updated_at,
                channel_id,
                message_id,
                thread_id,
                admin_id,
                rejection_reason
            FROM ideas
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (guild_id, limit, offset),
        )
        rows = cursor.fetchall()

    keys = [
        "id",
        "guild_id",
        "author_id",
        "content",
        "status",
        "created_at",
        "updated_at",
        "channel_id",
        "message_id",
        "thread_id",
        "admin_id",
        "rejection_reason",
    ]

    return [
        {key: row[index] for index, key in enumerate(keys)}
        for row in rows
    ]


def list_pending_idea_messages() -> List[IdeaRow]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            SELECT
                id,
                guild_id,
                author_id,
                content,
                status,
                created_at,
                updated_at,
                channel_id,
                message_id,
                thread_id,
                admin_id,
                rejection_reason
            FROM ideas
            WHERE status = 'pending' AND channel_id IS NOT NULL AND message_id IS NOT NULL
            """
        )
        rows = cursor.fetchall()

    keys = [
        "id",
        "guild_id",
        "author_id",
        "content",
        "status",
        "created_at",
        "updated_at",
        "channel_id",
        "message_id",
        "thread_id",
        "admin_id",
        "rejection_reason",
    ]

    return [
        {key: row[index] for index, key in enumerate(keys)}
        for row in rows
    ]


def count_user_ideas(guild_id: int, author_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM ideas WHERE guild_id = ? AND author_id = ?",
            (guild_id, author_id),
        )
        row = cursor.fetchone()

    return int(row[0]) if row else 0


def count_server_ideas(guild_id: int) -> int:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM ideas WHERE guild_id = ?",
            (guild_id,),
        )
        row = cursor.fetchone()

    return int(row[0]) if row else 0


def get_user_idea_stats(guild_id: int, author_id: int) -> Dict[str, float | int | None]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM ideas WHERE guild_id = ? AND author_id = ?",
            (guild_id, author_id),
        )
        total_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ideas
            WHERE guild_id = ? AND author_id = ? AND status = 'approved'
            """,
            (guild_id, author_id),
        )
        approved_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ideas
            WHERE guild_id = ? AND author_id = ? AND status = 'rejected'
            """,
            (guild_id, author_id),
        )
        rejected_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT AVG(r.rating), COUNT(r.rating)
            FROM idea_ratings r
            INNER JOIN ideas i ON i.id = r.idea_id
            WHERE i.guild_id = ? AND i.author_id = ?
            """,
            (guild_id, author_id),
        )
        rating_row = cursor.fetchone()

    average_rating: Optional[float] = None
    rating_count = 0
    if rating_row:
        avg_value, count_value = rating_row
        if avg_value is not None:
            average_rating = float(avg_value)
        if count_value is not None:
            rating_count = int(count_value)

    return {
        "total": int(total_row[0]) if total_row else 0,
        "approved": int(approved_row[0]) if approved_row else 0,
        "rejected": int(rejected_row[0]) if rejected_row else 0,
        "average_rating": average_rating,
        "ratings_count": rating_count,
    }


def get_server_idea_stats(guild_id: int) -> Dict[str, int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT COUNT(*) FROM ideas WHERE guild_id = ?",
            (guild_id,),
        )
        total_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ideas
            WHERE guild_id = ? AND status = 'approved'
            """,
            (guild_id,),
        )
        approved_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ideas
            WHERE guild_id = ? AND status = 'rejected'
            """,
            (guild_id,),
        )
        rejected_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM ideas
            WHERE guild_id = ? AND status = 'pending'
            """,
            (guild_id,),
        )
        pending_row = cursor.fetchone()

    return {
        "total": int(total_row[0]) if total_row else 0,
        "approved": int(approved_row[0]) if approved_row else 0,
        "rejected": int(rejected_row[0]) if rejected_row else 0,
        "pending": int(pending_row[0]) if pending_row else 0,
    }


def get_idea_rating_summary(idea_id: int) -> Tuple[Optional[float], int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT AVG(rating), COUNT(rating) FROM idea_ratings WHERE idea_id = ?",
            (idea_id,),
        )
        row = cursor.fetchone()

    if not row:
        return None, 0

    avg_value, count_value = row
    average = float(avg_value) if avg_value is not None else None
    count = int(count_value or 0)
    return average, count


def set_idea_rating(idea_id: int, user_id: int, rating: int) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            """
            INSERT INTO idea_ratings (idea_id, user_id, rating)
            VALUES (?, ?, ?)
            ON CONFLICT(idea_id, user_id)
            DO UPDATE SET rating = excluded.rating
            """,
            (idea_id, user_id, rating),
        )
        connection.commit()


def remove_idea_rating(idea_id: int, user_id: int) -> None:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "DELETE FROM idea_ratings WHERE idea_id = ? AND user_id = ?",
            (idea_id, user_id),
        )
        connection.commit()


def get_user_rating_for_idea(idea_id: int, user_id: int) -> Optional[int]:
    with get_connection() as connection:
        cursor = connection.cursor()
        _ensure_ideas_tables(cursor)
        cursor.execute(
            "SELECT rating FROM idea_ratings WHERE idea_id = ? AND user_id = ?",
            (idea_id, user_id),
        )
        row = cursor.fetchone()

    if row is None:
        return None
    rating_value = row[0]
    return int(rating_value) if rating_value is not None else None