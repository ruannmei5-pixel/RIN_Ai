"""
search_router.py

Smart Search Detection untuk RIN (AUTOMATIC WEB SEARCH FEATURE).

Menentukan apakah sebuah pesan user membutuhkan web search sebelum
dijawab. Keputusan dibuat SECARA LOKAL DAN INSTAN (rule/keyword, ~0ms):

    1. STRONG keyword (berita, harga, cuaca, skor, jabatan saat ini,
       versi terbaru, dst)                      -> True
    2. NEVER keyword (konsep, coding, matematika, menulis)  -> False
    3. WEAK keyword (kata waktu seperti "sekarang"/"hari ini"/tahun
       2026) HANYA jika disertai kata tanya info (siapa/berapa/kapan/
       kondisi/status/...)                      -> True
    4. Selain itu (pertanyaan biasa/obrolan)    -> False

OPTIMASI LATENSI: tidak ada request LLM untuk pertanyaan biasa.
Classifier LLM HANYA berjalan jika caller memberikan `client` secara
eksplisit (lihat config.web_search.llm_classifier / env
SEARCH_ROUTER_LLM_CLASSIFIER, default MATI).

Modul ini SENGAJA tidak pernah melempar exception ke caller
(app/core/assistant.py): kegagalan apa pun pada langkah opsional ini
selalu menghasilkan `False` (tidak melakukan search).
"""

from __future__ import annotations

import re
from typing import Optional

from app.core.logger import get_logger
from app.llm.ollama_client import ChatMessage, OllamaClient

logger = get_logger()


# ============================================================
# KEYWORD: JELAS BUTUH SEARCH (STRONG)
# ============================================================

_STRONG_SEARCH_KEYWORDS: tuple[str, ...] = (
    # --- perilaku lama (dipertahankan) ---
    "terbaru",
    "kondisi terkini",
    "cuaca",
    "berita",
    "harga",
    "kurs",
    "nilai tukar",
    "skor",
    "hasil pertandingan",
    "pertandingan tadi",
    "jadwal pertandingan",
    "jadwal rilis",
    "siapa presiden",
    "siapa yang menang",
    "siapa juara",
    "versi terbaru",
    "rilis terbaru",
    "update terbaru",
    "trending",
    "viral",
    "gempa",
    "bencana",
    "saham",
    "harga tiket",
    "jam tayang",
    # --- tambahan (pengganti classifier LLM untuk kasus umum) ---
    "terkini",
    "kabar terbaru",
    "breaking news",
    "klasemen",
    "hasil liga",
    "jadwal liga",
    "jadwal bola",
    "ramalan cuaca",
    "prakiraan cuaca",
    "curah hujan",
    "ihsg",
    "bitcoin",
    "kripto",
    "crypto",
    "siapa ceo",
    "siapa direktur",
    "siapa gubernur",
    "siapa menteri",
    "siapa ketua",
    "siapa pemenang",
    "kapan rilis",
    "tanggal rilis",
    "release date",
    "release notes",
    "changelog",
    "latest",
    "news",
    "weather",
    "stock price",
    "exchange rate",
    "who won",
    "who is the current",
)

# ============================================================
# KEYWORD: BUTUH SEARCH HANYA JIKA ADA KATA TANYA INFO (WEAK)
# ============================================================
#
# Kata waktu seperti "hari ini"/"sekarang" sering muncul di obrolan
# biasa ("aku capek hari ini", "buat kodenya sekarang"), jadi tidak
# cukup sendirian untuk memicu search (yang menambah latensi Tavily).

_WEAK_TIME_KEYWORDS: tuple[str, ...] = (
    "hari ini",
    "sekarang",
    "saat ini",
    "kini",
    "minggu ini",
    "bulan ini",
    "tahun ini",
    "kemarin",
    "semalam",
    "tadi malam",
)

_INFO_QUESTION_CUES: tuple[str, ...] = (
    "siapa",
    "berapa",
    "kapan",
    "kondisi",
    "status",
    "update",
    "info",
    "perkembangan",
    "daftar",
    "rekomendasi",
    "jadwal",
    "hasil",
    "terlaris",
    "terbaik",
    "who",
    "when",
    "how much",
)

# Tahun 2025+ juga dianggap kata waktu lemah.
_YEAR_PATTERN = r"20(?:2[5-9]|[3-9]\d)"


def _compile_keywords(keywords: tuple[str, ...], extra: str = "") -> "re.Pattern[str]":
    """
    Regex batas-kata untuk daftar keyword (multi-kata didukung).

    Awalan Indonesia yang membuat arti berubah ("menghargai", "berharga",
    "skoring") TIDAK cocok, tapi akhiran umum (-nya/-lah/-kah) tetap cocok
    ("harganya", "beritanya").
    """
    ordered = sorted(keywords, key=len, reverse=True)
    body = "|".join(re.escape(keyword) for keyword in ordered)
    if extra:
        body = f"{body}|{extra}" if body else extra
    return re.compile(rf"(?<!\w)(?:{body})(?:nya|lah|kah)?(?!\w)")


_STRONG_RE = _compile_keywords(_STRONG_SEARCH_KEYWORDS)
_WEAK_TIME_RE = _compile_keywords(_WEAK_TIME_KEYWORDS, extra=_YEAR_PATTERN)
_INFO_CUE_RE = _compile_keywords(_INFO_QUESTION_CUES)

# ============================================================
# KEYWORD: JELAS TIDAK BUTUH SEARCH
# ============================================================

_NEVER_SEARCH_KEYWORDS: tuple[str, ...] = (
    "jelaskan apa itu",
    "apa itu",
    "apa perbedaan",
    "buatkan program",
    "buatkan kode",
    "buatkan fungsi",
    "buatkan script",
    "buat program",
    "buat kode",
    "buat fungsi",
    "cara kerja",
    "konsep",
    "rumus",
    "terjemahkan",
    "perbaiki kode",
    "refactor",
    "debug",
    "hitung",
    "brainstorm",
    "ide untuk",
    "tuliskan",
    "rewrite",
)


def _contains_any(text_lower: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text_lower for keyword in keywords)


# ============================================================
# LLM CLASSIFIER (opsional, opt-in)
# ============================================================

_CLASSIFIER_SYSTEM_PROMPT = (
    "Kamu adalah classifier biner internal. Kamu BUKAN asisten yang "
    "menjawab user secara langsung."
)

_CLASSIFIER_USER_PROMPT_TEMPLATE = (
    "Tentukan apakah pertanyaan berikut MEMBUTUHKAN informasi terbaru "
    "dari internet untuk dijawab dengan benar (misalnya karena "
    "berkaitan dengan berita, harga, cuaca, jadwal, hasil pertandingan, "
    "jabatan seseorang saat ini, versi software/dokumentasi terbaru, "
    "atau fakta lain yang bisa berubah dari waktu ke waktu).\n\n"
    "Jawab HANYA dengan satu kata: YA atau TIDAK. "
    "Jangan menambahkan kata, tanda baca, atau penjelasan apa pun selain itu.\n\n"
    "Pertanyaan: {question}"
)


def _ask_llm_classifier(text: str, client: OllamaClient) -> Optional[bool]:
    """
    Bertanya ke Ollama apakah `text` butuh web search.

    Returns:
        True/False jika classifier berhasil dan bisa dibaca.
        None jika classifier gagal/timeout/format tidak dikenal
        (caller akan fallback ke False).
    """

    messages = [
        ChatMessage(role="system", content=_CLASSIFIER_SYSTEM_PROMPT),
        ChatMessage(
            role="user",
            content=_CLASSIFIER_USER_PROMPT_TEMPLATE.format(question=text),
        ),
    ]

    try:
        raw_reply = client.chat(messages)
    except Exception as exc:  # pragma: no cover - jaring pengaman
        logger.warning(
            "SEARCH_ROUTER: LLM classifier gagal, fallback ke TIDAK search: %s",
            exc,
        )
        return None

    normalized = raw_reply.strip().lower()

    if normalized.startswith("ya"):
        return True

    if normalized.startswith("tidak"):
        return False

    logger.warning(
        "SEARCH_ROUTER: LLM classifier mengembalikan format tak dikenal "
        "(%r), fallback ke TIDAK search.",
        raw_reply[:50],
    )

    return None


# ============================================================
# PUBLIC API
# ============================================================

def needs_web_search(
    text: str,
    client: Optional[OllamaClient] = None,
) -> bool:
    """
    Menentukan apakah `text` (pesan user terakhir) membutuhkan web
    search sebelum dijawab.

    Args:
        text: pesan user.
        client: OPSIONAL. OllamaClient untuk classifier LLM pada kasus
            yang tidak cocok aturan apa pun. Default None -> pertanyaan
            biasa dianggap TIDAK butuh search, tanpa request LLM apa pun.
    """

    if not text or not text.strip():
        return False

    text_lower = text.lower()

    # 1. RULE: jelas butuh search (STRONG)
    if _STRONG_RE.search(text_lower):
        logger.info("SEARCH_ROUTER: keyword(strong) -> True | text=%r", text[:80])
        return True

    # 2. RULE: jelas TIDAK butuh search
    if _contains_any(text_lower, _NEVER_SEARCH_KEYWORDS):
        logger.info("SEARCH_ROUTER: keyword(never) -> False | text=%r", text[:80])
        return False

    # 3. RULE: kata waktu (weak) + kata tanya info
    if _WEAK_TIME_RE.search(text_lower) and _INFO_CUE_RE.search(text_lower):
        logger.info("SEARCH_ROUTER: keyword(time+question) -> True | text=%r", text[:80])
        return True

    # 4. PERTANYAAN BIASA: tanpa search, tanpa LLM kecuali client diberikan.
    if client is None:
        logger.info(
            "SEARCH_ROUTER: pertanyaan biasa -> False (tanpa LLM) | text=%r",
            text[:80],
        )
        return False

    decision = _ask_llm_classifier(text, client)

    if decision is None:
        return False

    logger.info(
        "SEARCH_ROUTER: LLM classifier -> %s | text=%r",
        decision,
        text[:80],
    )

    return decision
