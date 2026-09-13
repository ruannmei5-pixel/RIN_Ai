"""
web_search.py

Web Search service untuk RIN (AUTOMATIC WEB SEARCH FEATURE).

Tanggung jawab modul ini, dan HANYA modul ini:
- Memanggil Web Search API eksternal (Tavily) untuk mendapatkan hasil
  pencarian (title, url, snippet).
- Memformat hasil pencarian menjadi blok context [SOURCE N] yang siap
  dikirim ke Ollama sebagai tambahan pesan (BUKAN menggantikan history).
- Memformat daftar sumber untuk ditampilkan ke user di akhir jawaban.

MENGAPA TAVILY:
- API sederhana (satu endpoint POST, JSON in/out).
- Dibuat khusus untuk use case LLM/RAG: hasilnya sudah berupa
  title/url/content bersih, tanpa perlu HTML scraping sendiri.
- Free tier tersedia (tidak perlu kartu kredit untuk mulai).
- Berjalan baik dari server Debian/Linux mana pun (hanya butuh HTTPS
  keluar), tidak butuh browser/headless Chrome seperti beberapa
  alternatif scraping.

KEAMANAN:
- API key TIDAK PERNAH di-hardcode di sini. Selalu dibaca dari
  environment variable TAVILY_API_KEY (lihat app/core/config.py &
  .env.example).
- API key TIDAK PERNAH ditulis ke log.
- Hasil pencarian diperlakukan sebagai DATA, bukan instruksi (lihat
  format_search_context() dan catatan prompt-injection di bawah).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

load_dotenv()

from app.core.logger import get_logger

logger = get_logger()

_TAVILY_ENDPOINT = "https://api.tavily.com/search"

# Batas panjang snippet per sumber, supaya satu sumber "nakal" tidak bisa
# membanjiri context window dengan teks yang sangat panjang.
_MAX_SNIPPET_CHARS = 600


# ============================================================
# ERRORS
# ============================================================

class WebSearchError(Exception):
    """Error umum saat melakukan web search."""


class WebSearchNotConfiguredError(WebSearchError):
    """TAVILY_API_KEY belum dikonfigurasi di environment/.env."""


# ============================================================
# RESULT
# ============================================================

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


# ============================================================
# SEARCH
# ============================================================

def is_configured() -> bool:
    """True jika TAVILY_API_KEY sudah diset di environment."""
    return bool(os.getenv("TAVILY_API_KEY", "").strip())


def search_web(
    query: str,
    max_results: int = 3,
    timeout_seconds: int = 8,
) -> List[SearchResult]:
    """
    Melakukan web search dan mengembalikan daftar SearchResult.

    Raises:
        WebSearchNotConfiguredError: jika TAVILY_API_KEY tidak diset.
        WebSearchError: jika request gagal (koneksi, timeout, status
            error, atau format response tidak dikenal).

    Fungsi ini TIDAK PERNAH mengembalikan traceback/detail internal ke
    caller lewat pesan exception yang tidak aman; caller (search_router
    / assistant.py) bertanggung jawab menangkap WebSearchError dan
    melakukan fallback ke Ollama tanpa search (PENTING: jangan biarkan
    RIN crash hanya karena search gagal).
    """

    api_key = os.getenv("TAVILY_API_KEY", "").strip()

    if not api_key:
        raise WebSearchNotConfiguredError(
            "TAVILY_API_KEY tidak dikonfigurasi. Set di file .env "
            "(lihat .env.example)."
        )

    query = (query or "").strip()

    if not query:
        return []

    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "max_results": max(1, min(max_results, 10)),
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        response = httpx.post(
            _TAVILY_ENDPOINT,
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

    except httpx.TimeoutException as exc:
        raise WebSearchError(
            f"Web search timeout setelah {timeout_seconds} detik."
        ) from exc

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else "?"
        # PENTING: jangan pernah menyertakan api_key di pesan error/log.
        raise WebSearchError(
            f"Web search API mengembalikan status {status_code}."
        ) from exc

    except httpx.RequestError as exc:
        raise WebSearchError(
            f"Tidak dapat terhubung ke web search API: {exc}"
        ) from exc

    except ValueError as exc:
        # response.json() gagal parse.
        raise WebSearchError(
            "Response web search API tidak dapat dibaca (bukan JSON valid)."
        ) from exc

    raw_results = data.get("results")

    if not isinstance(raw_results, list):
        raise WebSearchError(
            "Format response web search API tidak dikenal (field 'results' hilang)."
        )

    results: List[SearchResult] = []

    for item in raw_results[:max_results]:
        if not isinstance(item, dict):
            continue

        url = str(item.get("url") or "").strip()

        if not url:
            # Jangan pernah membuat/menebak URL. Lewati sumber tanpa URL.
            continue

        title = str(item.get("title") or "").strip() or url

        snippet = str(item.get("content") or "").strip()
        snippet = snippet[:_MAX_SNIPPET_CHARS]

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
            )
        )

    logger.info(
        "WEB_SEARCH: query=%r hasil=%d",
        query,
        len(results),
    )

    return results


# ============================================================
# CONTEXT FORMATTING (untuk dikirim ke Ollama)
# ============================================================

def format_search_context(results: List[SearchResult]) -> str:
    """
    Memformat hasil pencarian menjadi blok [SOURCE N] seperti diminta,
    supaya konsisten dan mudah dibaca baik oleh model maupun manusia
    yang membaca log.
    """
    blocks = []

    for index, result in enumerate(results, start=1):
        blocks.append(
            f"[SOURCE {index}]\n"
            f"Title: {result.title}\n"
            f"URL: {result.url}\n"
            f"Snippet: {result.snippet}"
        )

    return "\n\n".join(blocks)


# ============================================================
# SOURCES FOOTER (untuk ditampilkan ke user)
# ============================================================

def format_sources_footer(results: List[SearchResult]) -> str:
    """
    Membuat daftar sumber yang ditambahkan RIN (oleh KODE, bukan oleh
    model) di akhir jawaban, supaya URL yang tampil ke user dijamin
    berasal dari hasil pencarian sungguhan (tidak pernah dikarang oleh
    model).
    """

    if not results:
        return ""

    lines = [f"- {result.title} — {result.url}" for result in results]

    return "\n\nSumber:\n" + "\n".join(lines)
