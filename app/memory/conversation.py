"""
conversation.py

PLACEHOLDER — akan diimplementasikan pada PHASE 4 (Memory).

Rencana tanggung jawab modul ini:
- Menyimpan riwayat percakapan (conversation history) ke SQLite,
  terpisah dari short-term history yang saat ini masih disimpan
  sementara di memory proses oleh `app/core/assistant.py`.

Belum ada logika aktif pada Phase 1.
"""

from __future__ import annotations


def save_turn(role: str, content: str) -> None:
    """PLACEHOLDER. Akan menyimpan satu giliran percakapan ke database pada PHASE 4."""
    raise NotImplementedError("Conversation memory akan diimplementasikan pada PHASE 4.")


def load_recent_history(limit: int = 20):
    """PLACEHOLDER. Akan memuat riwayat percakapan terbaru pada PHASE 4."""
    raise NotImplementedError("Conversation memory akan diimplementasikan pada PHASE 4.")
