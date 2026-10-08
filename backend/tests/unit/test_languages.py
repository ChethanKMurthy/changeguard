from __future__ import annotations

from changeguard.analysis.references import check_call
from changeguard.analysis.structure import diff_signatures
from changeguard.languages import index_file
from changeguard.languages.model import CallSite, LanguageId
from tests.conftest import dedent

PY = dedent(
    """
    from .pricing import format_price as fp
    import shop.models as m

    @dataclass
    class Order:
        id: str
        total: float = 0.0

    class Cart:
        @staticmethod
        async def checkout(self, a, /, b: int = 2, *args, c, d=3, **kw) -> str:
            if a and b or c:
                return await fp(1, x=2)
            try:
                m.save(a)
            except Exception:
                pass

    def helper(x, *, y):
        return [i for i in x if i]
    """
)


def test_python_symbols_and_signatures() -> None:
    idx = index_file("src/shop/cart.py", PY)
    assert idx is not None
    by_name = {s.qualname: s for s in idx.symbols}
    checkout = by_name["Cart.checkout"]
    assert checkout.kind == "method" and checkout.signature is not None
    assert checkout.signature.is_async and checkout.signature.returns == "str"
    kinds = [(p.name, p.kind, p.has_default) for p in checkout.signature.params]
    assert kinds == [
        ("self", "positional_only", False),
        ("a", "positional_only", False),
        ("b", "positional_or_keyword", True),
        ("args", "var_positional", False),
        ("c", "keyword_only", False),
        ("d", "keyword_only", True),
        ("kw", "var_keyword", False),
    ]
    assert checkout.decorators == ("staticmethod",)
    # 1 + if + two boolean operators + except clause
    assert checkout.complexity == 5 and checkout.try_blocks == 1
    init = by_name["Order.__init__"]
    assert init.synthetic and [p.name for p in init.signature.params] == ["self", "id", "total"]  # type: ignore[union-attr]


def test_python_imports_and_calls() -> None:
    idx = index_file("src/shop/cart.py", PY)
    assert idx is not None
    imports = {(b.module, b.imported_name, b.local_name, b.kind, b.level) for b in idx.imports}
    assert ("pricing", "format_price", "fp", "name", 1) in imports
    assert ("shop.models", None, "m", "module", 0) in imports
    fp_call = next(c for c in idx.calls if c.callee == "fp")
    assert fp_call.awaited and fp_call.positional == 1 and fp_call.keywords == ("x",)
    assert fp_call.enclosing == "Cart.checkout"


def test_python_parse_errors_reported() -> None:
    idx = index_file("a.py", "def broken(:\n    pass\n")
    assert idx is not None and idx.parse_error_lines


TS = dedent(
    """
    import { a as b, c } from "./x";
    const { q } = require("./q");
    export async function f(p1: string, p2?: number, p3 = 4, ...rest: any[]): Promise<void> {
      await g(1, ...xs);
      new Foo(1, 2);
    }
    export const k = ({ a }: Props, cb) => a;
    const hidden = (x) => x;
    export { hidden as visible };
    export default class C { m(x) { return this.n(x); } n(y) { return y; } }
    """
)


def test_typescript_symbols_exports_and_calls() -> None:
    idx = index_file("src/app.ts", TS)
    assert idx is not None and idx.language is LanguageId.TYPESCRIPT
    f = idx.symbol("f")
    assert f is not None and f.exported and f.signature is not None and f.signature.is_async
    assert [(p.name, p.has_default, p.kind) for p in f.signature.params] == [
        ("p1", False, "positional_or_keyword"),
        ("p2", True, "positional_or_keyword"),
        ("p3", True, "positional_or_keyword"),
        ("rest", False, "var_positional"),
    ]
    assert idx.exports["visible"] == "hidden" and "hidden" not in idx.exports
    assert idx.symbol("C.m") is not None and idx.symbol("C.m").kind == "method"  # type: ignore[union-attr]
    new_call = next(c for c in idx.calls if c.is_new)
    assert new_call.callee == "Foo" and new_call.positional == 2
    assert {(b.module, b.imported_name, b.local_name) for b in idx.imports} >= {
        ("./x", "a", "b"),
        ("./q", "q", "q"),
    }


def test_js_test_cases_are_symbols() -> None:
    src = 'describe("math", () => { it("adds", () => { expect(add(1, 2)).toBe(3); }); });\n'
    idx = index_file("tests/math.test.js", src)
    assert idx is not None
    (test,) = [s for s in idx.symbols if s.kind == "test"]
    assert test.qualname == "math > adds" and test.assertions == 1


def _call(positional: int = 0, keywords: tuple[str, ...] = (), star: bool = False) -> CallSite:
    return CallSite(
        "f.py", 1, 1, "f", "f", None, positional, keywords, star, False, False, None, "f()"
    )


def _sig(src: str):  # type: ignore[no-untyped-def]
    idx = index_file("m.py", src)
    assert idx is not None
    return idx.symbols[0].signature


def test_python_call_binding_rules() -> None:
    sig = _sig("def f(a, b=1, *, c, d=2): pass\n")
    lang = LanguageId.PYTHON
    assert check_call(sig, _call(1, ("c",)), language=lang, drop_first=False) == []
    assert check_call(sig, _call(3, ("c",)), language=lang, drop_first=False) == [
        "passes 3 positional argument(s) but at most 2 are accepted"
    ]
    assert check_call(sig, _call(1, ("c", "zzz")), language=lang, drop_first=False) == [
        "passes unexpected keyword argument `zzz`"
    ]
    assert check_call(sig, _call(1, ("a", "c")), language=lang, drop_first=False) == [
        "passes multiple values for argument `a`"
    ]
    assert check_call(sig, _call(1), language=lang, drop_first=False) == [
        "does not pass required argument `c`"
    ]
    assert check_call(sig, _call(0, star=True), language=lang, drop_first=False) == []  # unknowable


def test_python_signature_diff_breaking_classification() -> None:
    before = _sig("def f(a, b=1, c=2): pass\n")
    compatible = diff_signatures(
        before, _sig("def f(a, b=1, c=2, d=None): pass\n"), LanguageId.PYTHON, False
    )
    assert not compatible.breaking and compatible.added_optional == ["d"]
    breaking = diff_signatures(
        before, _sig("def f(a, c=5, *, b=1): pass\n"), LanguageId.PYTHON, False
    )
    assert breaking.breaking
    assert ("b", "positional_or_keyword", "keyword_only") in breaking.kind_changes
    assert ("c", "2", "5") in breaking.default_changed
    annotated = diff_signatures(
        before, _sig("def f(a, b=1, c=2) -> int: pass\n"), LanguageId.PYTHON, False
    )
    assert annotated.returns_changed is None  # adding an annotation is not a change


def test_js_signature_diff_is_positional() -> None:
    def ts(src: str):  # type: ignore[no-untyped-def]
        idx = index_file("m.ts", src)
        assert idx is not None
        return idx.symbols[0].signature

    d = diff_signatures(
        ts("function f(a: number) {}"),
        ts("function f(renamed: number, b: string) {}"),
        LanguageId.TYPESCRIPT,
        False,
    )
    assert d.breaking and d.required_before == 1 and d.required_after == 2
    same = diff_signatures(
        ts("function f(a: number) {}"),
        ts("function f(renamed: number) {}"),
        LanguageId.TYPESCRIPT,
        False,
    )
    assert not same.any_change
