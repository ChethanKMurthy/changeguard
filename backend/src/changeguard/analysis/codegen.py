"""Deterministic test-skeleton generation for suggested tests.

Skeletons only use names that exist in the analysed code (symbols, parameters,
module paths). Values the tool cannot know are left as explicit ``...``
placeholders rather than invented.
"""

from __future__ import annotations

import posixpath
import re

from changeguard.languages.model import LanguageId, Signature, Symbol

_SOURCE_ROOTS = ("src/", "lib/", "app/")


def python_module(path: str) -> str:
    stem = path[:-3] if path.endswith(".py") else path.rsplit(".", 1)[0]
    for root in _SOURCE_ROOTS[:2]:
        if stem.startswith(root):
            stem = stem[len(root) :]
            break
    module = stem.replace("/", ".")
    return module[: -len(".__init__")] if module.endswith(".__init__") else module


def js_module(path: str) -> str:
    stem = path.rsplit(".", 1)[0]
    if stem.endswith("/index"):
        stem = stem[: -len("/index")]
    return "./" + stem if not stem.startswith(".") else stem


def snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return re.sub(r"[^a-z0-9_]+", "_", s).strip("_") or "behaviour"


def call_expression(symbol: Symbol, *, language: LanguageId, keyword_style: bool = True) -> str:
    """Render a call using the symbol's real parameter names and `...` placeholders."""
    sig = symbol.signature or Signature(())
    params = list(sig.params)
    if symbol.kind == "method" and params and params[0].name in ("self", "cls"):
        params = params[1:]
    target = symbol.name
    if symbol.kind == "method" and symbol.parent:
        target = f"{snake(symbol.parent.rsplit('.', 1)[-1])}.{symbol.name}"
    if symbol.name in ("__init__", "constructor") and symbol.parent:
        target = symbol.parent.rsplit(".", 1)[-1]
        if language is not LanguageId.PYTHON:
            target = f"new {target}"
    args: list[str] = []
    for p in params:
        if p.kind in ("var_positional", "var_keyword"):
            continue
        if language is LanguageId.PYTHON and keyword_style and p.kind != "positional_only":
            args.append(f"{p.name}=...")
        else:
            args.append("..." if language is LanguageId.PYTHON else f"/* {p.name} */ undefined")
    prefix = "await " if sig.is_async else ""
    return f"{prefix}{target}({', '.join(args)})"


def import_line(symbol: Symbol, path: str, language: LanguageId) -> str:
    top = symbol.parent.split(".")[0] if symbol.parent else symbol.name
    if language is LanguageId.PYTHON:
        return f"from {python_module(path)} import {top}"
    return f'import {{ {top} }} from "{js_module(path)}"; // adjust the path to the test location'


def regression_test(
    symbol: Symbol,
    path: str,
    language: LanguageId,
    *,
    purpose: str,
    body_comment: str,
    assertion: str | None = None,
) -> str:
    call = call_expression(symbol, language=language)
    test_name = snake(f"{symbol.name}_{purpose}")
    if language is LanguageId.PYTHON:
        is_async = bool(symbol.signature and symbol.signature.is_async)
        lines = [import_line(symbol, path, language), ""]
        if is_async:
            lines += ["import pytest", "", "", "@pytest.mark.asyncio"]
        else:
            lines.append("")
        lines.append(f"{'async ' if is_async else ''}def test_{test_name}():")
        lines.append(f"    # {body_comment}")
        if symbol.kind == "method" and symbol.name != "__init__" and symbol.parent:
            cls = symbol.parent.rsplit(".", 1)[-1]
            lines.append(
                f"    {snake(cls)} = {cls}(...)  # construct with representative arguments"
            )
        lines.append(f"    result = {call}")
        lines.append(
            f"    {assertion or 'assert result == ...  # expected value for these inputs'}"
        )
        return "\n".join(lines)
    is_async = bool(symbol.signature and symbol.signature.is_async)
    lines = [
        import_line(symbol, path, language),
        "",
        f'test("{symbol.name} {purpose.replace("_", " ")}", {"async " if is_async else ""}() => {{',
    ]
    lines.append(f"  // {body_comment}")
    lines.append(f"  const result = {call};")
    lines.append(f"  {assertion or 'expect(result).toEqual(/* expected value */ undefined);'}")
    lines.append("});")
    return "\n".join(lines)


def relative_test_hint(path: str, language: LanguageId) -> str:
    directory, name = posixpath.split(path)
    stem = name.rsplit(".", 1)[0]
    if language is LanguageId.PYTHON:
        return f"tests/test_{stem}.py"
    ext = name.rsplit(".", 1)[-1]
    return posixpath.join(directory, f"{stem}.test.{ext}")
