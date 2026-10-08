"""Write the OpenAPI document (the contract the frontend's TypeScript types are generated from).

uv run python -m changeguard.api.openapi_export ../frontend/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from changeguard.api.app import create_app
from changeguard.config import Settings


def main() -> int:
    app = create_app(Settings(expose_docs=True))
    document = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(document)
    else:
        sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
