import re, requests
from flask import Flask, request, Response, abort, make_response
from flask_cors import CORS
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app, resources={r"/proxy": {"origins": "*"}})

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/127.0.0.0 Safari/537.36")

COMMON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.korea.kr/",
}

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
    resp.headers["Access-Control-Expose-Headers"] = "Content-Type"
    return resp

@app.route("/proxy", methods=["GET", "OPTIONS"])
def proxy():
    if request.method == "OPTIONS":
        return ("", 204)

    url = request.args.get("url", "")
    if not url:
        abort(400, "missing url")

    def fetch_once(u):
        return requests.get(
            u, timeout=12, allow_redirects=True, headers=COMMON_HEADERS
        )

    r = fetch_once(url)

    ctype = (r.headers.get("Content-Type") or "").lower()
    text_head = r.text[:500] if "xml" not in ctype else ""

    # ⚠️ korea.kr이 에러 HTML을 준 경우 → m.korea.kr RSS로 폴백
    host = urlparse(url).hostname or ""
    if ("korea.kr" in host) and ("xml" not in ctype):
        # 에러 HTML 내 alternate 링크 탐색
        m = re.search(r'href="(https://m\.korea\.kr/[^"]+pressRelease\.do[^"]*)"', r.text, re.I)
        alt = m.group(1) if m else "https://m.korea.kr/rss/pressRelease.do"
        r2 = fetch_once(alt)
        # r2로 덮어쓰기
        r = r2
        ctype = (r.headers.get("Content-Type") or "").lower()

    # Content-Type 정리
    if not re.search(r"(xml|rss|atom|text|html)", ctype):
        ctype = "application/xml; charset=utf-8"

    resp = make_response(r.content, r.status_code)
    resp.headers["Content-Type"] = ctype
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/")
def health():
    return "ok"
