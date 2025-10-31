from pathlib import Path
import sqlite3

DB_PATH = Path("data/bot.db")


def get_connection() -> sqlite3.Connection:
    """Создает соединение с базой данных и при необходимости создает файл."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)