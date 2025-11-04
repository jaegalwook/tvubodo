import json, re, time
from urllib.parse import urlparse, unquote
import requests, feedparser
from flask import Flask, request, jsonify, make_response, abort
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/127.0 Safari/537.36")

COMMON_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.korea.kr/",
    "Connection": "close",
}

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept"
    resp.headers["Access-Control-Expose-Headers"] = "Content-Type"
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/")
def health():
    return "ok"

@app.get("/proxy")
def proxy():
    # (남겨둠: 테스트/진단용)
    url = request.args.get("url", "")
    if not url:
        abort(400, "missing url")
    try:
        r = requests.get(url, headers=COMMON_HEADERS, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        abort(502, f"upstream error: {e}")
    ctype = (r.headers.get("Content-Type") or "application/xml; charset=utf-8")
    resp = make_response(r.content, r.status_code)
    resp.headers["Content-Type"] = ctype
    return resp

def fetch_xml(url: str) -> str:
    """단일 RSS URL을 받아 XML 문자열 반환. www.korea.kr → m.korea.kr 강제 폴백 포함."""
    def _get(u):
        return requests.get(u, headers=COMMON_HEADERS, timeout=15, allow_redirects=True)

    r = _get(url)
    text = r.text
    ctype = (r.headers.get("Content-Type") or "")
    host = urlparse(url).hostname or ""
    looks_xml = ("xml" in ctype.lower()) or re.search(r"<(rss|feed|channel)\b", text, re.I)

    # korea.kr이 HTML 에러 줄 때 m.korea.kr로 한 번 더
    if (not looks_xml) and ("korea.kr" in host):
        alt = url.replace("://www.", "://m.")
        r2 = _get(alt)
        text = r2.text
        ctype = (r2.headers.get("Content-Type") or "")
        looks_xml = ("xml" in ctype.lower()) or re.search(r"<(rss|feed|channel)\b", text, re.I)
    return text

def parse_items(xml_text: str, source: str):
    """feedparser로 관대 파싱"""
    if not xml_text:
        return []
    # 일부 사이트가 잘못된 선언을 붙여도 feedparser가 상당부분 알아서 처리
    feed = feedparser.parse(xml_text)
    out = []
    for e in feed.entries[:100]:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        date = (e.get("published") or e.get("updated") or e.get("issued") or "").strip()
        if not link and "links" in e and e.links:
            link = e.links[0].get("href", "")
        out.append({
            "source": source,
            "title": title,
            "link": link,
            "date": date,
        })
    return out

@app.get("/rss")
def rss():
    """
    사용법:
    GET /rss?feeds=[{"name":"정책브리핑","url":"https://m.korea.kr/rss/pressRelease.do"}, ...]
    - feeds 파라미터는 URL-encoded JSON 배열
    - 응답은 {items:[...]} JSON
    """
    feeds_param = request.args.get("feeds", "")
    if not feeds_param:
        # 기본 피드 세트
        feeds = [
            {"name":"정책브리핑(모바일)","url":"https://m.korea.kr/rss/pressRelease.do"},
            {"name":"행정안전부(보도자료)","url":"https://www.mois.go.kr/rss/board.do?boardId=news&menuNo=200010"},
            {"name":"보건복지부(보도자료)","url":"https://www.mohw.go.kr/iframe/board/rss.do?bid=0032"},
        ]
    else:
        try:
            feeds = json.loads(feeds_param)
        except Exception:
            # 일부 클라이언트가 이미 인코딩된 문자열을 넣는 경우 대비
            try:
                feeds = json.loads(unquote(feeds_param))
            except Exception:
                abort(400, "feeds query must be JSON array")

    items = []
    for f in feeds:
        url = f.get("url", "")
        name = f.get("name", "기관")
        if not url.startswith("http"):
            continue
        try:
            xml = fetch_xml(url)
            one = parse_items(xml, name)
            items.extend(one)
        except Exception:
            # 개별 실패는 skip
            continue

    # 날짜 필드로 대략 정렬 (파서가 문자열을 주므로 naive 정렬)
    def keyfunc(x): return x.get("date","")
    items.sort(key=keyfunc, reverse=True)

    return jsonify({"items": items, "count": len(items)})
