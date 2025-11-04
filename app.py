import json, re
from urllib.parse import urlparse, unquote
import requests, feedparser
from flask import Flask, request, jsonify, make_response, abort
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/**": {"origins": "*"}})

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

def _http_get(u):
    return requests.get(u, headers=COMMON_HEADERS, timeout=15, allow_redirects=True)

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
    # 진단용: 원본 그대로 프록시
    url = request.args.get("url", "")
    if not url:
        abort(400, "missing url")
    try:
        r = _http_get(url)
    except requests.RequestException as e:
        abort(502, f"upstream error: {e}")
    ctype = (r.headers.get("Content-Type") or "application/xml; charset=utf-8")
    resp = make_response(r.content, r.status_code)
    resp.headers["Content-Type"] = ctype
    return resp

def is_xml_like(text: str, ctype: str) -> bool:
    if ctype and re.search(r"(xml|rss|atom)", ctype, re.I):
        return True
    return bool(re.search(r"<(rss|feed|channel)\b", text or "", re.I))

def force_mobile_korea(url: str) -> str:
    try:
        u = urlparse(url)
        if u.hostname == "www.korea.kr":
            return url.replace("://www.", "://m.")
        return url
    except Exception:
        return url

def fetch_xml_with_fallbacks(url: str):
    """
    1) 원본 시도
    2) korea.kr이면 m.korea.kr 강제
    3) 여전히 비-XML이면 Jina 프록시 (https://r.jina.ai/http://...)
    반환: (xml_text, diag_dict)
    """
    diag = {"tried": []}

    # 1) 원본
    try:
        r1 = _http_get(url)
        text1 = r1.text
        ctype1 = r1.headers.get("Content-Type", "")
        diag["tried"].append({"step": "origin", "url": url, "status": r1.status_code,
                              "ctype": ctype1, "head": (text1 or "")[:400]})
        if is_xml_like(text1, ctype1):
            return text1, diag
    except Exception as e:
        diag["tried"].append({"step": "origin-ex", "url": url, "error": str(e)})

    # 2) m.korea.kr 강제
    url2 = force_mobile_korea(url)
    if url2 != url:
        try:
            r2 = _http_get(url2)
            text2 = r2.text
            ctype2 = r2.headers.get("Content-Type", "")
            diag["tried"].append({"step": "mobile", "url": url2, "status": r2.status_code,
                                  "ctype": ctype2, "head": (text2 or "")[:400]})
            if is_xml_like(text2, ctype2):
                return text2, diag
        except Exception as e:
            diag["tried"].append({"step": "mobile-ex", "url": url2, "error": str(e)})

    # 3) Jina 프록시 (https URL을 http로 바꿔 붙임)
    try:
        # Jina는 https도 http로 붙여야 동작: r.jina.ai/http://{host/path}
        raw = url2 if url2 != url else url
        jina_target = "https://r.jina.ai/http://" + re.sub(r"^https?://", "", raw)
        r3 = _http_get(jina_target)
        text3 = r3.text
        ctype3 = r3.headers.get("Content-Type", "")
        diag["tried"].append({"step": "jina", "url": jina_target, "status": r3.status_code,
                              "ctype": ctype3, "head": (text3 or "")[:400]})
        if is_xml_like(text3, ctype3) or text3.strip().startswith("<?xml"):
            return text3, diag
    except Exception as e:
        diag["tried"].append({"step": "jina-ex", "url": jina_target, "error": str(e)})

    # 실패
    return "", diag

def parse_items(xml_text: str, source: str):
    if not xml_text:
        return []
    feed = feedparser.parse(xml_text)
    out = []
    for e in feed.entries[:120]:
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        date = (e.get("published") or e.get("updated") or e.get("issued") or "").strip()
        if not link and "links" in e and e.links:
            link = e.links[0].get("href", "")
        if title or link:
            out.append({"source": source, "title": title, "link": link, "date": date})
    return out

@app.get("/rss")
def rss():
    """
    GET /rss?feeds=[{"name":"정책브리핑","url":"https://m.korea.kr/rss/pressRelease.do"}]&debug=1
    - feeds: URL-encoded JSON 배열 (없으면 기본 세트)
    - debug=1: 각 피드별 진단(tried 리스트) 포함
    """
    feeds_param = request.args.get("feeds", "")
    debug = request.args.get("debug", "0") == "1"

    if not feeds_param:
        feeds = [
            {"name":"정책브리핑(모바일)","url":"https://m.korea.kr/rss/pressRelease.do"},
            {"name":"행정안전부(보도자료)","url":"https://www.mois.go.kr/rss/board.do?boardId=news&menuNo=200010"},
            {"name":"보건복지부(보도자료)","url":"https://www.mohw.go.kr/iframe/board/rss.do?bid=0032"},
        ]
    else:
        try:
            feeds = json.loads(feeds_param)
        except Exception:
            try:
                feeds = json.loads(unquote(feeds_param))
            except Exception:
                abort(400, "feeds query must be JSON array")

    all_items = []
    diagnostics = [] if debug else None

    for f in feeds:
        url = f.get("url", "")
        name = f.get("name", "기관")
        if not url.startswith("http"):
            if debug: diagnostics.append({"name": name, "error": "invalid url", "url": url})
            continue

        xml_text, diag = fetch_xml_with_fallbacks(url)
        items = parse_items(xml_text, name)
        all_items.extend(items)
        if debug:
            diagnostics.append({
                "name": name, "url": url,
                "parsed_count": len(items),
                "diagnostic": diag
            })

    # 문자열 날짜 기준 정렬
    all_items.sort(key=lambda x: x.get("date",""), reverse=True)

    resp = {"items": all_items, "count": len(all_items)}
    if debug:
        resp["debug"] = diagnostics
    return jsonify(resp)
