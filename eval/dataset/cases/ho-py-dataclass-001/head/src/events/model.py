from dataclasses import dataclass


@dataclass
class Event:
    name: str
    payload: dict
    occurred_at: float
