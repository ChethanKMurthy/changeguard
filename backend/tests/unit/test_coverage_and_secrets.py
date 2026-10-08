from __future__ import annotations

import json

import pytest

from changeguard.analysis.secrets import find_secrets, redact, shannon_entropy
from changeguard.errors import CoverageParseError
from changeguard.ingest.coverage import parse_coverage

COBERTURA = b"""<?xml version="1.0" ?>
<coverage version="7.6">
  <sources><source>/ci/project/src</source></sources>
  <packages><package name="shop"><classes>
    <class name="pricing.py" filename="shop/pricing.py">
      <lines><line number="1" hits="1"/><line number="4" hits="0"/><line number="4" hits="2"/></lines>
    </class>
  </classes></package></packages>
</coverage>
"""


def test_cobertura_parse_and_suffix_matching() -> None:
    report = parse_coverage(COBERTURA)
    assert report.format == "cobertura"
    assert report.files["shop/pricing.py"].lines == {
        1: 1,
        4: 2,
    }  # duplicate lines keep the max hits
    matches, unmatched = report.match(["src/shop/pricing.py", "src/shop/cart.py"])
    assert set(matches) == {"src/shop/pricing.py"} and unmatched == []


def test_cobertura_rejects_entity_expansion() -> None:
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;">]>
<coverage><packages/></coverage>"""
    with pytest.raises(CoverageParseError, match="forbidden"):
        parse_coverage(bomb)


def test_lcov_and_coverage_json() -> None:
    lcov = parse_coverage(b"TN:\nSF:/repo/src/a.js\nDA:1,3\nDA:2,0\nend_of_record\n")
    assert lcov.format == "lcov" and lcov.files["/repo/src/a.js"].lines == {1: 3, 2: 0}
    js = parse_coverage(
        json.dumps(
            {"files": {"src/b.py": {"executed_lines": [1, 2], "missing_lines": [5]}}}
        ).encode()
    )
    assert js.format == "coverage.py-json" and js.files["src/b.py"].lines == {1: 1, 2: 1, 5: 0}


def test_ambiguous_coverage_paths_are_not_guessed() -> None:
    report = parse_coverage(
        b"SF:a/util.py\nDA:1,1\nend_of_record\nSF:b/util.py\nDA:1,0\nend_of_record\n"
    )
    matches, _ = report.match(["src/util.py"])
    assert matches == {}


@pytest.mark.parametrize(
    "payload",
    [
        b"\xff\xfe\x00garbage",
        b"plain text",
        b'{"no_files": {}}',
        b"SF:a.py\nDA:x,1\nend_of_record\n",
        b"<root/>",
    ],
)
def test_invalid_coverage_rejected(payload: bytes) -> None:
    with pytest.raises(CoverageParseError):
        parse_coverage(payload)


# -- secrets ------------------------------------------------------------------------------
# Token-shaped strings are assembled at runtime so this file never contains a
# contiguous credential-looking literal.


def test_provider_tokens_detected_and_masked() -> None:
    github = "gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    aws = "AK" + "IA" + "QWERTYUIOPASDFGH"
    line = f'TOKEN = "{github}"  # and {aws}'
    found = find_secrets(line)
    assert {s.kind for s in found} == {"GitHub token", "AWS access key ID"}
    masked = redact(line)
    assert github not in masked and aws not in masked
    assert masked.startswith('TOKEN = "ghp_')


def test_generic_high_entropy_assignment() -> None:
    value = "pk9Qe7Lm2Zx4Rt8Vb1Nc6Yw3Hs5Jd0Fg"
    (match,) = find_secrets(f'PAYMENTS_API_KEY = "{value}"')
    assert not match.provider_specific
    assert shannon_entropy(value) > 4


@pytest.mark.parametrize(
    "line",
    [
        'password = "changeme123"',
        'api_key = "your_api_key_here"',
        'token = os.environ["TOKEN"]',
        'secret = "${SECRET_FROM_ENV}"',
        'password = "aaaaaaaaaaaa"',
    ],
)
def test_placeholders_are_not_secrets(line: str) -> None:
    assert find_secrets(line) == []
