"""Python indexer: symbols, signatures, imports, call sites, and metrics."""

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
    ParamKind,
    Signature,
    Symbol,
    SymbolKind,
)
from changeguard.languages.registry import is_test_path, parse
from changeguard.languages.treeutil import end_line, error_lines, line, normalized, text, walk

DECISION_NODES = frozenset(
    {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "conditional_expression",
        "boolean_operator",
        "for_in_clause",
        "if_clause",
        "case_clause",
    }
)
_DEFINITIONS = frozenset({"function_definition", "class_definition"})
_MAX_CALL_TEXT = 160


def index_python(path: str, source: str) -> FileIndex:
    tree = parse(source, "python")
    root = tree.root_node
    index = FileIndex(path=path, language=LanguageId.PYTHON, is_test=is_test_path(path))
    index.parse_error_lines = error_lines(root)
    identifiers: dict[str, set[int]] = defaultdict(set)

    # Iterative traversal carrying the lexical scope: a tuple of (name, kind).
    stack: list[tuple[Node, tuple[tuple[str, str], ...]]] = [(root, ())]
    while stack:
        node, scope = stack.pop()
        kind = node.type
        if kind == "decorated_definition":
            definition = node.child_by_field_name("definition")
            decorators = tuple(
                text(d)[1:].strip() for d in node.named_children if d.type == "decorator"
            )
            for d in node.named_children:
                if d.type == "decorator":
                    stack.append((d, scope))
            if definition is not None:
                _enter_definition(definition, node, decorators, scope, index, stack)
            continue
        if kind in _DEFINITIONS:
            _enter_definition(node, node, (), scope, index, stack)
            continue
        if kind == "call":
            _record_call(node, path, index)
        elif kind == "import_statement" or kind == "import_from_statement":
            index.imports.extend(_imports(node, path))
        elif kind == "identifier":
            identifiers[text(node)].add(line(node))
        elif kind == "expression_statement" and not scope:
            _module_variable(node, path, index)
        children = node.children
        for i in range(len(children) - 1, -1, -1):
            stack.append((children[i], scope))

    index.identifiers = {name: sorted(lines) for name, lines in identifiers.items()}
    _attach_enclosing(index)
    return index


# -- definitions ------------------------------------------------------------------


def _enter_definition(
    node: Node,
    outer: Node,
    decorators: tuple[str, ...],
    scope: tuple[tuple[str, str], ...],
    index: FileIndex,
    stack: list[tuple[Node, tuple[tuple[str, str], ...]]],
) -> None:
    name_node = node.child_by_field_name("name")
    name = text(name_node)
    body = node.child_by_field_name("body")
    parent_qual = ".".join(n for n, _ in scope) or None
    qualname = f"{parent_qual}.{name}" if parent_qual else name
    in_class = bool(scope) and scope[-1][1] == "class"

    if node.type == "function_definition":
        is_async = any(c.type == "async" for c in node.children)
        params_node = node.child_by_field_name("parameters")
        returns = node.child_by_field_name("return_type")
        signature = Signature(
            params=_params(params_node) if params_node is not None else (),
            returns=text(returns) or None,
            is_async=is_async,
        )
        sym_kind: SymbolKind = "method" if in_class else "function"
        if index.is_test and name.startswith("test"):
            sym_kind = "test"
        complexity, try_blocks, assertions = _body_metrics(body)
        index.symbols.append(
            Symbol(
                name=name,
                qualname=qualname,
                kind=sym_kind,
                file=index.path,
                start_line=line(outer),
                end_line=end_line(node),
                signature_line=line(node),
                signature=signature,
                parent=parent_qual if in_class else None,
                decorators=decorators,
                complexity=complexity,
                normalized_body=normalized(body) if body is not None else "",
                try_blocks=try_blocks,
                assertions=assertions,
            )
        )
        scope_kind = "function"
    else:
        cls = Symbol(
            name=name,
            qualname=qualname,
            kind="class",
            file=index.path,
            start_line=line(outer),
            end_line=end_line(node),
            signature_line=line(node),
            parent=parent_qual if in_class else None,
            decorators=decorators,
            normalized_body="",
        )
        index.symbols.append(cls)
        synthetic = _synthesized_init(node, cls, decorators)
        if synthetic is not None:
            index.symbols.append(synthetic)
        scope_kind = "class"

    inner_scope = (*scope, (name, scope_kind))
    for child in reversed(node.children):
        if child is body or (body is not None and child.id == body.id):
            stack.append((child, inner_scope))
        elif child.type != "identifier" or child.id != (name_node.id if name_node else -1):
            stack.append((child, scope))


def _params(params_node: Node) -> tuple[Param, ...]:
    params: list[Param] = []
    after_star = False
    for child in params_node.named_children:
        t = child.type
        if t == "comment":
            continue
        if t == "positional_separator":
            params = [
                replace(p, kind="positional_only") if p.kind == "positional_or_keyword" else p
                for p in params
            ]
            continue
        if t == "keyword_separator":
            after_star = True
            continue
        if t == "list_splat_pattern":
            params.append(Param(_first_identifier(child), "var_positional"))
            after_star = True
            continue
        if t == "dictionary_splat_pattern":
            params.append(Param(_first_identifier(child), "var_keyword"))
            continue
        kind: ParamKind = "keyword_only" if after_star else "positional_or_keyword"
        if t == "identifier":
            params.append(Param(text(child), kind))
        elif t == "typed_parameter":
            inner = child.named_children[0] if child.named_children else None
            annotation = text(child.child_by_field_name("type")) or None
            if inner is not None and inner.type == "list_splat_pattern":
                params.append(
                    Param(_first_identifier(inner), "var_positional", annotation=annotation)
                )
                after_star = True
            elif inner is not None and inner.type == "dictionary_splat_pattern":
                params.append(Param(_first_identifier(inner), "var_keyword", annotation=annotation))
            else:
                params.append(Param(text(inner), kind, annotation=annotation))
        elif t in ("default_parameter", "typed_default_parameter"):
            params.append(
                Param(
                    text(child.child_by_field_name("name")),
                    kind,
                    has_default=True,
                    default=text(child.child_by_field_name("value")),
                    annotation=text(child.child_by_field_name("type")) or None,
                )
            )
    return tuple(params)


def _first_identifier(node: Node) -> str:
    for n in walk(node):
        if n.type == "identifier":
            return text(n)
    return text(node).lstrip("*")


def _body_metrics(body: Node | None) -> tuple[int, int, int]:
    """Cyclomatic complexity, try-statement count, assertion count (nested defs excluded)."""
    if body is None:
        return 1, 0, 0
    complexity, tries, assertions = 1, 0, 0
    for n in walk(body, skip=lambda x: x.type in _DEFINITIONS or x.type == "decorated_definition"):
        t = n.type
        if t in DECISION_NODES:
            complexity += 1
        elif t == "try_statement":
            tries += 1
        elif t == "assert_statement":
            assertions += 1
        elif t == "call":
            fn = n.child_by_field_name("function")
            callee = text(fn)
            last = callee.rsplit(".", 1)[-1]
            if last.startswith("assert") or callee in {"pytest.raises", "pytest.fail"}:
                assertions += 1
    return complexity, tries, assertions


def _synthesized_init(cls_node: Node, cls: Symbol, decorators: tuple[str, ...]) -> Symbol | None:
    """Constructor signature for dataclasses and pydantic models without an explicit ``__init__``."""
    body = cls_node.child_by_field_name("body")
    if body is None:
        return None
    is_dataclass = any(
        d.split("(")[0].rsplit(".", 1)[-1] in {"dataclass", "define", "frozen"} for d in decorators
    )
    supers = text(cls_node.child_by_field_name("superclasses"))
    is_pydantic = "BaseModel" in supers
    if not (is_dataclass or is_pydantic):
        return None
    if any(
        c.type == "function_definition" and text(c.child_by_field_name("name")) == "__init__"
        for c in body.named_children
    ):
        return None
    kw_only = is_pydantic or any("kw_only=True" in d.replace(" ", "") for d in decorators)
    params: list[Param] = [Param("self", "positional_or_keyword")]
    for stmt in body.named_children:
        if stmt.type != "expression_statement" or not stmt.named_children:
            continue
        assign = stmt.named_children[0]
        if assign.type != "assignment":
            continue
        left = assign.child_by_field_name("left")
        annotation = assign.child_by_field_name("type")
        if left is None or left.type != "identifier" or annotation is None:
            continue
        ann_text = text(annotation)
        if "ClassVar" in ann_text:
            continue
        right = assign.child_by_field_name("right")
        params.append(
            Param(
                text(left),
                "keyword_only" if kw_only else "positional_or_keyword",
                has_default=right is not None,
                default=text(right) if right is not None else None,
                annotation=ann_text,
            )
        )
    return Symbol(
        name="__init__",
        qualname=f"{cls.qualname}.__init__",
        kind="method",
        file=cls.file,
        start_line=cls.start_line,
        end_line=cls.end_line,
        signature_line=cls.signature_line,
        signature=Signature(tuple(params)),
        parent=cls.qualname,
        synthetic=True,
        normalized_body=normalized(body),
    )


def _module_variable(node: Node, path: str, index: FileIndex) -> None:
    if not node.named_children:
        return
    assign = node.named_children[0]
    if assign.type != "assignment":
        return
    left = assign.child_by_field_name("left")
    if left is None or left.type != "identifier":
        return
    name = text(left)
    index.symbols.append(
        Symbol(
            name=name,
            qualname=name,
            kind="variable",
            file=path,
            start_line=line(node),
            end_line=end_line(node),
            signature_line=line(node),
            normalized_body=normalized(assign),
        )
    )


# -- imports and calls ----------------------------------------------------------


def _imports(node: Node, path: str) -> list[ImportBinding]:
    bindings: list[ImportBinding] = []
    ln = line(node)
    if node.type == "import_statement":
        for child in node.named_children:
            if child.type == "dotted_name":
                module = text(child)
                bindings.append(
                    ImportBinding(path, ln, module, None, module.split(".")[0], "module")
                )
            elif child.type == "aliased_import":
                module = text(child.child_by_field_name("name"))
                alias = text(child.child_by_field_name("alias"))
                bindings.append(ImportBinding(path, ln, module, None, alias, "module"))
        return bindings

    module_node = node.child_by_field_name("module_name")
    level = 0
    module = ""
    if module_node is not None and module_node.type == "relative_import":
        for c in module_node.children:
            if c.type == "import_prefix":
                level = text(c).count(".")
            elif c.type == "dotted_name":
                module = text(c)
    else:
        module = text(module_node)
    if any(c.type == "wildcard_import" for c in node.children):
        bindings.append(ImportBinding(path, ln, module, "*", "*", "wildcard", level))
        return bindings
    for name_node in node.children_by_field_name("name"):
        if name_node.type == "aliased_import":
            imported = text(name_node.child_by_field_name("name"))
            local = text(name_node.child_by_field_name("alias"))
        else:
            imported = text(name_node)
            local = imported
        bindings.append(ImportBinding(path, ln, module, imported, local, "name", level))
    return bindings


def _dotted(node: Node | None) -> str | None:
    """Render identifier/attribute chains like ``a.b.c``; ``None`` for other expressions."""
    if node is None:
        return None
    if node.type == "identifier":
        return text(node)
    if node.type == "attribute":
        obj = _dotted(node.child_by_field_name("object"))
        attr = node.child_by_field_name("attribute")
        if obj is None or attr is None:
            return None
        return f"{obj}.{text(attr)}"
    return None


def _record_call(node: Node, path: str, index: FileIndex) -> None:
    fn = node.child_by_field_name("function")
    args = node.child_by_field_name("arguments")
    if fn is None:
        return
    callee = _dotted(fn)
    if callee is None:
        attr = fn.child_by_field_name("attribute") if fn.type == "attribute" else None
        name = text(attr) if attr is not None else ""
        receiver_node = fn.child_by_field_name("object") if fn.type == "attribute" else None
        callee_text = text(fn)[:80]
        receiver = text(receiver_node)[:80] if receiver_node is not None else None
    else:
        name = callee.rsplit(".", 1)[-1]
        receiver = callee.rsplit(".", 1)[0] if "." in callee else None
        callee_text = callee
    positional = 0
    keywords: list[str] = []
    star_args = star_kwargs = False
    if args is not None:
        if args.type == "generator_expression":
            positional = 1
        else:
            for a in args.named_children:
                if a.type == "keyword_argument":
                    keywords.append(text(a.child_by_field_name("name")))
                elif a.type == "list_splat":
                    star_args = True
                elif a.type == "dictionary_splat":
                    star_kwargs = True
                elif a.type != "comment":
                    positional += 1
    parent = node.parent
    awaited = parent is not None and parent.type == "await"
    snippet = text(node)
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
            keywords=tuple(keywords),
            star_args=star_args,
            star_kwargs=star_kwargs,
            awaited=awaited,
            enclosing=None,
            text=" ".join(snippet.split()),
        )
    )


def _attach_enclosing(index: FileIndex) -> None:
    funcs = sorted(
        (s for s in index.symbols if s.kind in ("function", "method", "test") and not s.synthetic),
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
