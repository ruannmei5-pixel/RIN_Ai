"""
router.py

Deterministic keyword router untuk RIN (PHASE 7.1).

LATAR BELAKANG MASALAH:
Sebelum Phase 7.1, SEMUA keputusan "perlu tool atau tidak" (termasuk
`system_info`) selalu ditanyakan dulu ke Qwen3 lewat native tool-calling
Ollama (`OllamaClient.decide_tool_call`, lihat app/llm/ollama_client.py).
Untuk permintaan yang jelas-jelas butuh `system_info` (mis. "berapa CPU
saya?"), ini berarti RIN menunggu satu round-trip penuh ke model HANYA
untuk memutuskan tool apa yang dipakai — dan pada beberapa kondisi round
-trip ini timeout ("Tool-call decision gagal, lanjut tanpa tool: timed
out"), sehingga `system_info` TIDAK PERNAH terpanggil sama sekali dan
RIN salah menjawab seolah tidak punya akses ke informasi sistem.

SOLUSI PHASE 7.1:
Modul kecil ini HANYA berisi pencocokan kata kunci sederhana (bukan LLM,
bukan regex kompleks, bukan router baru yang berat) untuk mengenali
permintaan `system_info` yang jelas dari teks user, SEBELUM Assistant
sempat bertanya ke Ollama sama sekali (lihat pemakaiannya di
app/core/assistant.py::_decide_and_run_tool). Jika cocok, `system_info`
dipanggil langsung lewat ToolManager — tidak ada request ke Ollama untuk
tahap "tool selection" ini, sehingga tidak mungkin lagi terkena timeout
tool-call decision.

Modul ini SENGAJA tidak menyentuh routing `file_reader` / `workspace_list`
sama sekali. Kedua tool tersebut sudah bekerja dengan baik lewat
tool-calling Ollama seperti sebelumnya (lihat laporan Phase 7.1: kedua
tool berhasil, tidak timeout) — sesuai instruksi Phase 7.1 untuk hanya
mengubah seperlunya, `matches_system_info()` di bawah juga akan
menganggap sebuah pesan BUKAN permintaan system_info kalau pesan
tersebut mengandung petunjuk kuat bahwa user sedang meminta sesuatu
tentang file (lihat `_looks_like_file_request`), supaya permintaan file
tidak pernah "direbut" oleh router ini.
"""

from __future__ import annotations

import re
from typing import Iterable

# Kata kunci yang menandakan permintaan informasi sistem yang jelas.
# Dicocokkan sebagai frasa/kata utuh (word-boundary), case-insensitive,
# supaya kata pendek seperti "os" atau "ram" tidak salah cocok di
# tengah kata lain (mis. "posisi", "program").
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

# "os" sengaja dipisah dari list di atas: kata 2 huruf ini butuh
# word-boundary yang lebih ketat (huruf besar/kecil bercampur dengan
# kata bahasa Indonesia lain) tapi tetap valid sebagai keyword mandiri
# ketika berdiri sendiri sebagai kata, mis. "OS laptop saya apa?".
_SYSTEM_INFO_KEYWORDS_SHORT: tuple[str, ...] = ("os",)

# Petunjuk bahwa pesan sebenarnya tentang FILE (workspace_list /
# file_reader), bukan system_info — dicek LEBIH DULU supaya permintaan
# file tidak pernah salah dianggap system_info (lihat ATURAN PENTING
# Phase 7.1: "Pastikan permintaan file tidak salah dianggap sebagai
# system_info").
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


def _contains_any_keyword(text_lower: str, keywords: Iterable[str]) -> bool:
    for keyword in keywords:
        pattern = r"\b" + re.escape(keyword.strip()) + r"\b"
        if re.search(pattern, text_lower):
            return True
    return False


def _looks_like_file_request(text_lower: str) -> bool:
    """True jika pesan mengandung petunjuk kuat bahwa ini permintaan file."""
    return any(hint in text_lower for hint in _FILE_HINT_KEYWORDS)


def matches_system_info(text: str) -> bool:
    """
    True jika `text` adalah permintaan informasi sistem yang jelas
    (CPU, RAM, disk, OS, hostname, spesifikasi laptop, dsb).

    Sengaja konservatif: jika pesan juga mengandung petunjuk permintaan
    file (lihat `_FILE_HINT_KEYWORDS`), fungsi ini mengembalikan False
    supaya `file_reader` / `workspace_list` tidak pernah "direbut" oleh
    router system_info ini — permintaan seperti itu tetap diputuskan
    lewat jalur tool-calling Ollama seperti sebelumnya.
    """
    if not text or not text.strip():
        return False

    text_lower = text.lower()

    if _looks_like_file_request(text_lower):
        return False

    if _contains_any_keyword(text_lower, _SYSTEM_INFO_KEYWORDS):
        return True

    if _contains_any_keyword(text_lower, _SYSTEM_INFO_KEYWORDS_SHORT):
        return True

    return False
