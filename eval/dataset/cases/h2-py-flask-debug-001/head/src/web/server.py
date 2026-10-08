from flask import Flask

app = Flask(__name__)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def main() -> None:
    app.run(host="0.0.0.0", port=8080, debug=True)
