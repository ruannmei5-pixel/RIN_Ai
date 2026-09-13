"""
database.py

PLACEHOLDER — akan diimplementasikan pada PHASE 4 (Memory).

Rencana tanggung jawab modul ini:
- Membuat/menghubungkan ke database SQLite di `data/rin_memory.db`.
- Menyediakan koneksi/skema dasar yang dipakai oleh `conversation.py`
  dan `long_term.py`.

Belum ada logika aktif pada Phase 1. Modul ini sengaja disiapkan
sebagai stub agar struktur project sudah sesuai target sejak awal,
tanpa menambahkan dependency database sebelum benar-benar diperlukan.
"""

from __future__ import annotations

from pathlib import Path

# Lokasi database akan digunakan pada PHASE 4.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_PATH = PROJECT_ROOT / "data" / "rin_memory.db"


def get_connection():
    """
    PLACEHOLDER.

    Pada PHASE 4, fungsi ini akan mengembalikan koneksi `sqlite3` ke
    `data/rin_memory.db`, termasuk memastikan skema tabel sudah dibuat.
    """
    raise NotImplementedError("Memory database akan diimplementasikan pada PHASE 4.")
