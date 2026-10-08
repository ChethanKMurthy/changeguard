def send(to: str, *, subject: str, html: bool = False) -> dict:
    return {"to": to, "subject": subject, "html": html}
