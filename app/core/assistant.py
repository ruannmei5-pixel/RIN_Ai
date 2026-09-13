"""
assistant.py

Kelas inti Assistant (RIN).

Tanggung jawab kelas ini:
- Membangun system prompt kepribadian RIN (lihat app/core/personality.py).
- Memuat riwayat percakapan dari SQLite (app/core/memory.py) sebagai
  context awal, dibatasi jumlahnya agar tidak mengirim seluruh database
  tanpa batas ke Ollama (PHASE 3, poin 4).
- Menyimpan setiap giliran percakapan (user + assistant) yang BERHASIL
  ke SQLite, sehingga RIN tetap mengingat percakapan setelah program
  ditutup dan dibuka kembali (PHASE 3, poin 3).
- Mengirim pesan user ke Ollama melalui OllamaClient (mode biasa maupun
  streaming).
- Mengembalikan teks balasan ke pemanggil (main.py / GUI nanti).

Catatan penting soal memory (PHASE 3, poin 4 & 5 & 6):
- System prompt TIDAK PERNAH disimpan ke SQLite; ia dibangun ulang setiap
  kali Assistant dibuat, dari app/core/personality.py.
- Jika request ke Ollama gagal, giliran user TIDAK disimpan ke history
  in-memory maupun ke SQLite, supaya riwayat tidak "pincang".
- Balasan kosong tidak pernah disimpan (OllamaClient sudah menjamin ini
  dengan melempar OllamaResponseError sebelum balasan kosong sampai ke sini).
- Semua error dicatat ke logger sebelum di-raise ulang ke caller.
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from app.core.memory import Memory

from app.core.config import AppConfig
from app.core.logger import get_logger
from app.core.personality import build_system_prompt
from app.core.router import matches_system_info
from app.llm.ollama_client import (
    ChatMessage,
    OllamaClient,
    OllamaError,
    OllamaResponseError,
)
from app.tools.registry import ToolManager, build_default_tool_manager

logger = get_logger()

# Batas jumlah pesan (user+assistant) yang dimuat dari SQLite sekaligus
# dikirim sebagai context ke Ollama. Nilai ini sengaja dijaga wajar
# (tidak mengirim seluruh database) sesuai PHASE 3 poin 4.
MAX_CONTEXT_MESSAGES = 20


class Assistant:
    """
    Orkestrator utama RIN: personality + SQLite memory + Ollama + streaming.
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.client = OllamaClient(
            host=config.ollama.host,
            model=config.ollama.model,
            timeout_seconds=config.ollama.timeout_seconds,
        )

        # Memory persisten berbasis SQLite (lihat app/core/memory.py).
        self.memory = Memory()

        # Tool Manager (PHASE 6A): satu-satunya jalan RIN menjalankan
        # tools. Tool yang dinonaktifkan lewat config/config.json
        # ("tools": {"nama_tool": false}) tidak pernah ditawarkan ke
        # model (ATURAN UTAMA #16).
        self.tools: ToolManager = build_default_tool_manager()
        for tool_name, tool_enabled in config.tools_enabled.items():
            self.tools.set_enabled(tool_name, tool_enabled)

        # System prompt dibangun dari modul personality, BUKAN disimpan
        # sebagai memory user/assistant.
        system_prompt = build_system_prompt(config)

        self._history: List[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt)
        ]

        # Muat percakapan sebelumnya dari SQLite sebagai context awal,
        # dibatasi MAX_CONTEXT_MESSAGES agar tidak mengirim seluruh
        # database tanpa batas ke Ollama.
        for role, content in self.memory.get_recent_messages(limit=MAX_CONTEXT_MESSAGES):
            self._history.append(ChatMessage(role=role, content=content))

    def _trim_history(self) -> None:
        """
        Menjaga _history tetap wajar selama sesi berjalan: system prompt
        (indeks 0) selalu dipertahankan, sisanya dipotong ke
        MAX_CONTEXT_MESSAGES pesan terakhir. Ini mencegah _history
        membengkak tanpa batas pada sesi yang sangat panjang.
        """
        if len(self._history) > MAX_CONTEXT_MESSAGES + 1:
            system_message = self._history[0]
            recent = self._history[-MAX_CONTEXT_MESSAGES:]
            self._history = [system_message] + recent

    def _run_tool_and_format(self, tool_name: str, arguments: Optional[dict] = None) -> str:
        """
        Menjalankan satu tool lewat ToolManager dan memformat hasilnya
        persis seperti alur tool-calling biasa (status_message +
        result.output). Dipakai baik oleh jalur deterministic router
        (PHASE 7.1) maupun jalur keputusan tool via LLM (PHASE 6F),
        supaya keduanya menghasilkan format balasan yang konsisten dan
        logging (ToolManager.execute) tetap sama persis.
        """
        tool = self.tools.get(tool_name)
        result = self.tools.execute(tool_name, arguments or {})

        status_message = tool.status_message if tool and tool.status_message else (
            f"⚙️ RIN menggunakan {tool_name}..."
        )

        return f"{status_message}\n\n{result.output}"

    def _decide_and_run_tool(self) -> Optional[str]:
        """
        Menentukan apakah tool diperlukan untuk membalas giliran user
        yang terakhir di `self._history`, dan jika ya, menjalankannya
        lewat Tool Manager (PHASE 6F & 6G).

        PHASE 7.1: sebelum bertanya ke LLM sama sekali, method ini
        lebih dulu mengecek apakah pesan user adalah permintaan
        `system_info` yang jelas (lihat app/core/router.py). Jika ya,
        `system_info` dipanggil LANGSUNG tanpa melibatkan Ollama untuk
        tahap "tool selection" — ini menghilangkan penyebab utama
        "Tool-call decision gagal ... timed out" untuk pertanyaan
        sistem seperti CPU/RAM/disk/hostname, karena tahap yang
        sebelumnya timeout (satu request Ollama) sekarang dilewati
        sepenuhnya untuk kasus ini.

        Permintaan file (`file_reader` / `workspace_list`) TIDAK
        terpengaruh oleh perubahan ini: keduanya tetap lewat jalur
        tool-calling Ollama seperti sebelumnya (lihat
        `router.matches_system_info`, yang sengaja menolak pesan
        bernuansa file), karena keduanya sudah terbukti berhasil dan
        instruksi Phase 7.1 meminta perubahan seminimal mungkin.

        Returns:
            Teks balasan lengkap RIN (sudah termasuk indikator status
            tool singkat, PHASE 6L) jika tool dipakai; atau None jika
            RIN sebaiknya menjawab normal tanpa tool sama sekali.

        Tidak pernah melempar OllamaError: jika langkah keputusan tool
        gagal karena masalah Ollama, method ini kembali ke None supaya
        alur normal (self.client.chat / chat_stream) yang menangani
        error tersebut seperti biasa, persis seperti sebelum Phase 6.
        """
        last_user_text = ""
        if self._history and self._history[-1].role == "user":
            last_user_text = self._history[-1].content

        system_info_tool = self.tools.get("system_info")
        if (
            system_info_tool is not None
            and system_info_tool.enabled
            and matches_system_info(last_user_text)
        ):
            return self._run_tool_and_format("system_info")

        tool_schemas = self.tools.ollama_schemas()
        if not tool_schemas:
            return None

        decision = self.client.decide_tool_call(self._history, tool_schemas)
        if decision is None:
            return None

        return self._run_tool_and_format(decision.name, decision.arguments)

    def ask(self, user_input: str) -> str:
        """
        Mengirim input user ke model dan mengembalikan balasan teks.

        Riwayat percakapan yang berhasil disimpan baik ke _history
        (untuk sesi berjalan) maupun ke SQLite (untuk sesi berikutnya).

        Args:
            user_input: Teks yang diketik oleh pengguna.

        Returns:
            Teks balasan dari RIN.

        Raises:
            OllamaError: jika terjadi masalah saat berkomunikasi dengan Ollama.
                Caller (main.py) bertanggung jawab menampilkan pesan yang
                ramah kepada user berdasarkan exception ini.
        """
        self._history.append(ChatMessage(role="user", content=user_input))

        try:
            tool_reply = self._decide_and_run_tool()
            reply = tool_reply if tool_reply is not None else self.client.chat(self._history)
        except OllamaError as exc:
            # Jangan simpan giliran user ke history jika gagal mendapat balasan,
            # supaya history tidak "pincang" (user message tanpa balasan).
            self._history.pop()
            logger.error("Gagal mendapatkan balasan dari Ollama (ask): %s", exc)
            raise

        self._history.append(ChatMessage(role="assistant", content=reply))
        self._trim_history()

        # Simpan ke SQLite HANYA setelah balasan berhasil didapat.
        self.memory.add_message("user", user_input)
        self.memory.add_message("assistant", reply)

        return reply

    def ask_stream(self, user_input: str) -> Iterator[str]:
        """
        Sama seperti `ask()`, tetapi menghasilkan (yield) potongan balasan
        secara bertahap (streaming) begitu diterima dari Ollama, alih-alih
        menunggu seluruh jawaban selesai.

        Hanya jawaban final (bukan reasoning/thinking internal) yang pernah
        ter-yield ke pemanggil; penyaringan dilakukan di `OllamaClient`.
        Riwayat percakapan (in-memory maupun SQLite) hanya diisi dengan
        jawaban final yang utuh setelah streaming selesai, sama seperti
        pada `ask()`.

        Args:
            user_input: Teks yang diketik oleh pengguna.

        Yields:
            Potongan teks (str) dari balasan RIN, sesuai urutan kemunculan.

        Raises:
            OllamaError: jika terjadi masalah saat berkomunikasi dengan Ollama
                (termasuk saat streaming terputus di tengah jalan). Caller
                (main.py / GUI) bertanggung jawab menampilkan pesan yang
                ramah kepada user berdasarkan exception ini.
        """
        self._history.append(ChatMessage(role="user", content=user_input))

        reply_parts: List[str] = []
        try:
            tool_reply = self._decide_and_run_tool()
            if tool_reply is not None:
                # Tool tidak benar-benar "streaming" (hasilnya sudah utuh),
                # tapi tetap dikirim lewat mekanisme yield yang sama supaya
                # caller (CLI, API) tidak perlu tahu bedanya.
                reply_parts.append(tool_reply)
                yield tool_reply
            else:
                for chunk in self.client.chat_stream(self._history):
                    reply_parts.append(chunk)
                    yield chunk
        except BaseException as exc:
            # Mencakup OllamaError maupun interupsi (mis. KeyboardInterrupt):
            # jangan simpan giliran user ke history jika balasan tidak
            # selesai, supaya history tidak "pincang" (user message tanpa
            # balasan assistant).
            self._history.pop()
            if isinstance(exc, OllamaError):
                logger.error("Gagal mendapatkan balasan dari Ollama (ask_stream): %s", exc)
            raise

        full_reply = "".join(reply_parts).strip()

        if not full_reply:
            self._history.pop()
            logger.error("Ollama mengembalikan balasan kosong (ask_stream).")
            raise OllamaResponseError("Ollama mengembalikan balasan kosong.")

        self._history.append(ChatMessage(role="assistant", content=full_reply))
        self._trim_history()

        # Simpan ke SQLite HANYA setelah balasan berhasil dan tidak kosong.
        self.memory.add_message("user", user_input)
        self.memory.add_message("assistant", full_reply)
