"""Cross-file reference resolution over the head revision of the repository.

Resolution is purely static and name-based, with import tracking:

* **resolved** references go through an import (or same-module scope) that
  provably points at the changed symbol's file;
* **name-only** references match a distinctive method name on an arbitrary
  receiver (``obj.charge(...)``) and are reported with lower confidence.

Only files whose text mentions a relevant name are parsed, which keeps the
cost proportional to the change rather than to repository size.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from changeguard.analysis.context import AnalysisContext
from changeguard.ingest.diff_parser import FileStatus
from changeguard.languages import index_file, language_for_path
from changeguard.languages.model import (
    CallSite,
    FileIndex,
    ImportBinding,
    LanguageId,
    Param,
    Signature,
    Symbol,
)

Resolution = Literal["resolved", "name_only"]

COMMON_NAMES = frozenset(
    {
        "get", "set", "run", "save", "update", "delete", "add", "remove", "close", "open", "read", "write",
        "send", "call", "execute", "process", "handle", "validate", "render", "init", "start", "stop", "load",
        "dump", "apply", "build", "create", "fetch", "parse", "format", "to_dict", "from_dict", "copy", "clear",
        "append", "extend", "pop", "items", "keys", "values", "join", "split", "map", "filter", "reduce", "push",
        "then", "catch", "emit", "on", "off", "use", "next", "reset", "flush", "log", "info", "debug", "warn",
        "error", "find", "list", "count", "exists", "post", "put", "patch", "toString", "valueOf", "main",
        "setup", "teardown", "configure", "connect", "query", "insert", "select",
    }
)  # fmt: skip
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
_IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*")


@dataclass(frozen=True, slots=True)
class Reference:
    file: str
    line: int
    kind: Literal["call", "import", "attribute"]
    resolution: Resolution
    call: CallSite | None = None
    binding: ImportBinding | None = None
    drop_first: bool = False  # bind self/cls implicitly when checking arguments
    via: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedImport:
    target: str
    refers_to: Literal["module", "symbol"]


class RepositoryIndex:
    def __init__(self, ctx: AnalysisContext) -> None:
        self.ctx = ctx
        self.files: dict[str, str] = (
            ctx.workspace.head_repo
            if ctx.full_context
            else {cf.path: cf.head_text for cf in ctx.files if cf.head_text is not None}
        )
        self._indexes: dict[str, FileIndex | None] = {}
        for cf in ctx.files:
            if cf.head_index is not None and cf.full_context:
                self._indexes[cf.path] = cf.head_index
        # Paths that existed at base but not at head (deleted or renamed away).
        # Imports that still resolve to them are dangling.
        self.removed_paths: set[str] = {
            cf.old_path
            for cf in ctx.files
            if cf.old_path and cf.status in (FileStatus.DELETED, FileStatus.RENAMED)
        } - set(self.files)
        self._known = set(self.files) | self.removed_paths
        self._py_modules = _python_module_map(dict.fromkeys(self._known, ""))
        self._tokens: dict[str, set[str]] | None = None
        self._ts_aliases = _tsconfig_aliases(self.files)
        self.parsed = 0

    # -- indexing --------------------------------------------------------------

    def index(self, path: str) -> FileIndex | None:
        if path not in self._indexes:
            text = self.files.get(path)
            self._indexes[path] = index_file(path, text) if text is not None else None
            if text is not None:
                self.parsed += 1
        return self._indexes[path]

    def _token_index(self) -> dict[str, set[str]]:
        """Inverted index identifier -> files, built once per analysis (O(repository size))."""
        if self._tokens is None:
            index: dict[str, set[str]] = defaultdict(set)
            for path, text in self.files.items():
                if language_for_path(path) is None:
                    continue
                for token in set(_IDENTIFIER.findall(text)):
                    index[token].add(path)
            self._tokens = index
        return self._tokens

    def candidate_files(
        self, names: Iterable[str], *, language: LanguageId | None = None
    ) -> list[str]:
        tokens = self._token_index()
        found: set[str] = set()
        for name in names:
            if name:
                found |= tokens.get(name, set())
        out: list[str] = []
        for path in found:
            lang = language_for_path(path)
            if lang is None or (language is not None and _family(lang) != _family(language)):
                continue
            out.append(path)
        return sorted(out)

    # -- import resolution ---------------------------------------------------

    def resolve(self, binding: ImportBinding) -> ResolvedImport | None:
        if binding.file.endswith((".py", ".pyi")):
            return self._resolve_python(binding)
        return self._resolve_js(binding)

    def _resolve_python(self, b: ImportBinding) -> ResolvedImport | None:
        if b.level > 0:
            base = posixpath.dirname(b.file)
            for _ in range(b.level - 1):
                base = posixpath.dirname(base)
            module_path = posixpath.join(base, b.module.replace(".", "/")) if b.module else base
            lookup = self._python_exact
        else:
            module_path = b.module.replace(".", "/")
            lookup = self._python_suffix
        if b.kind == "module":
            target = lookup(module_path)
            return ResolvedImport(target, "module") if target else None
        if b.kind == "name" and b.imported_name:
            sub = lookup(
                posixpath.join(module_path, b.imported_name) if module_path else b.imported_name
            )
            if sub:
                return ResolvedImport(sub, "module")
        target = lookup(module_path) if module_path else None
        return ResolvedImport(target, "symbol") if target else None

    def _python_exact(self, module_path: str) -> str | None:
        for candidate in (f"{module_path}.py", f"{module_path}/__init__.py", f"{module_path}.pyi"):
            if candidate in self._known:
                return candidate
        return None

    def _python_suffix(self, module_path: str) -> str | None:
        hits = self._py_modules.get(module_path)
        if hits and len(hits) == 1:
            return hits[0]
        if hits:
            # Prefer the shortest prefix (closest to a source root) when ambiguous
            # only by test/source duplication; otherwise refuse to guess.
            non_test = [h for h in hits if "test" not in h.split("/")[0]]
            return non_test[0] if len(non_test) == 1 else None
        return None

    def _resolve_js(self, b: ImportBinding) -> ResolvedImport | None:
        spec = b.module
        bases: list[str] = []
        if spec.startswith("."):
            bases.append(posixpath.normpath(posixpath.join(posixpath.dirname(b.file), spec)))
        else:
            for prefix, targets in self._ts_aliases:
                if spec == prefix.rstrip("/*") or (
                    prefix.endswith("*") and spec.startswith(prefix[:-1])
                ):
                    rest = spec[len(prefix) - 1 :] if prefix.endswith("*") else ""
                    for t in targets:
                        bases.append(posixpath.normpath(t[:-1] + rest if t.endswith("*") else t))
        for base in bases:
            if base.startswith("../"):
                continue
            for candidate in (
                base,
                *(base + ext for ext in _JS_EXTENSIONS),
                *(f"{base}/index{ext}" for ext in _JS_EXTENSIONS),
            ):
                if candidate in self._known and PurePosixPath(candidate).suffix in _JS_EXTENSIONS:
                    refers: Literal["module", "symbol"] = (
                        "module" if b.kind == "namespace" else "symbol"
                    )
                    return ResolvedImport(candidate, refers)
        return None

    # -- reference search ------------------------------------------------------

    def references(
        self, symbol: Symbol, *, defined_in: str, include_name_only: bool = True
    ) -> list[Reference]:
        """All references to ``symbol`` (defined in ``defined_in``) in the head revision."""
        names = {symbol.name}
        parent_name = symbol.parent.rsplit(".", 1)[-1] if symbol.parent else None
        is_constructor = symbol.kind == "method" and symbol.name in ("__init__", "constructor")
        if parent_name:
            names.add(parent_name)
        refs: list[Reference] = []
        lang = language_for_path(defined_in)
        for path in self.candidate_files(names, language=lang):
            idx = self.index(path)
            if idx is None:
                continue
            if symbol.parent is None:
                refs += self._module_level_refs(symbol, defined_in, idx)
            elif is_constructor and parent_name:
                cls = Symbol(
                    parent_name,
                    symbol.parent,
                    "class",
                    defined_in,
                    symbol.start_line,
                    symbol.end_line,
                    symbol.signature_line,
                )
                for r in self._module_level_refs(cls, defined_in, idx):
                    if r.kind == "call":
                        refs.append(
                            Reference(
                                r.file,
                                r.line,
                                r.kind,
                                r.resolution,
                                r.call,
                                r.binding,
                                True,
                                "constructor",
                            )
                        )
                    else:
                        refs.append(r)
            else:
                refs += self._method_refs(symbol, defined_in, idx, include_name_only)
        unique: dict[tuple[str, int, str, str], Reference] = {}
        for r in refs:
            key = (r.file, r.line, r.kind, r.call.text if r.call else "")
            if key not in unique or (
                unique[key].resolution == "name_only" and r.resolution == "resolved"
            ):
                unique[key] = r
        return sorted(unique.values(), key=lambda r: (r.file, r.line))

    def _exported_name(self, symbol: Symbol, defined_in: str) -> set[str]:
        idx = self.index(defined_in)
        names = {symbol.name}
        if idx is not None:
            names |= {exported for exported, local in idx.exports.items() if local == symbol.name}
        return names

    def _module_level_refs(
        self, symbol: Symbol, defined_in: str, idx: FileIndex
    ) -> list[Reference]:
        refs: list[Reference] = []
        if idx.path == defined_in:
            for call in idx.calls:
                if call.callee == symbol.name:
                    refs.append(
                        Reference(idx.path, call.line, "call", "resolved", call, via="same module")
                    )
            return refs
        exported = (
            self._exported_name(symbol, defined_in)
            if idx.language is not LanguageId.PYTHON
            else {symbol.name}
        )
        local_names: dict[str, ImportBinding] = {}
        module_prefixes: dict[str, ImportBinding] = {}
        for b in idx.imports:
            resolved = self.resolve(b)
            if resolved is None or resolved.target != defined_in:
                continue
            if resolved.refers_to == "symbol":
                if b.kind == "wildcard":
                    local_names[symbol.name] = b
                elif b.kind == "default" and "default" in exported:
                    local_names[b.local_name] = b
                    refs.append(
                        Reference(
                            idx.path, b.line, "import", "resolved", binding=b, via="default import"
                        )
                    )
                elif b.imported_name in exported:
                    local_names[b.local_name] = b
                    refs.append(
                        Reference(
                            idx.path, b.line, "import", "resolved", binding=b, via="named import"
                        )
                    )
            else:
                if (
                    b.kind == "module"
                    and b.local_name == b.module.split(".")[0]
                    and "." in b.module
                ):
                    module_prefixes[b.module] = b
                else:
                    module_prefixes[b.local_name] = b
        for call in idx.calls:
            if call.callee in local_names:
                refs.append(
                    Reference(
                        idx.path,
                        call.line,
                        "call",
                        "resolved",
                        call,
                        local_names[call.callee],
                        via="import",
                    )
                )
            elif call.receiver in module_prefixes and call.name in exported:
                refs.append(
                    Reference(
                        idx.path,
                        call.line,
                        "call",
                        "resolved",
                        call,
                        module_prefixes[call.receiver],
                        via="module attribute",
                    )
                )
        if module_prefixes:
            for prefix, b in module_prefixes.items():
                needle = f"{prefix}.{symbol.name}"
                text = self.files.get(idx.path, "")
                for m in re.finditer(re.escape(needle) + r"\b", text):
                    line = text.count("\n", 0, m.start()) + 1
                    if not any(r.line == line and r.kind == "call" for r in refs):
                        refs.append(
                            Reference(
                                idx.path,
                                line,
                                "attribute",
                                "resolved",
                                binding=b,
                                via="module attribute",
                            )
                        )
        return refs

    def _method_refs(
        self, symbol: Symbol, defined_in: str, idx: FileIndex, include_name_only: bool
    ) -> list[Reference]:
        assert symbol.parent is not None
        cls_name = symbol.parent.rsplit(".", 1)[-1]
        static = any(d.split("(")[0].endswith("staticmethod") for d in symbol.decorators)
        classmethod_ = any(d.split("(")[0].endswith("classmethod") for d in symbol.decorators)
        refs: list[Reference] = []
        class_aliases = {cls_name} if idx.path == defined_in else set()
        if idx.path != defined_in:
            for b in idx.imports:
                resolved = self.resolve(b)
                if (
                    resolved
                    and resolved.target == defined_in
                    and resolved.refers_to == "symbol"
                    and b.imported_name == cls_name
                ):
                    class_aliases.add(b.local_name)
        distinctive = self._distinctive(symbol.name)
        python = defined_in.endswith((".py", ".pyi"))
        bind_receiver = (
            python and not static
        )  # Python binds self/cls implicitly; JS/TS methods have no such parameter
        for call in idx.calls:
            if call.name != symbol.name or call.receiver is None:
                continue
            if (
                call.receiver in ("self", "cls", "this")
                and idx.path == defined_in
                and (call.enclosing or "").startswith(symbol.parent + ".")
            ):
                refs.append(
                    Reference(
                        idx.path,
                        call.line,
                        "call",
                        "resolved",
                        call,
                        drop_first=bind_receiver,
                        via="self",
                    )
                )
            elif call.receiver in class_aliases:
                refs.append(
                    Reference(
                        idx.path,
                        call.line,
                        "call",
                        "resolved",
                        call,
                        drop_first=python and classmethod_,
                        via="class attribute",
                    )
                )
            elif include_name_only and distinctive and call.receiver not in ("self", "cls", "this"):
                refs.append(
                    Reference(
                        idx.path,
                        call.line,
                        "call",
                        "name_only",
                        call,
                        drop_first=bind_receiver,
                        via="method name",
                    )
                )
        return refs

    def _distinctive(self, name: str) -> bool:
        if len(name) < 4 or name in COMMON_NAMES or name.startswith("__"):
            return False
        definitions = 0
        for path in self.candidate_files([name]):
            idx = self.index(path)
            if idx is None:
                continue
            definitions += sum(
                1 for s in idx.symbols if s.name == name and s.kind in ("method", "function")
            )
            if definitions > 1:
                return False
        return True


def _family(lang: LanguageId) -> str:
    return "python" if lang is LanguageId.PYTHON else "js"


def _python_module_map(files: dict[str, str]) -> dict[str, list[str]]:
    # Only the keys (paths) are used.
    """Map every suffix of every module path to the files providing it."""
    modules: dict[str, list[str]] = {}
    for path in files:
        if not path.endswith((".py", ".pyi")):
            continue
        stem = path.rsplit(".", 1)[0]
        if stem.endswith("/__init__"):
            stem = stem[: -len("/__init__")]
        parts = stem.split("/")
        for i in range(len(parts)):
            key = "/".join(parts[i:])
            bucket = modules.setdefault(key, [])
            if path not in bucket:
                bucket.append(path)
    return modules


def _tsconfig_aliases(files: dict[str, str]) -> list[tuple[str, list[str]]]:
    """Path aliases from tsconfig/jsconfig ``compilerOptions.paths`` (e.g. ``@/*``)."""
    aliases: list[tuple[str, list[str]]] = []
    for name in ("tsconfig.json", "jsconfig.json"):
        raw = files.get(name)
        if raw is None:
            continue
        try:
            config = json.loads(_strip_jsonc(raw))
        except (json.JSONDecodeError, ValueError):
            continue
        options = config.get("compilerOptions", {}) if isinstance(config, dict) else {}
        base_url = str(options.get("baseUrl", ".")).strip("./") if isinstance(options, dict) else ""
        paths = options.get("paths", {}) if isinstance(options, dict) else {}
        if not isinstance(paths, dict):
            continue
        for alias, targets in paths.items():
            if isinstance(targets, list):
                resolved = [
                    posixpath.normpath(posixpath.join(base_url, str(t))).lstrip("./")
                    for t in targets
                ]
                aliases.append(
                    (str(alias), [t if not t.startswith("/") else t[1:] for t in resolved])
                )
    return aliases


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments and trailing commas outside of strings."""
    out: list[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(ch)
            i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


# -- signature compatibility ------------------------------------------------------


def check_call(
    signature: Signature, call: CallSite, *, language: LanguageId, drop_first: bool
) -> list[str]:
    """Problems a call would hit against ``signature`` (empty list = compatible or unknowable)."""
    params = list(signature.params)
    if drop_first and params:
        params = params[1:]
    if language is LanguageId.PYTHON:
        return _check_python(params, call)
    return _check_js(params, call, typescript=language is LanguageId.TYPESCRIPT)


def _check_python(params: list[Param], call: CallSite) -> list[str]:
    if call.star_args or call.star_kwargs:
        return []  # arity cannot be determined statically
    problems: list[str] = []
    positional_params = [
        p for p in params if p.kind in ("positional_only", "positional_or_keyword")
    ]
    has_var_pos = any(p.kind == "var_positional" for p in params)
    has_var_kw = any(p.kind == "var_keyword" for p in params)
    if not has_var_pos and call.positional > len(positional_params):
        problems.append(
            f"passes {call.positional} positional argument(s) but at most {len(positional_params)} are accepted"
        )
    bound = {p.name for p in positional_params[: call.positional]}
    by_name = {p.name: p for p in params}
    for kw in call.keywords:
        p = by_name.get(kw)
        if p is None or p.kind in ("positional_only", "var_positional", "var_keyword"):
            if not has_var_kw:
                problems.append(f"passes unexpected keyword argument `{kw}`")
        elif kw in bound:
            problems.append(f"passes multiple values for argument `{kw}`")
        else:
            bound.add(kw)
    for p in params:
        if p.kind in ("var_positional", "var_keyword") or p.has_default:
            continue
        if p.name not in bound:
            problems.append(f"does not pass required argument `{p.name}`")
    return problems


def _check_js(params: list[Param], call: CallSite, *, typescript: bool) -> list[str]:
    if call.star_args:
        return []
    required = 0
    for p in params:
        if p.kind == "var_positional":
            break
        if not p.has_default:
            required += 1
    unbounded = any(p.kind == "var_positional" for p in params)
    maximum = len([p for p in params if p.kind != "var_positional"])
    problems: list[str] = []
    if call.positional < required:
        problems.append(f"passes {call.positional} argument(s) but {required} are required")
    if typescript and not unbounded and call.positional > maximum:
        problems.append(f"passes {call.positional} argument(s) but at most {maximum} are accepted")
    return problems
