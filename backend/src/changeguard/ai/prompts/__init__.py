"""Versioned prompt registry.

Prompts are plain files under ``prompts/<id>/<version>/`` so they are reviewed
like code. Each loaded template carries a SHA-256 of its text; the hash is
recorded in every report and every recorded model response, so an output can
always be traced to the exact prompt that produced it.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from string import Template

_ROOT = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    id: str
    version: str
    description: str
    system: str
    user_template: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(f"{self.system}\n\x00\n{self.user_template}".encode()).hexdigest()

    def render_user(self, **values: str) -> str:
        # Template.substitute raises on missing keys; values are inserted verbatim
        # (no further interpolation), so untrusted text cannot inject placeholders.
        return Template(self.user_template).substitute(**values)


@functools.cache
def load_prompt(prompt_id: str = "review", version: str = "v1") -> PromptTemplate:
    directory = _ROOT / prompt_id / version
    meta = json.loads((directory / "meta.json").read_text())
    return PromptTemplate(
        id=meta["id"],
        version=meta["version"],
        description=meta["description"],
        system=(directory / "system.md").read_text().strip(),
        user_template=(directory / "user.md").read_text().strip(),
    )
