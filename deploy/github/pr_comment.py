"""Post a ChangeGuard report as a pull request comment, or update the earlier one.

Used by the GitHub Action (action.yml). Standard library only, so it runs on
any runner without installing anything. One comment per pull request: the
comment carries a hidden marker and is edited in place on every push.

Environment: GH_TOKEN, GITHUB_REPOSITORY, PR, and optionally GITHUB_API_URL.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

MARKER = "<!-- changeguard-report -->"
LIMIT = 60_000  # GitHub rejects comment bodies over 65,536 characters


def body(markdown: str) -> str:
    if len(markdown) > LIMIT:
        cut = markdown.rfind("\n", 0, LIMIT)
        markdown = markdown[: cut if cut > 0 else LIMIT]
        markdown += "\n\n_Report truncated. The full report is in the job summary._\n"
    return f"{MARKER}\n{markdown}"


def _call(method: str, url: str, token: str, payload: dict[str, str] | None = None) -> object:
    if not url.startswith("https://"):
        raise ValueError(f"refusing a non-HTTPS API URL: {url}")
    request = urllib.request.Request(  # noqa: S310 - scheme checked above
        url,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - scheme checked above
        return json.loads(response.read() or b"null")


def existing_comment(api: str, repo: str, pr: str, token: str) -> int | None:
    page = 1
    while True:
        url = f"{api}/repos/{repo}/issues/{pr}/comments?per_page=100&page={page}"
        comments = _call("GET", url, token)
        if not isinstance(comments, list) or not comments:
            return None
        for comment in comments:
            if str(comment.get("body", "")).startswith(MARKER):
                return int(comment["id"])
        page += 1


def main() -> int:
    token, repo, pr = os.environ["GH_TOKEN"], os.environ["GITHUB_REPOSITORY"], os.environ["PR"]
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    text = body(Path(sys.argv[1]).read_text())
    try:
        comment_id = existing_comment(api, repo, pr, token)
        if comment_id is None:
            _call("POST", f"{api}/repos/{repo}/issues/{pr}/comments", token, {"body": text})
            print("posted the ChangeGuard comment")
        else:
            _call(
                "PATCH", f"{api}/repos/{repo}/issues/comments/{comment_id}", token, {"body": text}
            )
            print("updated the ChangeGuard comment")
    except urllib.error.HTTPError as exc:
        # Pull requests from forks get a read-only token; the report is still in the job summary.
        print(f"::warning::Could not comment on the pull request (HTTP {exc.code}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
