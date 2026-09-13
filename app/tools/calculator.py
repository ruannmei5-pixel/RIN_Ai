"""
calculator.py

Tool calculator untuk RIN (PHASE 6B).

KEAMANAN (ATURAN UTAMA #10): tool ini TIDAK PERNAH menggunakan eval()
atau exec(). Ekspresi divalidasi karakternya terlebih dahulu, lalu
di-parse dengan modul `ast` bawaan Python dan dievaluasi manual node per
node, hanya untuk operasi aritmatika yang secara eksplisit diizinkan
(+, -, *, /, %, **, (), unary +/-). Node lain (pemanggilan fungsi, nama
variabel, atribut, dsb.) langsung ditolak.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Dict, Union

from app.tools.registry import Tool, ToolPermission, ToolValidationError

_MAX_EXPRESSION_LENGTH = 200
_MAX_EXPONENT = 1000
_MAX_ABS_RESULT = 1e15

_ALLOWED_CHARS = set("0123456789+-*/%().eE \t")

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

Number = Union[int, float]


def _eval_node(node: ast.AST) -> Number:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ToolValidationError("Ekspresi hanya boleh berisi angka.")
        return node.value

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        func = _BINOPS.get(op_type)
        if func is None:
            raise ToolValidationError("Operator tidak diizinkan.")

        left = _eval_node(node.left)
        right = _eval_node(node.right)

        if op_type is ast.Pow and abs(right) > _MAX_EXPONENT:
            raise ToolValidationError("Pangkat terlalu besar untuk dihitung dengan aman.")
        if op_type in (ast.Div, ast.Mod) and right == 0:
            raise ToolValidationError("Tidak bisa membagi dengan nol.")

        try:
            result = func(left, right)
        except OverflowError as exc:
            raise ToolValidationError("Hasil perhitungan terlalu besar.") from exc

        if isinstance(result, complex) or abs(result) > _MAX_ABS_RESULT:
            raise ToolValidationError("Hasil perhitungan terlalu besar.")

        return result

    if isinstance(node, ast.UnaryOp):
        func = _UNARYOPS.get(type(node.op))
        if func is None:
            raise ToolValidationError("Operator tidak diizinkan.")
        return func(_eval_node(node.operand))

    raise ToolValidationError("Ekspresi mengandung elemen yang tidak diizinkan.")


def safe_calculate(expression: str) -> Number:
    """
    Menghitung ekspresi aritmatika sederhana dengan aman.

    Raises:
        ToolValidationError: jika ekspresi kosong, terlalu panjang,
            berisi karakter/operator yang tidak diizinkan, atau hasilnya
            tidak masuk akal (mis. pembagian nol, pangkat ekstrem).
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ToolValidationError("RIN tidak dapat menghitung ekspresi tersebut.")

    expression = expression.strip()

    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ToolValidationError("Ekspresi terlalu panjang.")

    # Validasi karakter SEBELUM parsing, sebagai lapisan pertahanan
    # tambahan di luar ast.parse().
    if not set(expression) <= _ALLOWED_CHARS:
        raise ToolValidationError("RIN tidak dapat menghitung ekspresi tersebut.")

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ToolValidationError("RIN tidak dapat menghitung ekspresi tersebut.") from exc

    return _eval_node(tree)


def _format_number(value: Number) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


def _handle(arguments: Dict[str, Any]) -> str:
    expression = arguments.get("expression", "")

    try:
        result = safe_calculate(expression)
    except ToolValidationError as exc:
        return str(exc)

    return f"Hasil dari {str(expression).strip()} adalah {_format_number(result)}."


def calculator_tool() -> Tool:
    return Tool(
        name="calculator",
        description=(
            "Menghitung ekspresi matematika dasar: penjumlahan, pengurangan, "
            "perkalian, pembagian, modulo, tanda kurung, dan pangkat. "
            "Gunakan HANYA untuk pertanyaan berhitung, bukan untuk teks biasa."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Ekspresi matematika yang akan dihitung, contoh: "
                        "'125 * 8' atau '(2 + 3) ** 2'."
                    ),
                }
            },
            "required": ["expression"],
        },
        permission=ToolPermission.SAFE,
        handler=_handle,
        status_message="⚙️ RIN menggunakan Calculator...",
    )
