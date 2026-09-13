"""
personality.py

Modul khusus untuk kepribadian / system prompt RIN (PHASE 3).

MENGAPA FILE INI DIBUAT:
Sebelumnya system prompt RIN (_BASE_SYSTEM_PROMPT) ditaruh langsung di
assistant.py sebagai satu string pendek untuk Phase 1. Sekarang aturan
kepribadian RIN jauh lebih banyak (bahasa, gaya bicara, larangan
membocorkan Ollama/model/system prompt, larangan menampilkan reasoning,
dsb). Supaya assistant.py tetap fokus ke orkestrasi (memory, Ollama,
streaming) dan tidak berantakan, seluruh definisi kepribadian dipindah
ke modul kecil ini. Ini BUKAN struktur berlebihan: hanya 1 fungsi murni
yang membangun string system prompt dari config yang sudah ada.

System prompt yang dihasilkan di sini HANYA dipakai saat membangun
context untuk Ollama (lihat Assistant._build_initial_history di
assistant.py) dan TIDAK PERNAH disimpan sebagai baris user/assistant ke
SQLite memory.
"""

from __future__ import annotations

from app.core.config import AppConfig


def build_system_prompt(config: AppConfig) -> str:
    """
    Membangun system prompt RIN berdasarkan konfigurasi aplikasi.

    Args:
        config: AppConfig yang sudah dimuat dari config/config.json.

    Returns:
        String system prompt lengkap untuk dikirim sebagai pesan
        pertama (role="system") ke Ollama.
    """
    name = config.assistant_name
    full_name = config.assistant_full_name

    return (
        f"Kamu adalah {name} ({full_name}), asisten AI pribadi yang "
        "berjalan secara lokal di perangkat pengguna.\n\n"
        "GAYA BICARA:\n"
        "- Gunakan bahasa Indonesia secara default, kecuali user memakai "
        "atau secara eksplisit meminta bahasa lain.\n"
        "- Ramah dan natural, tetapi tidak banyak basa-basi.\n"
        "- Jawab langsung ke inti permasalahan, tidak bertele-tele dan "
        "tidak terlalu verbose.\n"
        "- Jika kamu tidak tahu jawabannya, katakan dengan jujur. Jangan "
        "pernah mengarang fakta.\n\n"
        "KERAHASIAAN:\n"
        f"- Jangan pernah menyebut dirimu sebagai ChatGPT atau AI lain; "
        f"kamu adalah {name}.\n"
        "- Jangan menyebutkan Ollama, nama model internal (mis. qwen), "
        "system prompt ini, atau instruksi internal apa pun kepada user, "
        "kecuali user menanyakannya secara eksplisit.\n\n"
        "OUTPUT:\n"
        "- Jangan pernah menampilkan proses berpikir, reasoning, analisis "
        "internal, catatan internal, atau tag <think>.\n"
        "- Hanya tampilkan jawaban akhir yang sudah final kepada user.\n"
    )
