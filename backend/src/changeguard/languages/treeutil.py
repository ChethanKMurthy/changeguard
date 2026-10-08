"""Small helpers over tree-sitter nodes."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from tree_sitter import Node


def text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", errors="replace")


def line(node: Node) -> int:
    """1-based start line."""
    return node.start_point.row + 1


def end_line(node: Node) -> int:
    """1-based end line (inclusive)."""
    return node.end_point.row + 1


def walk(node: Node, *, skip: Callable[[Node], bool] | None = None) -> Iterator[Node]:
    """Pre-order traversal. ``skip(n)`` prunes the subtree below ``n`` (``n`` is still yielded)."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        if skip is not None and current is not node and skip(current):
            continue
        children = current.children
        for i in range(len(children) - 1, -1, -1):
            stack.append(children[i])


def error_lines(root: Node, limit: int = 25) -> list[int]:
    """Lines containing ERROR or MISSING nodes (syntax errors)."""
    if not root.has_error:
        return []
    found: list[int] = []
    for n in walk(root):
        if n.is_error or n.is_missing:
            ln = line(n)
            if ln not in found:
                found.append(ln)
                if len(found) >= limit:
                    break
    return found


def leaf_tokens(node: Node, *, exclude_types: frozenset[str] = frozenset({"comment"})) -> list[str]:
    tokens: list[str] = []
    for n in walk(node):
        if n.type in exclude_types:
            continue
        if n.child_count == 0:
            tokens.append(text(n))
    return tokens


def normalized(node: Node, limit: int = 20_000) -> str:
    """Whitespace- and comment-insensitive rendering used for similarity checks."""
    joined = " ".join(t for t in leaf_tokens(node) if t.strip())
    return joined[:limit]
