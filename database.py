from pathlib import Path
import sqlite3
from typing import Dict, Optional

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