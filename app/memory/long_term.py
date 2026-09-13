"""
long_term.py

PLACEHOLDER — akan diimplementasikan pada PHASE 4 (Memory).

Rencana tanggung jawab modul ini (sesuai task):
- save_memory()   -> menyimpan informasi yang SECARA EKSPLISIT diminta
                     user untuk diingat (mis. "RIN, ingat bahwa ...").
- get_memory()    -> mengambil satu memory berdasarkan kunci/id.
- search_memory() -> mencari memory berdasarkan kata kunci.
- delete_memory() -> menghapus memory (mis. "RIN, lupakan bahwa ...").
- list_memories() -> menampilkan semua long-term memory yang tersimpan.

Aturan penting yang harus dipegang saat implementasi nanti:
- JANGAN menyimpan seluruh percakapan secara otomatis sebagai long-term
  memory. Hanya simpan saat user eksplisit meminta RIN mengingat sesuatu.

Belum ada logika aktif pada Phase 1.
"""

from __future__ import annotations

from typing import List


def save_memory(content: str) -> None:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 4."""
    raise NotImplementedError("Long-term memory akan diimplementasikan pada PHASE 4.")


def get_memory(memory_id: int):
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 4."""
    raise NotImplementedError("Long-term memory akan diimplementasikan pada PHASE 4.")


def search_memory(keyword: str) -> List[str]:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 4."""
    raise NotImplementedError("Long-term memory akan diimplementasikan pada PHASE 4.")


def delete_memory(memory_id: int) -> None:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 4."""
    raise NotImplementedError("Long-term memory akan diimplementasikan pada PHASE 4.")


def list_memories() -> List[str]:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 4."""
    raise NotImplementedError("Long-term memory akan diimplementasikan pada PHASE 4.")
