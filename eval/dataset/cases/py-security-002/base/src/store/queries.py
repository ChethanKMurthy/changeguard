import sqlite3


def find_user(conn: sqlite3.Connection, user_id: int) -> tuple | None:
    cursor = conn.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
