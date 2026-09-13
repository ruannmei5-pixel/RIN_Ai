"""
applications.py

PLACEHOLDER — akan diimplementasikan pada PHASE 7 (Application Control).

Rencana tanggung jawab modul ini:
- Membuka aplikasi Windows dari daftar whitelist saja (mis. VS Code,
  Chrome, File Explorer).
- TIDAK memberikan arbitrary executable execution ke LLM.
- Meminta konfirmasi user sebelum membuka aplikasi.

Belum ada logika aktif pada Phase 1.
"""

from __future__ import annotations

# Daftar whitelist akan diisi dan dibaca dari configuration pada PHASE 7,
# bukan di-hardcode secara permanen di sini.
ALLOWED_APPS: dict[str, str] = {}


def open_application(app_key: str) -> None:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 7 dengan whitelist + konfirmasi."""
    raise NotImplementedError("Application control tool akan diimplementasikan pada PHASE 7.")
