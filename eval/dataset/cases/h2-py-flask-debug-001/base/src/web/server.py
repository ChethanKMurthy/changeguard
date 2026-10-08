from flask import Flask

app = Flask(__name__)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def main() -> None:
    app.run(host="127.0.0.1", port=8080)
