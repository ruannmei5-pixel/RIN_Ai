"""
memory.py

SQLite-based conversation memory untuk RIN.

Fungsi:
- Membuat database SQLite secara otomatis.
- Menyimpan percakapan user dan RIN.
- Mengambil percakapan terbaru untuk context Ollama.
- Bisa menghapus seluruh memory.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Tuple


class Memory:
    """Mengelola memory percakapan RIN menggunakan SQLite."""

    def __init__(self, db_path: str | Path = "data/rin_memory.db") -> None:
        self.db_path = Path(db_path)

        # Pastikan folder data tersedia
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        """Membuka koneksi database SQLite."""
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        """Membuat tabel memory jika belum ada."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            connection.commit()

    def add_message(self, role: str, content: str) -> None:
        """
        Menyimpan satu pesan ke memory.

        role:
            system
            user
            assistant
        """
        if not content.strip():
            return

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (role, content)
                VALUES (?, ?)
                """,
                (role, content.strip()),
            )
            connection.commit()

    def get_recent_messages(
        self,
        limit: int = 20,
    ) -> List[Tuple[str, str]]:
        """
        Mengambil pesan terbaru dari memory.

        Returns:
            List berisi tuple:
            [
                ("user", "hai"),
                ("assistant", "Halo!"),
            ]
        """

        if limit <= 0:
            return []

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM conversations
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (limit,),
            ).fetchall()

        return [(row["role"], row["content"]) for row in rows]

    def get_all_messages(self) -> List[Tuple[str, str]]:
        """Mengambil seluruh isi memory."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM conversations
                ORDER BY id ASC
                """
            ).fetchall()

        return [(row["role"], row["content"]) for row in rows]

    def clear(self) -> None:
        """Menghapus seluruh memory percakapan."""
        with self._connect() as connection:
            connection.execute("DELETE FROM conversations")
            connection.commit()

    def count(self) -> int:
        """Mengembalikan jumlah pesan yang tersimpan."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM conversations"
            ).fetchone()

        return int(row["total"])