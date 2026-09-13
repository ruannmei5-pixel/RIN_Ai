"""
test_router.py

Unit test untuk deterministic keyword router PHASE 7.1
(app/core/router.py). Murni logic Python, tidak butuh Ollama.
"""

from __future__ import annotations

import pytest

from app.core.router import matches_system_info


@pytest.mark.parametrize(
    "text",
    [
        "RIN, berapa CPU saya?",
        "berapa RAM laptop saya?",
        "informasi sistem laptop ini apa saja?",
        "berapa penggunaan disk?",
        "hostname laptop saya?",
        "RIN, berapa penggunaan CPU sekarang?",
        "RIN, berapa RAM yang digunakan?",
        "spesifikasi laptop ini apa?",
        "spesifikasi komputer saya gimana?",
        "OS laptop saya apa?",
        "nama komputer saya apa?",
        "sistem operasi apa yang dipakai?",
        "berapa penyimpanan yang tersisa?",
        "info sistem dong",
    ],
)
def test_matches_system_info_true_cases(text: str) -> None:
    assert matches_system_info(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "RIN, apa itu Python?",
        "RIN, file apa saja yang ada di workspace?",
        "RIN, baca catatan.txt",
        "tolong ringkas dokumen.txt",
        "halo RIN, apa kabar?",
        "",
        "   ",
        # Kata pendek seperti "os"/"ram" tidak boleh salah cocok sebagai
        # substring di tengah kata lain.
        "aku lagi di posisi yang sulit",
        "program studi saya apa ya",
    ],
)
def test_matches_system_info_false_cases(text: str) -> None:
    assert matches_system_info(text) is False


def test_file_hint_overrides_system_info_keyword() -> None:
    """
    Permintaan yang menyebut file secara eksplisit TIDAK BOLEH direbut
    oleh router system_info, meskipun kebetulan juga menyebut kata
    seperti "info".
    """
    assert matches_system_info("RIN, baca info_sistem.txt") is False
