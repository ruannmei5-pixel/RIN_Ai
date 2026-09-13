from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

import httpx
from ollama import Client, ResponseError

from app.core.logger import get_logger

logger = get_logger()


# ============================================================
# ERROR
# ============================================================

class OllamaError(Exception):
    """Error umum yang berkaitan dengan Ollama."""


class OllamaConnectionError(OllamaError):
    """Ollama tidak dapat dihubungi."""


class OllamaTimeoutError(OllamaError):
    """Request ke Ollama timeout."""


class OllamaModelNotFoundError(OllamaError):
    """Model Ollama tidak ditemukan."""


class OllamaResponseError(OllamaError):
    """Response Ollama tidak sesuai."""


# ============================================================
# MESSAGE
# ============================================================

@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ToolCallRequest:
    """Satu keputusan tool-call terstruktur dari model (PHASE 6F)."""

    name: str
    arguments: Dict[str, Any]


# ============================================================
# THINKING FILTER
# ============================================================

def clean_thinking(text: str) -> str:
    """
    Membersihkan reasoning/thinking dari output Qwen.

    Mendukung beberapa bentuk:

        <think>
        reasoning
        </think>
        jawaban

    maupun:

        reasoning
        </think>
        jawaban
    """

    if not text:
        return ""

    # --------------------------------------------------------
    # Kasus normal:
    # <think> ... </think> jawaban
    # --------------------------------------------------------

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Kasus Qwen yang kita temukan:
    #
    # reasoning
    # </think>
    # jawaban
    #
    # Ambil hanya bagian SETELAH </think>
    # --------------------------------------------------------

    if "</think>" in text.lower():
        parts = re.split(
            r"</think>",
            text,
            maxsplit=1,
            flags=re.IGNORECASE,
        )

        text = parts[1]

    # --------------------------------------------------------
    # Bersihkan kemungkinan tag pembuka yang tersisa
    # --------------------------------------------------------

    text = re.sub(
        r"<think>.*?",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    return text.strip()


# ============================================================
# STREAM THINKING FILTER
# ============================================================

class ThinkingStreamFilter:
    """
    Filter streaming untuk memastikan reasoning tidak pernah
    ditampilkan ke user.

    Strategi:

        sebelum </think>
            → tahan semuanya

        setelah </think>
            → keluarkan sebagai jawaban final
    """

    def __init__(self) -> None:
        self.buffer = ""
        self.finished_thinking = False

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""

        self.buffer += chunk

        # ----------------------------------------------------
        # Kalau reasoning sudah selesai
        # ----------------------------------------------------

        if self.finished_thinking:
            result = self.buffer
            self.buffer = ""
            return result

        # ----------------------------------------------------
        # Cari </think>
        # ----------------------------------------------------

        match = re.search(
            r"</think>",
            self.buffer,
            flags=re.IGNORECASE,
        )

        if match:
            self.finished_thinking = True

            result = self.buffer[match.end():]

            self.buffer = ""

            return result

        # ----------------------------------------------------
        # Jangan keluarkan apa pun selama thinking.
        #
        # Ini sengaja dilakukan supaya reasoning Qwen tidak
        # pernah muncul di terminal.
        # ----------------------------------------------------

        return ""

    def finish(self) -> str:
        """
        Dipanggil ketika stream selesai.

        Kalau tidak pernah menemukan </think>, kita anggap
        seluruh buffer sebagai jawaban agar RIN tidak blank.
        """

        if self.finished_thinking:
            result = self.buffer
            self.buffer = ""
            return result

        # Tidak ada </think>.
        # Bersihkan fallback.
        result = clean_thinking(self.buffer)

        self.buffer = ""

        return result


# ============================================================
# OLLAMA CLIENT
# ============================================================

class OllamaClient:
    """
    Client RIN untuk Ollama local API.
    """

    def __init__(
        self,
        host: str,
        model: str,
        timeout_seconds: int = 60,
    ) -> None:

        self.host = host.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

        self._client = Client(
            host=self.host,
            timeout=timeout_seconds,
        )

    # ========================================================
    # CHAT NORMAL
    # ========================================================

    def chat(self, messages: List[ChatMessage]) -> str:

        payload = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

        try:

            response = self._client.chat(
                model=self.model,
                messages=payload,
                think=False,
                stream=False,
            )

        except TypeError:

            # Compatibility dengan Ollama client lama.

            try:

                response = self._client.chat(
                    model=self.model,
                    messages=payload,
                    stream=False,
                )

            except Exception as exc:
                self._raise_generic(exc)

        except ResponseError as exc:
            self._raise_response_error(exc)

        except (httpx.ConnectError, ConnectionError) as exc:

            logger.error(
                "Tidak dapat terhubung ke Ollama: %s",
                exc,
            )

            raise OllamaConnectionError(
                f"Tidak dapat terhubung ke Ollama di {self.host}."
            ) from exc

        except httpx.TimeoutException as exc:

            logger.error(
                "Ollama timeout: %s",
                exc,
            )

            raise OllamaTimeoutError(
                f"Request Ollama melebihi {self.timeout_seconds} detik."
            ) from exc

        except Exception as exc:
            self._raise_generic(exc)

        # ----------------------------------------------------
        # Ambil content
        # ----------------------------------------------------

        try:

            content = response.message.content

        except AttributeError:

            try:
                content = response["message"]["content"]

            except (KeyError, TypeError) as exc:

                raise OllamaResponseError(
                    "Response Ollama tidak dapat dibaca."
                ) from exc

        # ----------------------------------------------------
        # Bersihkan thinking
        # ----------------------------------------------------

        content = clean_thinking(content)

        if not content:

            raise OllamaResponseError(
                "Ollama mengembalikan balasan kosong."
            )

        return content

    # ========================================================
    # TOOL CALLING (PHASE 6F)
    # ========================================================

    def decide_tool_call(
        self,
        messages: List[ChatMessage],
        tools: List[Dict[str, Any]],
    ) -> Optional[ToolCallRequest]:
        """
        Menanyakan ke model apakah salah satu `tools` diperlukan untuk
        membalas percakapan sejauh ini, menggunakan native tool-calling
        Ollama (bukan dengan menebak dari teks bebas model — ATURAN
        UTAMA #12).

        Mengembalikan None jika:
        - tidak ada tool yang tersedia,
        - model memutuskan tidak perlu tool sama sekali (RIN akan
          menjawab normal seperti biasa, PHASE 6F), atau
        - terjadi masalah apa pun saat proses keputusan ini (koneksi,
          format tidak dikenal, dsb). Ini SENGAJA tidak melempar
          exception, supaya kegagalan pada langkah opsional ini tidak
          pernah membuat chat biasa (tanpa tool) ikut gagal; error
          Ollama yang sesungguhnya akan tetap muncul seperti biasa pada
          panggilan chat()/chat_stream() berikutnya.
        """
        if not tools:
            return None

        payload = [
            {"role": message.role, "content": message.content}
            for message in messages
        ]

        try:
            response = self._client.chat(
                model=self.model,
                messages=payload,
                tools=tools,
                think=False,
                stream=False,
            )
        except TypeError:
            try:
                response = self._client.chat(
                    model=self.model,
                    messages=payload,
                    tools=tools,
                    stream=False,
                )
            except Exception as exc:
                logger.warning("Tool-call decision gagal (compat lama): %s", exc)
                return None
        except Exception as exc:
            # Mencakup ResponseError, error koneksi/timeout, dan lainnya.
            # Lihat docstring: sengaja tidak di-raise ulang di sini.
            logger.warning("Tool-call decision gagal, lanjut tanpa tool: %s", exc)
            return None

        return self._extract_tool_call(response)

    @staticmethod
    def _extract_tool_call(response: Any) -> Optional[ToolCallRequest]:
        """Mengekstrak tool_call pertama dari response Ollama, jika ada."""

        try:
            tool_calls = response.message.tool_calls
        except AttributeError:
            try:
                tool_calls = response["message"].get("tool_calls")
            except (KeyError, TypeError):
                tool_calls = None

        if not tool_calls:
            return None

        first_call = tool_calls[0]

        try:
            function = first_call.function
            name = function.name
            arguments = function.arguments
        except AttributeError:
            try:
                function = first_call["function"]
                name = function["name"]
                arguments = function.get("arguments", {})
            except (KeyError, TypeError):
                logger.warning("Format tool_call dari Ollama tidak dikenali.")
                return None

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}

        if not isinstance(arguments, dict):
            arguments = {}

        if not name:
            return None

        return ToolCallRequest(name=name, arguments=arguments)

    # ========================================================
    # STREAMING
    # ========================================================

    def chat_stream(
        self,
        messages: List[ChatMessage],
    ) -> Iterator[str]:

        payload = [
            {
                "role": message.role,
                "content": message.content,
            }
            for message in messages
        ]

        try:

            stream = self._client.chat(
                model=self.model,
                messages=payload,
                think=False,
                stream=True,
            )

        except TypeError:

            try:

                stream = self._client.chat(
                    model=self.model,
                    messages=payload,
                    stream=True,
                )

            except Exception as exc:
                self._raise_generic(exc)
                return

        except ResponseError as exc:

            self._raise_response_error(exc)
            return

        except (httpx.ConnectError, ConnectionError) as exc:

            raise OllamaConnectionError(
                f"Koneksi ke Ollama di {self.host} gagal."
            ) from exc

        except httpx.TimeoutException as exc:

            raise OllamaTimeoutError(
                f"Request Ollama melebihi {self.timeout_seconds} detik."
            ) from exc

        except Exception as exc:

            self._raise_generic(exc)
            return

        # ----------------------------------------------------
        # THINKING FILTER
        # ----------------------------------------------------

        thinking_filter = ThinkingStreamFilter()

        full_reply = ""

        try:

            for part in stream:

                try:

                    raw_chunk = part.message.content

                except AttributeError:

                    try:
                        raw_chunk = part["message"]["content"]

                    except (KeyError, TypeError) as exc:

                        raise OllamaResponseError(
                            "Chunk Ollama tidak dapat dibaca."
                        ) from exc

                if not raw_chunk:
                    continue

                visible = thinking_filter.feed(raw_chunk)

                if visible:

                    full_reply += visible

                    yield visible

        except ResponseError as exc:

            self._raise_response_error(exc)

        except (httpx.ConnectError, ConnectionError) as exc:

            raise OllamaConnectionError(
                "Koneksi Ollama terputus."
            ) from exc

        except httpx.TimeoutException as exc:

            raise OllamaTimeoutError(
                "Streaming Ollama timeout."
            ) from exc

        except OllamaError:
            raise

        except Exception as exc:

            self._raise_generic(exc)

        # ----------------------------------------------------
        # FLUSH BUFFER
        # ----------------------------------------------------

        final_chunk = thinking_filter.finish()

        if final_chunk:

            full_reply += final_chunk

            yield final_chunk

        if not full_reply.strip():

            raise OllamaResponseError(
                "Ollama tidak menghasilkan jawaban."
            )

    # ========================================================
    # ERROR HANDLING
    # ========================================================

    def _raise_response_error(
        self,
        exc: ResponseError,
    ) -> None:

        status_code = getattr(
            exc,
            "status_code",
            None,
        )

        if status_code == 404:

            raise OllamaModelNotFoundError(
                f"Model '{self.model}' tidak ditemukan. "
                f"Jalankan: ollama pull {self.model}"
            ) from exc

        raise OllamaResponseError(
            f"Ollama mengembalikan error: {exc}"
        ) from exc

    def _raise_generic(
        self,
        exc: Exception,
    ) -> None:

        logger.error(
            "Kesalahan Ollama: %s",
            exc,
        )

        raise OllamaError(
            f"Terjadi kesalahan saat menghubungi Ollama: {exc}"
        ) from exc