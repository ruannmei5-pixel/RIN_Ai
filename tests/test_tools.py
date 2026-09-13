"""
test_tools.py

Unit test untuk Tool System PHASE 6. Test ini TIDAK membutuhkan Ollama
sama sekali (murni logic Python), sehingga selalu berjalan di CI/tanpa
Ollama.
"""

from __future__ import annotations

import pytest

from app.tools.calculator import calculator_tool, safe_calculate
from app.tools.datetime_tool import datetime_tool
from app.tools.files import file_reader_tool, resolve_safe_path, WORKSPACE_DIR
from app.tools.registry import ToolManager, ToolValidationError, build_default_tool_manager
from app.tools.system import system_info_tool


# ============================================================
# CALCULATOR
# ============================================================

def test_calculator_basic_operations() -> None:
    assert safe_calculate("125 * 8") == 1000
    assert safe_calculate("10 / 4") == 2.5
    assert safe_calculate("(2 + 3) * 4") == 20
    assert safe_calculate("2 ** 10") == 1024
    assert safe_calculate("10 % 3") == 1


def test_calculator_rejects_division_by_zero() -> None:
    with pytest.raises(ToolValidationError):
        safe_calculate("5 / 0")


def test_calculator_rejects_non_arithmetic_input() -> None:
    # Tidak boleh ada eval() sama sekali: input berbahaya harus ditolak
    # sebagai ekspresi tidak valid, bukan dieksekusi.
    for dangerous in [
        "__import__('os').system('echo hacked')",
        "open('/etc/passwd').read()",
        "1; import os",
        "[].__class__",
    ]:
        with pytest.raises(ToolValidationError):
            safe_calculate(dangerous)


def test_calculator_tool_handles_invalid_expression_gracefully() -> None:
    tool = calculator_tool()
    result = tool.handler({"expression": "2 + "})
    assert "tidak dapat menghitung" in result.lower()


def test_calculator_tool_end_to_end() -> None:
    tool = calculator_tool()
    result = tool.handler({"expression": "123 * 45"})
    assert "5535" in result


# ============================================================
# DATETIME
# ============================================================

def test_datetime_tool_returns_nonempty_string() -> None:
    tool = datetime_tool()
    result = tool.handler({})
    assert isinstance(result, str)
    assert len(result) > 0


# ============================================================
# SYSTEM INFO
# ============================================================

def test_system_info_tool_is_read_only_and_returns_text() -> None:
    tool = system_info_tool()
    result = tool.handler({})
    assert isinstance(result, str)
    assert "OS" in result


# ============================================================
# FILE READER — sandbox & path traversal
# ============================================================

def test_file_reader_rejects_path_traversal() -> None:
    with pytest.raises(ToolValidationError):
        resolve_safe_path("../../secret.txt")

    with pytest.raises(ToolValidationError):
        resolve_safe_path("..\\..\\secret.txt")


def test_file_reader_rejects_absolute_path() -> None:
    with pytest.raises(ToolValidationError):
        resolve_safe_path("/etc/passwd")


def test_file_reader_rejects_disallowed_extension() -> None:
    with pytest.raises(ToolValidationError):
        resolve_safe_path("script.py")


def test_file_reader_rejects_sensitive_filename() -> None:
    with pytest.raises(ToolValidationError):
        resolve_safe_path("password.txt")


def test_file_reader_reads_file_inside_workspace(tmp_path, monkeypatch) -> None:
    # Arahkan WORKSPACE_DIR ke folder sementara supaya test tidak
    # menyentuh workspace/ production.
    monkeypatch.setattr("app.tools.files.WORKSPACE_DIR", tmp_path)

    note_path = tmp_path / "catatan.txt"
    note_path.write_text("halo dari test", encoding="utf-8")

    tool = file_reader_tool()
    result = tool.handler({"filename": "catatan.txt"})
    assert "halo dari test" in result


def test_file_reader_tool_denied_traversal_via_handler(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.tools.files.WORKSPACE_DIR", tmp_path)

    tool = file_reader_tool()
    result = tool.handler({"filename": "../../secret.txt"})
    assert "workspace" in result.lower()


# ============================================================
# TOOL MANAGER / REGISTRY
# ============================================================

def test_tool_manager_execute_unknown_tool_does_not_raise() -> None:
    manager = ToolManager()
    result = manager.execute("tidak_ada", {})
    assert result.success is False


def test_tool_manager_can_disable_tool() -> None:
    manager = build_default_tool_manager()
    manager.set_enabled("file_reader", False)

    schemas = manager.ollama_schemas()
    names = [schema["function"]["name"] for schema in schemas]
    assert "file_reader" not in names
    assert "calculator" in names

    result = manager.execute("file_reader", {"filename": "catatan.txt"})
    assert result.success is False


def test_build_default_tool_manager_registers_all_phase6_tools() -> None:
    manager = build_default_tool_manager()
    names = {tool.name for tool in manager.all_tools()}
    assert names == {"calculator", "datetime", "system_info", "file_reader"}
