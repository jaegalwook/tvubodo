import os, textwrap
from flask import Flask, request, jsonify
from flask_cors import CORS

# ---- OpenAI SDK (v1.x) ----
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.get("/")
def health():
    return "ok"

SYSTEM_PROMPT = """\
당신은 한국어 기사 작성 어시스턴트입니다.
입력으로 보도자료 원문과 메타(기관/제목/날짜/링크), 톤/길이/템플릿 설정이 주어집니다.
규칙:
- 사실 중심, 과장/허위 금지. 알 수 없는 사실은 추정하지 말고 '원문 참고'로 남겨라.
- 마크다운으로만 출력. 불필요한 접두어/설명 금지.
- 섹션 제목은 간결하게.
- 표시는 '—'가 아닌 구체 문장 위주.
템플릿:
- std: 요약→정책 포인트→효과/과제→출처
- faq: 무엇/왜/어떻게/언제/누가 → 출처
- bullet: 핵심 요약/포인트/기대효과/남은 과제 → 출처
톤:
- neutral(중립), policy(정책 해설), promo(대민 안내), editorial(해설/오피니언)
길이:
- short(600~800자), medium(900~1200자), long(1400~1800자)
"""

def build_user_prompt(payload: dict) -> str:
    source = payload.get("source") or "출처 미기재"
    title  = payload.get("title")  or "(제목 없음)"
    date   = payload.get("date")   or ""
    link   = payload.get("link")   or ""
    body   = (payload.get("body") or "").strip()
    tone   = payload.get("tone")   or "neutral"
    length = payload.get("length") or "medium"
    tmpl   = payload.get("template") or "std"

    guide = f"""\
[메타]
- 기관/출처: {source}
- 제목: {title}
- 게재일: {date or "—"}
- 원문 링크: {link or "—"}

[요청설정]
- 톤: {tone}
- 길이: {length}
- 템플릿: {tmpl}

[원문]
{body[:20000]}
"""
    return textwrap.dedent(guide)

@app.post("/generate")
def generate():
    if not OPENAI_API_KEY:
        return jsonify({"error":"OPENAI_API_KEY 미설정"}), 500

    data = request.get_json(force=True, silent=True) or {}
    try:
        user_prompt = build_user_prompt(data)
        # 모델은 취향껏 교체 가능(gpt-4o-mini 등)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            messages=[
                {"role":"system","content":SYSTEM_PROMPT},
                {"role":"user","content":user_prompt}
            ]
        )
        md = resp.choices[0].message.content.strip()
        return jsonify({"markdown": md})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
