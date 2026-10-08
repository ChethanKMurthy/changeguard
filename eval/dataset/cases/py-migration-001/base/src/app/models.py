from dataclasses import dataclass


@dataclass
class User:
    id: int
    email: str
    legacy_email: str | None = None
