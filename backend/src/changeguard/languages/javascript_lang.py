"""JavaScript / TypeScript indexer (JS, JSX, TS, TSX)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from tree_sitter import Node

from changeguard.languages.model import (
    CallSite,
    FileIndex,
    ImportBinding,
    LanguageId,
    Param,
    Signature,
    Symbol,
    SymbolKind,
)
from changeguard.languages.registry import Grammar, is_test_path, parse
from changeguard.languages.treeutil import end_line, error_lines, line, normalized, text, walk

FUNCTION_VALUE_TYPES = frozenset(
    {"arrow_function", "function_expression", "function", "generator_function"}
)
FUNCTION_NODES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "function",
        "generator_function",
        "arrow_function",
        "method_definition",
        "function_signature",
    }
)
DECISION_NODES = frozenset(
    {
        "if_statement",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "switch_case",
        "catch_clause",
        "ternary_expression",
    }
)
LOGICAL_OPERATORS = frozenset({"&&", "||", "??"})
TEST_FUNCTIONS = frozenset({"it", "test", "fit", "xit", "xtest"})
SUITE_FUNCTIONS = frozenset({"describe", "fdescribe", "xdescribe", "suite", "context"})
_MAX_CALL_TEXT = 160


def index_javascript(path: str, source: str, grammar: Grammar) -> FileIndex:
    language = LanguageId.TYPESCRIPT if grammar in ("typescript", "tsx") else LanguageId.JAVASCRIPT
    tree = parse(source, grammar)
    root = tree.root_node
    index = FileIndex(path=path, language=language, is_test=is_test_path(path))
    index.parse_error_lines = error_lines(root)
    identifiers: dict[str, set[int]] = defaultdict(set)
    exported_locals: set[str] = set()

    stack: list[tuple[Node, tuple[str, ...], bool]] = [(root, (), False)]
    while stack:
        node, scope, exported = stack.pop()
        t = node.type
        child_scope = scope
        if t == "export_statement":
            _record_export_clause(node, index, exported_locals)
            for child in reversed(node.children):
                stack.append((child, scope, True))
            continue
        if t in ("function_declaration", "generator_function_declaration", "function_signature"):
            name = text(node.child_by_field_name("name")) or "default"
            _add_function(index, node, node, name, scope, exported, kind="function")
            child_scope = (*scope, name)
        elif t in ("class_declaration", "abstract_class_declaration", "class"):
            name = text(node.child_by_field_name("name")) or ("default" if exported else "")
            if name:
                _add_class(index, node, name, scope, exported)
                child_scope = (*scope, name)
        elif t == "method_definition":
            parent = node.parent
            if parent is not None and parent.type == "class_body" and scope:
                name = text(node.child_by_field_name("name"))
                _add_function(index, node, node, name, scope, False, kind="method")
                child_scope = (*scope, name)
        elif t == "variable_declarator":
            value = node.child_by_field_name("value")
            name_node = node.child_by_field_name("name")
            if value is not None and name_node is not None:
                if value.type in FUNCTION_VALUE_TYPES and name_node.type == "identifier":
                    outer = node.parent if node.parent is not None else node
                    if outer.parent is not None and outer.parent.type == "export_statement":
                        outer = outer.parent
                    name = text(name_node)
                    _add_function(index, value, outer, name, scope, exported, kind="function")
                    child_scope = (*scope, name)
                elif _is_require(value):
                    index.imports.extend(_require_bindings(name_node, value, path))
                elif not scope and name_node.type == "identifier":
                    index.symbols.append(_variable(index.path, node, text(name_node), exported))
        elif t in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
            name = text(node.child_by_field_name("name"))
            index.symbols.append(
                Symbol(
                    name=name,
                    qualname=name,
                    kind="type",
                    file=path,
                    start_line=line(node),
                    end_line=end_line(node),
                    signature_line=line(node),
                    exported=exported,
                    normalized_body=normalized(node),
                )
            )
        elif t == "import_statement":
            index.imports.extend(_import_bindings(node, path))
        elif t in ("call_expression", "new_expression"):
            test_symbol = _test_case(node, index, scope)
            if test_symbol is not None:
                child_scope = (*scope, test_symbol)
            _record_call(node, path, index)
        elif t == "assignment_expression":
            _commonjs_export(node, index, scope)
        elif t in (
            "identifier",
            "property_identifier",
            "type_identifier",
            "shorthand_property_identifier",
        ):
            identifiers[text(node)].add(line(node))

        # `export const f = ...` wraps declarators in a declaration node.
        child_exported = exported and t in ("lexical_declaration", "variable_declaration")
        children = node.children
        for i in range(len(children) - 1, -1, -1):
            stack.append((children[i], child_scope, child_exported))

    for sym in index.symbols:
        if sym.parent is not None:
            continue
        if sym.name in exported_locals:
            sym.exported = True  # exported under an alias via `export { local as alias }`
        elif sym.exported:
            index.exports.setdefault(sym.name, sym.name)
    index.identifiers = {name: sorted(lines) for name, lines in identifiers.items()}
    _attach_enclosing(index)
    return index


# -- symbols ----------------------------------------------------------------------


def _add_function(
    index: FileIndex,
    fn: Node,
    outer: Node,
    name: str,
    scope: tuple[str, ...],
    exported: bool,
    *,
    kind: SymbolKind,
) -> None:
    params_node = fn.child_by_field_name("parameters")
    params: tuple[Param, ...]
    if params_node is None:
        # `x => x * 2` has a single bare identifier parameter.
        single = fn.child_by_field_name("parameter")
        params = (Param(text(single), "positional_or_keyword"),) if single is not None else ()
    else:
        params = _params(params_node)
    return_type = fn.child_by_field_name("return_type")
    returns = text(return_type).lstrip(":").strip() if return_type is not None else None
    is_async = any(c.type == "async" for c in fn.children)
    body = fn.child_by_field_name("body")
    complexity, tries, assertions = _body_metrics(body)
    qual_parent = ".".join(scope) or None
    index.symbols.append(
        Symbol(
            name=name,
            qualname=f"{qual_parent}.{name}" if qual_parent else name,
            kind=kind,
            file=index.path,
            start_line=line(outer),
            end_line=end_line(outer if outer.end_point.row >= fn.end_point.row else fn),
            signature_line=line(fn),
            signature=Signature(params, returns or None, is_async),
            parent=qual_parent if kind == "method" else None,
            exported=exported,
            complexity=complexity,
            normalized_body=normalized(body) if body is not None else "",
            try_blocks=tries,
            assertions=assertions,
        )
    )


def _add_class(
    index: FileIndex, node: Node, name: str, scope: tuple[str, ...], exported: bool
) -> None:
    qual_parent = ".".join(scope) or None
    outer = (
        node.parent if node.parent is not None and node.parent.type == "export_statement" else node
    )
    index.symbols.append(
        Symbol(
            name=name,
            qualname=f"{qual_parent}.{name}" if qual_parent else name,
            kind="class",
            file=index.path,
            start_line=line(outer),
            end_line=end_line(node),
            signature_line=line(node),
            exported=exported,
        )
    )


def _variable(path: str, declarator: Node, name: str, exported: bool) -> Symbol:
    decl = declarator.parent if declarator.parent is not None else declarator
    return Symbol(
        name=name,
        qualname=name,
        kind="variable",
        file=path,
        start_line=line(decl),
        end_line=end_line(decl),
        signature_line=line(decl),
        exported=exported,
        normalized_body=normalized(declarator),
    )


def _params(params_node: Node) -> tuple[Param, ...]:
    params: list[Param] = []
    for child in params_node.named_children:
        t = child.type
        if t == "comment":
            continue
        if t in ("required_parameter", "optional_parameter"):
            pattern = child.child_by_field_name("pattern")
            value = child.child_by_field_name("value")
            type_node = child.child_by_field_name("type")
            annotation = text(type_node).lstrip(":").strip() if type_node is not None else None
            if pattern is not None and pattern.type == "rest_pattern":
                params.append(
                    Param(_pattern_name(pattern), "var_positional", annotation=annotation)
                )
                continue
            params.append(
                Param(
                    _pattern_name(pattern),
                    "positional_or_keyword",
                    has_default=value is not None or t == "optional_parameter",
                    default=text(value) if value is not None else None,
                    annotation=annotation or None,
                )
            )
        elif t == "rest_pattern":
            params.append(Param(_pattern_name(child), "var_positional"))
        elif t == "assignment_pattern":
            left = child.child_by_field_name("left")
            right = child.child_by_field_name("right")
            params.append(Param(_pattern_name(left), "positional_or_keyword", True, text(right)))
        elif t in ("identifier", "object_pattern", "array_pattern"):
            params.append(Param(_pattern_name(child), "positional_or_keyword"))
    return tuple(params)


def _pattern_name(node: Node | None) -> str:
    if node is None:
        return "?"
    if node.type == "identifier":
        return text(node)
    if node.type == "rest_pattern":
        for c in node.named_children:
            return _pattern_name(c)
    if node.type == "object_pattern":
        return (
            "{" + ", ".join(text(c).split(":")[0].strip() for c in node.named_children)[:60] + "}"
        )
    if node.type == "array_pattern":
        return "[" + ", ".join(text(c) for c in node.named_children)[:60] + "]"
    return text(node)[:60]


def _body_metrics(body: Node | None) -> tuple[int, int, int]:
    if body is None:
        return 1, 0, 0
    complexity, tries, assertions = 1, 0, 0
    for n in walk(body, skip=lambda x: x.type in FUNCTION_NODES):
        t = n.type
        if t in DECISION_NODES:
            complexity += 1
        elif t == "binary_expression":
            op = n.child_by_field_name("operator")
            if op is not None and text(op) in LOGICAL_OPERATORS:
                complexity += 1
        elif t == "try_statement":
            tries += 1
        elif t == "call_expression":
            callee = text(n.child_by_field_name("function"))
            if callee in ("expect", "assert") or callee.startswith("assert."):
                assertions += 1
    return complexity, tries, assertions


def _test_case(node: Node, index: FileIndex, scope: tuple[str, ...]) -> str | None:
    """Register ``it("...")``/``test("...")`` calls as test symbols; returns a scope label."""
    if not index.is_test or node.type != "call_expression":
        return None
    fn = node.child_by_field_name("function")
    callee = text(fn)
    base = callee.split(".")[0]
    if base not in TEST_FUNCTIONS and base not in SUITE_FUNCTIONS:
        return None
    args = node.child_by_field_name("arguments")
    if args is None or not args.named_children:
        return None
    first = args.named_children[0]
    if first.type not in ("string", "template_string"):
        return None
    title = text(first).strip("'\"`")[:100]
    if base in SUITE_FUNCTIONS:
        return title
    qual_parent = " > ".join(scope) or None
    callback = args.named_children[1] if len(args.named_children) > 1 else None
    _, _, assertions = _body_metrics(
        callback.child_by_field_name("body") if callback is not None else None
    )
    index.symbols.append(
        Symbol(
            name=title,
            qualname=f"{qual_parent} > {title}" if qual_parent else title,
            kind="test",
            file=index.path,
            start_line=line(node),
            end_line=end_line(node),
            signature_line=line(node),
            normalized_body=normalized(callback) if callback is not None else "",
            assertions=assertions,
        )
    )
    return title


# -- imports / exports --------------------------------------------------------------


def _import_bindings(node: Node, path: str) -> list[ImportBinding]:
    source = node.child_by_field_name("source")
    module = text(source).strip("'\"`")
    ln = line(node)
    bindings: list[ImportBinding] = []
    clause = next((c for c in node.named_children if c.type == "import_clause"), None)
    if clause is None:
        return bindings  # side-effect import
    for c in clause.named_children:
        if c.type == "identifier":
            bindings.append(ImportBinding(path, ln, module, "default", text(c), "default"))
        elif c.type == "namespace_import":
            alias = next((x for x in c.named_children if x.type == "identifier"), None)
            bindings.append(ImportBinding(path, ln, module, None, text(alias), "namespace"))
        elif c.type == "named_imports":
            for spec in c.named_children:
                if spec.type != "import_specifier":
                    continue
                imported = text(spec.child_by_field_name("name"))
                alias = spec.child_by_field_name("alias")
                bindings.append(
                    ImportBinding(
                        path,
                        ln,
                        module,
                        imported,
                        text(alias) if alias is not None else imported,
                        "name",
                    )
                )
    return bindings


def _is_require(value: Node) -> bool:
    if value.type == "await_expression" and value.named_children:
        value = value.named_children[0]
    if value.type != "call_expression":
        return False
    fn = value.child_by_field_name("function")
    return fn is not None and text(fn) == "require"


def _require_bindings(name_node: Node, call: Node, path: str) -> list[ImportBinding]:
    args = call.child_by_field_name("arguments")
    if args is None or not args.named_children or args.named_children[0].type != "string":
        return []
    module = text(args.named_children[0]).strip("'\"`")
    ln = line(call)
    if name_node.type == "identifier":
        return [ImportBinding(path, ln, module, None, text(name_node), "namespace")]
    bindings: list[ImportBinding] = []
    if name_node.type == "object_pattern":
        for prop in name_node.named_children:
            if prop.type == "shorthand_property_identifier_pattern":
                bindings.append(ImportBinding(path, ln, module, text(prop), text(prop), "name"))
            elif prop.type == "pair_pattern":
                key = text(prop.child_by_field_name("key"))
                value = text(prop.child_by_field_name("value"))
                bindings.append(ImportBinding(path, ln, module, key, value, "name"))
    return bindings


def _record_export_clause(node: Node, index: FileIndex, exported_locals: set[str]) -> None:
    for c in node.named_children:
        if c.type == "export_clause":
            for spec in c.named_children:
                if spec.type != "export_specifier":
                    continue
                local = text(spec.child_by_field_name("name"))
                alias = spec.child_by_field_name("alias")
                index.exports[text(alias) if alias is not None else local] = local
                exported_locals.add(local)
    if any(c.type == "default" for c in node.children):
        value = node.child_by_field_name("value")
        if value is not None and value.type == "identifier":
            index.exports["default"] = text(value)
            exported_locals.add(text(value))


def _commonjs_export(node: Node, index: FileIndex, scope: tuple[str, ...]) -> None:
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    target = text(left)
    if left is None or right is None:
        return
    name: str | None = None
    if target.startswith(("module.exports.", "exports.")):
        name = target.rsplit(".", 1)[-1]
    elif target == "module.exports" and right.type == "object":
        for prop in right.named_children:
            if prop.type == "shorthand_property_identifier":
                index.exports[text(prop)] = text(prop)
            elif prop.type == "pair":
                index.exports[text(prop.child_by_field_name("key"))] = text(
                    prop.child_by_field_name("value")
                )
        return
    if name is None:
        return
    if right.type in FUNCTION_VALUE_TYPES:
        _add_function(index, right, node, name, scope, True, kind="function")
    index.exports[name] = name


# -- calls -------------------------------------------------------------------------


def _dotted(node: Node | None) -> str | None:
    if node is None:
        return None
    if node.type in ("identifier", "this", "super", "property_identifier"):
        return text(node)
    if node.type == "member_expression":
        obj = _dotted(node.child_by_field_name("object"))
        prop = node.child_by_field_name("property")
        if obj is None or prop is None:
            return None
        return f"{obj}.{text(prop)}"
    return None


def _record_call(node: Node, path: str, index: FileIndex) -> None:
    is_new = node.type == "new_expression"
    fn = node.child_by_field_name("constructor" if is_new else "function")
    if fn is None:
        return
    callee = _dotted(fn)
    if callee is None:
        prop = fn.child_by_field_name("property") if fn.type == "member_expression" else None
        name = text(prop) if prop is not None else ""
        obj = fn.child_by_field_name("object") if fn.type == "member_expression" else None
        receiver = text(obj)[:80] if obj is not None else None
        callee_text = text(fn)[:80]
    else:
        name = callee.rsplit(".", 1)[-1]
        receiver = callee.rsplit(".", 1)[0] if "." in callee else None
        callee_text = callee
    args = node.child_by_field_name("arguments")
    positional = 0
    star = False
    if args is not None:
        for a in args.named_children:
            if a.type == "spread_element":
                star = True
            elif a.type != "comment":
                positional += 1
    parent = node.parent
    awaited = False
    if parent is not None:
        if parent.type == "await_expression":
            awaited = True
        elif parent.type == "member_expression":
            prop = parent.child_by_field_name("property")
            awaited = text(prop) in {"then", "catch", "finally"}
    snippet = " ".join(text(node).split())
    if len(snippet) > _MAX_CALL_TEXT:
        snippet = snippet[: _MAX_CALL_TEXT - 1] + "…"
    index.calls.append(
        CallSite(
            file=path,
            line=line(node),
            end_line=end_line(node),
            callee=callee_text,
            name=name,
            receiver=receiver,
            positional=positional,
            keywords=(),
            star_args=star,
            star_kwargs=False,
            awaited=awaited,
            enclosing=None,
            text=snippet,
            is_new=is_new,
        )
    )


def _attach_enclosing(index: FileIndex) -> None:
    funcs = sorted(
        (s for s in index.symbols if s.kind in ("function", "method", "test")),
        key=lambda s: (s.start_line, -s.end_line),
    )
    if not funcs:
        return
    updated: list[CallSite] = []
    for call in index.calls:
        best: Symbol | None = None
        for s in funcs:
            if s.start_line > call.line:
                break
            if s.end_line >= call.line and (best is None or s.start_line >= best.start_line):
                best = s
        updated.append(replace(call, enclosing=best.qualname) if best else call)
    index.calls = updated
