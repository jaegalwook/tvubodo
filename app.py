import os, re, requests
from flask import Flask, request, Response, abort
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # 모든 오리진 허용 (필요시 도메인 제한)

# (선택) 보안상 허용 도메인 화이트리스트
ALLOW_RE = re.compile(
    r"^(https:\/\/)"
    r"("
    r"(www\.)?korea\.kr"
    r"|www\.mois\.go\.kr"
    r"|www\.mohw\.go\.kr"
    r"|gnews\.gg\.go\.kr"
    r"|.*\.go\.kr"
    r")\/", re.IGNORECASE
)

@app.get("/proxy")
def proxy():
    url = request.args.get("url", "")
    if not url:
        abort(400, "missing url")

    # (선택) 허용 도메인만 통과
    if not ALLOW_RE.match(url):
        abort(403, "blocked by whitelist")

    try:
        # 서버에서 직접 받아오기 (리다이렉트 허용)
        r = requests.get(url, timeout=10, allow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (RSS Proxy)"
        })
    except requests.RequestException as e:
        abort(502, f"upstream error: {e}")

    # 원본의 content-type을 최대한 전달
    ctype = r.headers.get("Content-Type", "application/xml; charset=utf-8")
    # 텍스트 류만 통과 (보안)
    if not any(s in ctype for s in ["xml", "html", "text", "application/rss+xml", "application/atom+xml"]):
        ctype = "application/xml; charset=utf-8"

    return Response(r.content, status=r.status_code, content_type=ctype)

@app.get("/")
def health():
    return "ok"
