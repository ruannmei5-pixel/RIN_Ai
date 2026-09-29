"""
openai_compatible.py

TAHAP 3 — Base class untuk provider cloud yang kompatibel dengan
OpenAI-style Chat Completions API (`POST {base_url}/chat/completions`).

Dipakai oleh:
- NvidiaProvider  (app/llm/providers/nvidia_provider.py)

Semua logic HTTP, streaming (SSE), dan error handling ada di SATU
tempat ini.

KEAMANAN:
- API key HANYA dipakai untuk membangun header Authorization di sini,
  di backend. Tidak pernah dikembalikan/di-log.
- Pesan error SENGAJA disaring supaya tidak pernah menyertakan API key
  atau isi header Authorization (lihat `_sanitize_error_text`).
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from app.core.logger import get_logger
from app.llm.base import (
    AIProvider,
    ChatMessage,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderHealth,
    ProviderModelNotFoundError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

logger = get_logger()


def _sanitize_error_text(text: str, api_key: str) -> str:
    """Pastikan API key tidak pernah muncul di pesan error, walau tertukar."""
    if api_key:
        text = text.replace(api_key, "***")
    return text[:300]


class OpenAICompatibleProvider(AIProvider):
    """
    Provider generik untuk API bergaya OpenAI Chat Completions.

    Subclass HANYA perlu mengisi `id`, `display_name`, dan default
    base_url lewat constructor masing-masing (lihat nvidia_provider.py).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 25.0,
        extra_headers: Optional[Dict[str, str]] = None,
        connect_timeout_seconds: float = 5.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.model = (model or "").strip()
        # timeout_seconds dipakai untuk DUA hal: batas tunggu byte
        # berikutnya dari server (httpx read timeout) DAN batas total
        # menunggu token pertama pada streaming. Setelah itu router
        # (app/llm/router.py) fallback ke provider cadangan.
        self.timeout_seconds = timeout_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self._extra_headers = extra_headers or {}

        # Satu httpx.Client dipakai ulang (connection pooling + keep-alive),
        # sehingga TCP/TLS handshake hanya terjadi sekali. Dibuat lazy.
        self._transport = transport
        self._client: Optional[httpx.Client] = None
        self._client_lock = threading.Lock()

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout_seconds,
            read=self.timeout_seconds,
            write=10.0,
            pool=5.0,
        )

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = httpx.Client(
                        timeout=self._timeout(),
                        limits=httpx.Limits(
                            max_connections=10,
                            max_keepalive_connections=5,
                            keepalive_expiry=60.0,
                        ),
                        transport=self._transport,
                    )
        return self._client

    def close(self) -> None:
        """Menutup koneksi persisten (opsional; dipanggil saat shutdown)."""
        client, self._client = self._client, None
        if client is not None:
            client.close()

    # --------------------------------------------------------------
    # CONFIG
    # --------------------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.base_url)

    @property
    def active_model(self) -> str:
        return self.model

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers)
        return headers

    def _require_configured(self) -> None:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                f"{self.display_name}: API key belum dikonfigurasi."
            )
        if not self.model:
            raise ProviderNotConfiguredError(
                f"{self.display_name}: model belum dikonfigurasi "
                f"(set environment variable model-nya)."
            )

    @staticmethod
    def _messages_payload(messages: List[ChatMessage]) -> List[Dict[str, str]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    # --------------------------------------------------------------
    # CHAT (non-streaming)
    # --------------------------------------------------------------

    def chat(self, messages: List[ChatMessage], model: Optional[str] = None) -> str:
        self._require_configured()
        active_model = (model or self.model).strip()

        payload = {
            "model": active_model,
            "messages": self._messages_payload(messages),
            "stream": False,
        }

        try:
            response = self._get_client().post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name}: request melebihi {self.timeout_seconds:g} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"{self.display_name}: tidak dapat terhubung ({exc.__class__.__name__})."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(
                f"{self.display_name}: error HTTP tak terduga ({exc.__class__.__name__})."
            ) from exc

        self._raise_for_status(response)

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderResponseError(
                f"{self.display_name}: response tidak dapat dibaca."
            ) from exc

        if not content or not str(content).strip():
            raise ProviderResponseError(
                f"{self.display_name}: mengembalikan balasan kosong."
            )

        return str(content)

    # --------------------------------------------------------------
    # CHAT (streaming, SSE)
    # --------------------------------------------------------------

    def chat_stream(self, messages: List[ChatMessage], model: Optional[str] = None) -> Iterator[str]:
        self._require_configured()
        active_model = (model or self.model).strip()

        payload = {
            "model": active_model,
            "messages": self._messages_payload(messages),
            "stream": True,
        }

        full_reply = ""
        started_at = time.monotonic()

        try:
            with self._get_client().stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    # Baca body error (bukan stream) sebelum melempar.
                    response.read()
                    self._raise_for_status(response)

                for line in response.iter_lines():
                    # Batas total menunggu token pertama. httpx read
                    # timeout saja tidak cukup: jika server terus
                    # mengirim keep-alive/event kosong, read timeout
                    # tidak pernah terpicu dan RIN menggantung.
                    if (
                        not full_reply
                        and time.monotonic() - started_at > self.timeout_seconds
                    ):
                        raise ProviderTimeoutError(
                            f"{self.display_name}: token pertama tidak tiba "
                            f"dalam {self.timeout_seconds:g} detik."
                        )
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[len("data:"):].strip()

                    if data_str == "[DONE]":
                        break

                    try:
                        event = json.loads(data_str)
                    except ValueError:
                        continue

                    try:
                        delta = event["choices"][0].get("delta", {})
                        chunk = delta.get("content") or ""
                    except (KeyError, IndexError, TypeError):
                        chunk = ""

                    if chunk:
                        full_reply += chunk
                        yield chunk

        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"{self.display_name}: streaming timeout setelah {self.timeout_seconds:g} detik."
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"{self.display_name}: koneksi streaming terputus ({exc.__class__.__name__})."
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderResponseError(
                f"{self.display_name}: error HTTP streaming tak terduga ({exc.__class__.__name__})."
            ) from exc

        if not full_reply.strip():
            raise ProviderResponseError(
                f"{self.display_name}: tidak menghasilkan jawaban."
            )

    # --------------------------------------------------------------
    # ERROR MAPPING
    # --------------------------------------------------------------

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return

        status = response.status_code
        body_text = _sanitize_error_text(response.text or "", self.api_key)

        if status in (401, 403):
            raise ProviderAuthError(
                f"{self.display_name}: API key ditolak (HTTP {status})."
            )
        if status == 404:
            raise ProviderModelNotFoundError(
                f"{self.display_name}: model '{self.model}' tidak ditemukan (HTTP 404)."
            )
        if status == 429:
            raise ProviderUnavailableError(
                f"{self.display_name}: rate limit tercapai (HTTP 429)."
            )
        if status >= 500:
            raise ProviderUnavailableError(
                f"{self.display_name}: server sedang tidak tersedia (HTTP {status})."
            )

        logger.warning(
            "%s: HTTP %s tidak dikenal — body(sanitized)=%r",
            self.display_name,
            status,
            body_text,
        )
        raise ProviderResponseError(
            f"{self.display_name}: mengembalikan error (HTTP {status})."
        )

    # --------------------------------------------------------------
    # MODELS / HEALTH
    # --------------------------------------------------------------

    def get_models(self) -> List[str]:
        if not self.api_key:
            return []
        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=8,
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("data", [])
            return [
                str(item.get("id") or "").strip()
                for item in items
                if isinstance(item, dict) and item.get("id")
            ]
        except Exception as exc:  # pragma: no cover - jaring pengaman
            logger.warning("%s: gagal mengambil daftar model: %s", self.display_name, exc)
            return []

    def health_check(self) -> ProviderHealth:
        if not self.is_configured():
            return ProviderHealth(
                configured=False,
                available=False,
                detail=f"{self.display_name}: belum dikonfigurasi.",
            )

        try:
            response = httpx.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=8,
            )
            if response.status_code in (401, 403):
                return ProviderHealth(
                    configured=True,
                    available=False,
                    detail=f"{self.display_name}: API key ditolak.",
                )
            response.raise_for_status()
            return ProviderHealth(
                configured=True,
                available=True,
                detail=f"{self.model} via {self.base_url}",
            )
        except Exception:
            return ProviderHealth(
                configured=True,
                available=False,
                detail=f"{self.display_name} sedang tidak dapat dihubungi.",
            )
