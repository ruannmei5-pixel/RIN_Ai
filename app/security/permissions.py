"""
permissions.py

PLACEHOLDER — akan diimplementasikan pada PHASE 10 (Security).

Rencana tanggung jawab modul ini:
- Mendefinisikan level permission: READ, WRITE, EXECUTE, SYSTEM.
- Default: READ diizinkan langsung; WRITE, EXECUTE, SYSTEM membutuhkan
  konfirmasi user sebelum tool dijalankan.
- Menjadi satu-satunya tempat keputusan "apakah tindakan ini boleh
  dijalankan tanpa/dengan konfirmasi user", dipanggil oleh semua modul
  di `app/tools/` sebelum eksekusi.

Alur yang akan diimplementasikan:
    AI memutuskan kebutuhan -> Tool memvalidasi -> Permission layer
    -> User confirmation jika diperlukan -> Tool execution -> Logging

Belum ada logika aktif pada Phase 1.
"""

from __future__ import annotations

from enum import Enum


class PermissionLevel(str, Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    SYSTEM = "SYSTEM"


# Default policy yang akan diterapkan pada PHASE 10:
# READ diizinkan otomatis, sisanya butuh konfirmasi user.
DEFAULT_REQUIRES_CONFIRMATION = {
    PermissionLevel.READ: False,
    PermissionLevel.WRITE: True,
    PermissionLevel.EXECUTE: True,
    PermissionLevel.SYSTEM: True,
}


def requires_confirmation(level: PermissionLevel) -> bool:
    """PLACEHOLDER kerangka dasar. Logika konfirmasi penuh menyusul di PHASE 10."""
    raise NotImplementedError("Permission layer akan diimplementasikan pada PHASE 10.")
