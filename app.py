# --- 상단부 그대로 --- #
import os, textwrap
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

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

@app.get("/health")
def health_json():
    return jsonify({"ok": True})

# ---- OpenAI ----
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

SYSTEM_PROMPT = """(생략: 이전과 동일)"""

def build_user_prompt(payload: dict) -> str:
    # (생략: 이전과 동일)
    ...

def _generate_impl(data):
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        return None, ("OPENAI_API_KEY 미설정", 500)
    try:
        user_prompt = build_user_prompt(data)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            messages=[{"role":"system","content":SYSTEM_PROMPT},
                      {"role":"user","content":user_prompt}]
        )
        md = resp.choices[0].message.content.strip()
        return {"markdown": md}, None
    except Exception as e:
        return None, (str(e), 500)

# ✅ 일부 광고/보안 확장프로그램이 /generate 경로명을 막는 일이 있어 우회 경로 추가
@app.route("/generate", methods=["POST", "OPTIONS"])
@app.route("/api/g", methods=["POST", "OPTIONS"])
def generate():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True, silent=True) or {}
    ok, err = _generate_impl(data)
    if err:
        msg, code = err
        return jsonify({"error": msg}), code
    return jsonify(ok)
