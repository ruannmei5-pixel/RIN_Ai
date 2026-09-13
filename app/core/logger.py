"""
logger.py

Setup logging dasar untuk RIN.

Phase 1:
- Log ditulis ke console dan ke file `logs/rin.log`.
- Logging terpisah (rin.log vs actions.log) baru dilengkapi di PHASE 11.

Aturan penting:
- Jangan pernah mencatat password, API key, atau secret ke dalam log.
"""

from __future__ import annotations

import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "rin.log"

_LOGGER_NAME = "rin"
_configured = False


def get_logger() -> logging.Logger:
    """
    Mengembalikan logger utama RIN.

    Logger hanya dikonfigurasi satu kali (idempotent), sehingga aman
    dipanggil berkali-kali dari berbagai modul tanpa membuat handler ganda.
    """
    global _configured

    logger = logging.getLogger(_LOGGER_NAME)

    if _configured:
        return logger

    logger.setLevel(logging.DEBUG)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler console: tampilkan info ke atas, tanpa membuat layar berisik.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Handler file: simpan semua level debug ke atas untuk keperluan troubleshooting.
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    _configured = True
    return logger
