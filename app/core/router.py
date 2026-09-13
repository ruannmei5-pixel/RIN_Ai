"""
router.py

Deterministic keyword router untuk RIN (PHASE 7.1).

Router ini mengenali permintaan system_info yang jelas
tanpa meminta Ollama melakukan tool selection terlebih dahulu.
"""

from __future__ import annotations

import re
from typing import Iterable


_SYSTEM_INFO_KEYWORDS: tuple[str, ...] = (
    "cpu",
    "prosesor",
    "processor",
    "ram",
    "memory",
    "memori",
    "penggunaan cpu",
    "penggunaan ram",
    "disk",
    "penyimpanan",
    "storage",
    "sistem operasi",
    "windows",
    "hostname",
    "nama komputer",
    "spesifikasi laptop",
    "spesifikasi komputer",
    "informasi sistem",
    "info sistem",
    "informasi laptop",
    "info laptop",
    "sistem laptop",
)

_SYSTEM_INFO_KEYWORDS_SHORT: tuple[str, ...] = (
    "os",
)

_FILE_HINT_KEYWORDS: tuple[str, ...] = (
    "baca ",
    "file",
    "workspace",
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".py",
    ".js",
    ".html",
    ".css",
    ".yaml",
    ".yml",
    ".log",
)


def _contains_any_keyword(
    text_lower: str,
    keywords: Iterable[str],
) -> bool:
    """
    Mengecek apakah teks mengandung salah satu keyword.
    Pencocokan tidak membedakan huruf besar/kecil.
    """

    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword.strip()) + r"\b"

        if re.search(pattern, text_lower):
            return True

    return False


def _looks_like_file_request(
    text_lower: str,
) -> bool:
    """
    True jika pesan terlihat seperti permintaan file/workspace.
    """

    return any(
        hint in text_lower
        for hint in _FILE_HINT_KEYWORDS
    )


def matches_system_info(text: str) -> bool:
    """
    True jika text merupakan permintaan informasi sistem
    yang cukup jelas.

    Contoh yang cocok:
        - berapa CPU saya?
        - penggunaan RAM berapa?
        - informasi sistem laptop
        - OS saya apa?
        - hostname komputer saya apa?
        - spesifikasi laptop saya

    Permintaan file sengaja ditolak agar tidak direbut
    oleh router system_info.
    """

    if not text or not text.strip():
        return False

    text_lower = text.lower()

    # Prioritas pertama: jangan ambil alih permintaan file.
    if _looks_like_file_request(text_lower):
        return False

    # Keyword utama.
    if _contains_any_keyword(
        text_lower,
        _SYSTEM_INFO_KEYWORDS,
    ):
        return True

    # Keyword pendek seperti "OS".
    if _contains_any_keyword(
        text_lower,
        _SYSTEM_INFO_KEYWORDS_SHORT,
    ):
        return True

    return False