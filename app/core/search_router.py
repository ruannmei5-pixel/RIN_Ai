"""
search_router.py

Smart Search Detection untuk RIN (AUTOMATIC WEB SEARCH FEATURE).

Menentukan apakah sebuah pesan user membutuhkan web search sebelum
dijawab, memakai pendekatan HYBRID:

    1. RULE/KEYWORD (cepat, gratis, deterministic)
       - Kasus yang jelas butuh search (berita, harga, cuaca, jadwal,
         hasil pertandingan, jabatan orang saat ini, versi terbaru,
         dst) -> langsung True, TANPA memanggil Ollama sama sekali.
       - Kasus yang jelas TIDAK butuh search (matematika, konsep,
         brainstorming, menulis/rewriting, coding dasar) -> langsung
         False, TANPA memanggil Ollama sama sekali.

    2. LLM CLASSIFIER RINGAN (untuk kasus ambigu saja)
       - Hanya dipanggil jika kedua daftar keyword di atas TIDAK
         cocok sama sekali.
       - Satu pertanyaan singkat ke Ollama ("YA"/"TIDAK" saja),
         non-streaming, dengan fallback AMAN (anggap TIDAK butuh
         search) jika classifier gagal/timeout/format aneh, supaya
         chat biasa tidak pernah ikut gagal hanya karena langkah
         opsional ini.

TRADE-OFF PERFORMA (lihat juga README/jawaban):
    - Rule/keyword: ~0ms overhead, tapi tidak selalu akurat untuk
      kalimat yang tidak memakai keyword baku.
    - LLM classifier: akurasi lebih baik untuk kasus ambigu, TAPI
      menambah satu roundtrip ke Ollama (biasanya <1-3 detik untuk
      model kecil seperti qwen3:4b) SEBELUM jawaban utama mulai
      di-generate/streaming. Karena itu, LLM classifier HANYA dipakai
      sebagai fallback untuk kasus yang benar-benar ambigu, bukan
      untuk setiap pesan.

Modul ini SENGAJA tidak pernah melempar exception ke caller
(app/core/assistant.py): kegagalan apa pun pada langkah opsional ini
selalu menghasilkan `False` (tidak melakukan search), supaya chat
biasa tetap berjalan seperti biasa (lihat ATURAN PENTING: jangan
membuat search dilakukan pada semua pertanyaan, dan jangan membuat
RIN crash).
"""

from __future__ import annotations

from typing import Optional

from app.core.logger import get_logger
from app.llm.ollama_client import ChatMessage, OllamaClient

logger = get_logger()


# ============================================================
# KEYWORD: JELAS BUTUH SEARCH
# ============================================================

_ALWAYS_SEARCH_KEYWORDS: tuple[str, ...] = (
    "terbaru",
    "hari ini",
    "sekarang",
    "saat ini",
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
)

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
# LLM CLASSIFIER (untuk kasus ambigu)
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
        client: OllamaClient untuk classifier LLM pada kasus ambigu.
            Jika None, kasus ambigu dianggap TIDAK butuh search (fail
            safe, tanpa memanggil Ollama sama sekali).
    """

    if not text or not text.strip():
        return False

    text_lower = text.lower()

    # --------------------------------------------------------
    # 1. RULE: jelas butuh search
    # --------------------------------------------------------

    if _contains_any(text_lower, _ALWAYS_SEARCH_KEYWORDS):
        logger.info("SEARCH_ROUTER: keyword(always) -> True | text=%r", text[:80])
        return True

    # --------------------------------------------------------
    # 2. RULE: jelas TIDAK butuh search
    # --------------------------------------------------------

    if _contains_any(text_lower, _NEVER_SEARCH_KEYWORDS):
        logger.info("SEARCH_ROUTER: keyword(never) -> False | text=%r", text[:80])
        return False

    # --------------------------------------------------------
    # 3. AMBIGU: LLM classifier ringan (opsional)
    # --------------------------------------------------------

    if client is None:
        logger.info(
            "SEARCH_ROUTER: ambigu tanpa classifier -> False | text=%r",
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
