"""
main.py

Entry point aplikasi RIN.

Phase 1:
- CLI
- Ollama
- Qwen3 4B
- streaming response
- hidden thinking
"""

from __future__ import annotations

from app.core.assistant import Assistant
from app.core.config import ConfigError, load_config
from app.core.logger import get_logger
from app.llm.ollama_client import (
    OllamaConnectionError,
    OllamaError,
    OllamaModelNotFoundError,
    OllamaResponseError,
    OllamaTimeoutError,
)


logger = get_logger()

_EXIT_COMMANDS = {
    "exit",
    "quit",
    "keluar",
}


def print_banner(
    assistant_name: str,
    assistant_full_name: str,
) -> None:

    line = "=" * 40

    print()
    print(line)
    print(f" {assistant_name}")
    print(f" {assistant_full_name}")
    print(line)
    print()


def handle_ollama_error(
    exc: OllamaError,
) -> None:
    """
    Menampilkan error yang mudah dipahami user.
    Detail tetap masuk ke log.
    """

    if isinstance(
        exc,
        OllamaConnectionError,
    ):

        print(
            "\nRIN: Aku tidak bisa terhubung "
            "ke Ollama.\n"
            "Pastikan Ollama sedang berjalan.\n"
        )

    elif isinstance(
        exc,
        OllamaTimeoutError,
    ):

        print(
            "\nRIN: Prosesnya terlalu lama. "
            "Coba lagi sebentar.\n"
        )

    elif isinstance(
        exc,
        OllamaModelNotFoundError,
    ):

        print(
            "\nRIN: Model Ollama yang digunakan "
            "tidak ditemukan.\n"
            "Periksa config/config.json "
            "dan jalankan 'ollama list'.\n"
        )

    elif isinstance(
        exc,
        OllamaResponseError,
    ):

        print(
            "\nRIN: Aku menerima response "
            "yang tidak bisa diproses.\n"
        )

    else:

        print(
            "\nRIN: Terjadi kesalahan "
            "saat menghubungi Ollama.\n"
        )

    logger.error(
        "Ollama error: %s",
        exc,
    )


def main() -> None:

    # ========================================================
    # LOAD CONFIG
    # ========================================================

    try:

        config = load_config()

    except ConfigError as exc:

        print(
            "RIN: Gagal memuat konfigurasi."
        )

        print(exc)

        logger.error(
            "ConfigError: %s",
            exc,
        )

        return

    # ========================================================
    # BANNER
    # ========================================================

    print_banner(
        config.assistant_name,
        config.assistant_full_name,
    )

    # ========================================================
    # INITIALIZE ASSISTANT
    # ========================================================

    try:

        assistant = Assistant(config)

    except Exception as exc:

        print(
            "RIN: Gagal menyiapkan assistant."
        )

        print(
            "Cek logs/rin.log untuk detail."
        )

        logger.exception(
            "Gagal inisialisasi Assistant: %s",
            exc,
        )

        return

    logger.info(
        "RIN dimulai dengan model '%s' "
        "di host '%s'",
        config.ollama.model,
        config.ollama.host,
    )

    # ========================================================
    # MAIN LOOP
    # ========================================================

    while True:

        try:

            user_input = input(
                "You: "
            ).strip()

        except (
            EOFError,
            KeyboardInterrupt,
        ):

            print(
                "\nRIN: Sampai jumpa!"
            )

            break

        if not user_input:
            continue

        # ----------------------------------------------------
        # EXIT
        # ----------------------------------------------------

        if user_input.lower() in _EXIT_COMMANDS:

            print(
                "RIN: Sampai jumpa!"
            )

            break

        # ----------------------------------------------------
        # STREAM RESPONSE
        # ----------------------------------------------------

        try:

            print(
                "\nRIN: ",
                end="",
                flush=True,
            )

            response_received = False

            for chunk in assistant.ask_stream(
                user_input
            ):

                response_received = True

                print(
                    chunk,
                    end="",
                    flush=True,
                )

            print(
                "\n"
            )

            if not response_received:

                print(
                    "RIN: Aku belum mendapatkan "
                    "jawaban dari model.\n"
                )

        except OllamaError as exc:

            # Karena "RIN: " sudah dicetak sebelum
            # error, beri newline agar tampilan tetap rapi.

            print()

            handle_ollama_error(
                exc
            )

        except KeyboardInterrupt:

            print(
                "\n\nRIN: Proses dihentikan."
            )

        except Exception as exc:

            print(
                "\nRIN: Maaf, terjadi "
                "kesalahan tak terduga."
            )

            print(
                "Detail sudah dicatat di log."
            )

            logger.exception(
                "Kesalahan tak terduga: %s",
                exc,
            )


if __name__ == "__main__":
    main()