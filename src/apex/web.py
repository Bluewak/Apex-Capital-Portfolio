"""웹 브리지 (v2 §7) — 무터미널 서빙. **의존성 0**(stdlib http.server).

설문 폼 GET / → JSON POST /advice → serving.run_advice → HTML 리포트 즉시 반환.
"CLI 절벽"을 없애되 FastAPI 등 벤더 의존 없이. 핵심 로직은 순수 함수 ``handle_advice``
로 분리해 서버 없이 단위 테스트한다. 원장 봉인은 라이브 서버(do_POST)에서만.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

from apex import report, serving, store
from apex.schemas import SurveyAnswers
from apex.serving import AdviceCommand

_FORM = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Apex 설문</title>
<style>body{font:15px/1.6 -apple-system,"Malgun Gothic",sans-serif;max-width:560px;margin:2rem auto;padding:0 1rem}
label{display:block;margin:.7rem 0 .2rem;font-weight:600}select,input{width:100%;padding:.5rem;font-size:15px}
button{margin-top:1.2rem;padding:.7rem 1.4rem;font-size:15px;cursor:pointer}small{color:#667}</style></head>
<body><h1>Apex 분석 리포트 설문</h1>
<small>분석·교육용 예시 리포트(개별 투자권유 아님). 원금 손실 가능.</small>
<form id="f">
<label>나이</label><input name="q1_age" type="number" value="62">
<label>투자 기간(1 단기 ~ 5 장기)</label><input name="q2_horizon" type="number" min="1" max="5" value="3">
<label>목적</label><select name="q3_objective"><option>보전</option><option>균형</option><option>증식</option></select>
<label>투자 원금(원)</label><input name="q4_capital" type="number" value="100000000">
<label>월 적립(원)</label><input name="q5_monthly" type="number" value="0">
<label>감내 가능 연손실(예: -0.05 = -5%)</label><input name="q6_max_loss" type="number" step="0.01" value="-0.05">
<label>투자 경험</label><select name="q7_experience"><option>없음</option><option>보통</option><option>많음</option></select>
<label>유동성 필요</label><select name="q8_liquidity"><option>낮음</option><option selected>보통</option><option>높음</option></select>
<label>환율 태도</label><select name="q9_fx"><option>회피</option><option>일부허용</option><option>허용</option></select>
<label>급락 시 행동</label><select name="q10_behavior"><option>매도</option><option>유지</option><option>추가매수</option></select>
<button type="submit">분석 리포트 생성</button></form>
<script>
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();
const fd=new FormData(e.target),o={input_snapshot_id:'web'};
for(const[k,v]of fd)o[k]=['q1_age','q2_horizon','q4_capital','q5_monthly'].includes(k)?parseInt(v):
(k==='q6_max_loss'?parseFloat(v):v);
const r=await fetch('/advice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(o)});
document.open();document.write(await r.text());document.close();});
</script></body></html>"""


def handle_advice(body: bytes) -> tuple[int, str]:
    """JSON 설문 바이트 → (status, HTML). 순수(원장 미기록) — 서버 없이 테스트 가능."""
    try:
        answers = SurveyAnswers(**json.loads(body))
    except Exception as e:  # noqa: BLE001 — 입력 검증 실패는 400로 안내(서버 중단 아님)
        return 400, f"<!doctype html><meta charset=utf-8><pre>입력 오류: {escape(str(e))}</pre>"
    res = serving.run_advice(AdviceCommand(answers=answers))
    return 200, report.render(res, answers)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, _FORM)
        else:
            self._send(404, "<pre>not found</pre>")

    def do_POST(self) -> None:
        if self.path != "/advice":
            self._send(404, "<pre>not found</pre>")
            return
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n)
        status, html = handle_advice(body)
        if status == 200:  # 라이브 서버에서만 원장 봉인
            try:
                answers = SurveyAnswers(**json.loads(body))
                res = serving.run_advice(AdviceCommand(answers=answers))
                store.append_run(res, answers, "web", "KRW", datetime.now(UTC).isoformat())
            except Exception:  # noqa: BLE001 — 원장 실패가 응답을 막지 않음
                pass
        self._send(status, html)

    def _send(self, code: int, html: str) -> None:
        b = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *args: object) -> None:  # 서버 로그 억제
        pass


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    """블로킹 웹 서버 실행(Ctrl+C 종료)."""
    HTTPServer((host, port), _Handler).serve_forever()
