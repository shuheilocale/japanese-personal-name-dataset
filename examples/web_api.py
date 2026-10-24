"""標準ライブラリだけで作る小さな JSON API。

    python examples/web_api.py            # http://127.0.0.1:8000/
    curl 'http://127.0.0.1:8000/random?gender=female&count=3'
    curl 'http://127.0.0.1:8000/search?reading=こう&partial=1'

エンドポイント:
    GET /random?gender=male|female&count=N   ランダムなフルネーム
    GET /search?reading=...&partial=0|1       読みで名を検索
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs, urlparse

from japanese_personal_name_dataset import generate_random_full_name, search_by_reading


def handle(path: str) -> Tuple[int, Any]:
    url = urlparse(path)
    q: Dict[str, List[str]] = parse_qs(url.query)
    if url.path == "/random":
        gender = q.get("gender", ["female"])[0]
        if gender not in ("male", "female"):
            return 400, {"error": "gender must be male or female"}
        count = max(1, min(int(q.get("count", ["1"])[0]), 100))
        names = []
        for _ in range(count):
            kanji, reading = generate_random_full_name(gender=gender, return_reading=True)  # type: ignore[arg-type]
            names.append({"name": kanji, "reading": reading})
        return 200, names
    if url.path == "/search":
        reading = q.get("reading", [""])[0]
        if not reading:
            return 400, {"error": "reading is required"}
        return 200, search_by_reading(reading, partial=q.get("partial", ["0"])[0] == "1")[:50]
    return 404, {"error": "not found", "endpoints": ["/random", "/search"]}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        status, body = handle(self.path)
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Japanese name JSON API (example)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("Serving on http://127.0.0.1:%d/ (Ctrl+C to stop)" % args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
