"""
terminal.py

PLACEHOLDER — akan diimplementasikan pada PHASE 8 (Terminal Tool).

Rencana tanggung jawab modul ini:
- Menjalankan command yang ada di whitelist saja (mis. `ipconfig`,
  `hostname`, `whoami`, `ping`).
- TIDAK PERNAH menjalankan `subprocess.run(user_input, shell=True)`
  atau mekanisme sejenis yang memberi LLM akses command bebas.
- Command yang berpotensi mengubah sistem wajib meminta konfirmasi
  dan tercatat di `logs/actions.log`.

Belum ada logika aktif pada Phase 1.
"""

from __future__ import annotations

# Whitelist command aman akan dibaca dari configuration pada PHASE 8.
ALLOWED_COMMANDS: tuple[str, ...] = ("ipconfig", "hostname", "whoami", "ping")


def run_command(command_key: str) -> str:
    """PLACEHOLDER. Akan diimplementasikan pada PHASE 8 dengan whitelist + konfirmasi + logging."""
    raise NotImplementedError("Terminal tool akan diimplementasikan pada PHASE 8.")
