"""Report Generator — PipelineResult → 룰기반 자연어 HTML 리포트 (04 §2, 08 §6·§9·§10, M6).

규제 하드요구(§4-5): 유형 귀속형 프레이밍·면책·원금손실/과거성과 무보장 고지.
분기: ok(예시 배분+IPS+disclosed 안심) / downgrade(사유 렌더) / hold(교육 대안, 대체 포트 금지).
"""
from __future__ import annotations

from html import escape

from apex.universe import ASSET_CLASS, CLASS_COLOR, CLASS_LABEL

# 용어집 (툴팁, R4 이해도 레이어)
_GLOSSARY = {
    "SAA": "Strategic Asset Allocation · 장기 기준 배분 비율",
    "MDD": "Maximum Drawdown · 고점 대비 최대 하락폭",
    "VaR": "Value at Risk · 특정 확률에서의 예상 최대 손실",
    "CAGR": "연복리 수익률",
    "평시": "위기 3구간(2008·2020·2022)을 제외한 정상 시장 기준",
}
_CSS = """
:root{--bg:#eef1f4;--card:#fff;--ink:#16202f;--muted:#586576;--line:#d9e0e8;--accent:#0e5a63;
--good:#2c7a5b;--warn:#a3641b;--hold:#a2413a;--soft:#0e5a6314}
@media(prefers-color-scheme:dark){:root{--bg:#0b0f14;--card:#141b23;--ink:#e7ecf2;--muted:#9aa7b6;
--line:#26313c;--accent:#3ba7a0;--good:#4cae82;--warn:#d29a4d;--hold:#d38177;--soft:#3ba7a01f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,"Malgun Gothic","Noto Sans KR",Segoe UI,sans-serif;letter-spacing:-.003em}
.wrap{max-width:760px;margin:0 auto;padding:28px 20px 64px}
.eyebrow{font:600 11px/1 ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
h1{font-size:26px;margin:.3em 0 .2em;letter-spacing:-.02em}
h2{font-size:16px;margin:26px 0 8px}
.sub{color:var(--muted);font-size:14px;margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-top:14px}
.disclaimer{background:var(--soft);border:1px solid color-mix(in srgb,var(--accent) 26%,transparent);
border-radius:10px;padding:11px 14px;font-size:12.5px;margin-top:16px}
.callout{border-radius:11px;padding:13px 15px;margin:14px 0;font-size:13.5px;border:1px solid var(--line)}
.callout .lab{font:700 10.5px/1 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;display:block;margin-bottom:5px}
.c-warn{background:color-mix(in srgb,var(--warn) 12%,transparent);border-color:color-mix(in srgb,var(--warn) 26%,transparent)}
.c-warn .lab{color:var(--warn)}
.c-hold{background:color-mix(in srgb,var(--hold) 12%,transparent);border-color:color-mix(in srgb,var(--hold) 30%,transparent)}
.c-hold .lab{color:var(--hold)}
.c-disc{background:var(--bg)}.c-disc .lab{color:var(--warn)}
.bar{display:flex;height:26px;border-radius:7px;overflow:hidden;border:1px solid var(--line);margin:10px 0 8px}
.bar span{display:flex;align-items:center;justify-content:center;color:#fff;font:600 10.5px ui-monospace,monospace;min-width:0}
.leg{display:flex;flex-wrap:wrap;gap:5px 14px;font-size:12px;color:var(--muted)}
.leg i{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin:14px 0}
.metrics .m{background:var(--card);padding:10px 12px}
.metrics .lab{font:10px ui-monospace,monospace;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.metrics .v{font-size:18px;font-weight:660;font-variant-numeric:tabular-nums;margin-top:2px}
.neg{color:var(--hold)}.pos{color:var(--good)}
.ips{white-space:pre-wrap;font-size:13.5px;color:var(--ink)}
abbr{border-bottom:1px dotted var(--accent);cursor:help;text-decoration:none}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
td:first-child,th:first-child{text-align:left}
.foot{margin-top:22px;padding-top:14px;border-top:1px solid var(--line);font-size:11.5px;color:var(--muted);line-height:1.5}
.chip{display:inline-block;font:600 11px ui-monospace,monospace;padding:3px 9px;border-radius:999px}
.chip.ok{background:color-mix(in srgb,var(--good) 14%,transparent);color:var(--good)}
.chip.warn{background:color-mix(in srgb,var(--warn) 14%,transparent);color:var(--warn)}
.chip.hold{background:color-mix(in srgb,var(--hold) 14%,transparent);color:var(--hold)}
"""


def _term(t: str) -> str:
    return f'<abbr title="{escape(_GLOSSARY[t])}">{t}</abbr>'


def _alloc_bar(weights: dict[str, float]) -> str:
    by: dict[str, float] = {}
    for tk, w in weights.items():
        by[ASSET_CLASS[tk]] = by.get(ASSET_CLASS[tk], 0.0) + w
    segs = "".join(
        f'<span style="flex:{w:.4f};background:{CLASS_COLOR[code]}">{CLASS_LABEL[code]} {w:.0%}</span>'
        for code, w in sorted(by.items(), key=lambda kv: -kv[1])
    )
    legend = " ".join(
        f'<span><i style="background:{CLASS_COLOR[ASSET_CLASS[tk]]}"></i>{escape(tk)} {w:.0%}</span>'
        for tk, w in sorted(weights.items(), key=lambda kv: -kv[1])
    )
    return f'<div class="bar">{segs}</div><div class="leg">{legend}</div>'


def _stress_block(risk) -> str:
    if not risk.stress:
        return ""
    rows = "".join(
        f"<tr><td>{escape(s.scenario)}</td><td class='neg'>{s.loss:.0%}</td>"
        f"<td>{escape(s.top_contributor or '')}</td></tr>"
        for s in risk.stress
    )
    return (
        f'<div class="callout c-disc"><span class="lab">참고 공시 · 극단 시장(차단 아님)</span>'
        f'아래는 20년에 몇 번 오는 극단 구간의 {_term("평시")}과 다른 실측 손실입니다. '
        f'이 유형도 이때는 크게 빠졌으나 역사적으로 회복해 왔습니다(미래 보장 아님).'
        f'<table><thead><tr><th>구간</th><th>손실</th><th>최대 기여</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _body(result, answers) -> str:
    prof = escape(result.final_profile)
    parts: list[str] = []

    # 재보정 관문 (모순 주문, R5) — 발행/보류에 앞서 먼저 고지
    if result.reelicitation:
        parts.append(
            f'<div class="callout c-warn"><span class="lab">먼저 확인해 주세요 · 재보정</span>'
            f"{escape(result.reelicitation)}</div>"
        )

    # 강등 사유 렌더 (downgrade, R4 CS 티켓5)
    if result.downgrade_path and result.decision == "ok":
        steps = "".join(f"<li>{escape(s)}</li>" for s in result.downgrade_path)
        parts.append(
            f'<div class="callout c-warn"><span class="lab">등급 조정 안내 (시스템 오류 아님)</span>'
            f"요청 등급의 예상 손실이 감내 한도를 초과해 아래와 같이 한 등급씩 조정되었습니다:"
            f"<ul>{steps}</ul></div>"
        )

    if result.decision == "hold":
        parts.append(
            f'<div class="callout c-hold"><span class="lab">배정 보류</span>'
            f"{escape(result.explanation)}</div>"
            f'<div class="callout"><span class="lab">교육용 대안(권유 아님)</span>'
            f"감내 한도를 −10%까지 넓히면 안정형 예시를, 전액 현금성(예금·MMF 성격)이면 "
            f"기대수익 ~연 3%를 참고하실 수 있습니다. 개인 맞춤 배분은 표시하지 않습니다. "
            f"전문가 상담 예약은 자문업 등록 완료 후 활성화됩니다(현재 준비 중)."
        )
        return "\n".join(parts)

    # ok 분기
    r = result.risk
    parts.append(f'<div class="card"><h2>{prof} 유형 예시 배분 '
                 f'<span class="chip ok">발행</span></h2>{_alloc_bar(result.allocation.weights)}</div>')
    parts.append(
        '<div class="metrics">'
        f'<div class="m"><div class="lab">기대 {_term("CAGR")}</div>'
        f'<div class="v pos">{(result.expected_cagr or 0):.1%}</div></div>'
        f'<div class="m"><div class="lab">평시 vol</div><div class="v">{r.vol_annual:.1%}</div></div>'
        f'<div class="m"><div class="lab">평시 {_term("MDD")}</div>'
        f'<div class="v neg">{r.mdd:.1%}</div></div>'
        f'<div class="m"><div class="lab">평시 {_term("VaR")}95</div>'
        f'<div class="v">{r.var95_annual:.1%}</div></div></div>'
    )
    parts.append(_stress_block(r))
    # 환효과 분리 표기 (환회피 응답 기본, R4 행동재무 갭2)
    if answers.q9_fx == "회피":
        usd = r.currency_exposure.get("USD", 1.0)
        parts.append(
            f'<div class="callout c-disc"><span class="lab">환효과 분리 · 환회피 응답 반영</span>'
            f"원화 표시 수익 = <b>자산손익 + 환손익</b>입니다. 이 배분은 USD 노출 약 {usd:.0%}라 "
            f"원화 기준 손익의 상당 부분이 환율에 좌우됩니다(원화 강세 시 손실 확대). "
            f"MVP는 환헤지를 제공하지 않아, 환회피 응답을 이 분리 고지로 반영합니다."
            f"</div>"
        )
    if result.ips is not None:
        parts.append(f'<div class="card"><h2>투자정책서(IPS) · 예시</h2>'
                     f'<div class="ips">{escape(result.ips.rendered_text)}</div></div>')
    return "\n".join(p for p in parts if p)


def render(result, answers) -> str:
    """PipelineResult → 자립형 HTML 리포트 문자열."""
    chip = {"ok": "ok", "hold": "hold"}.get(result.decision, "ok")  # 최종 decision=ok|hold
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apex 분석 리포트 · {escape(result.final_profile)} 유형</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
  <div class="eyebrow">Apex · 분석·교육용 리포트 (개별 자문 아님)</div>
  <h1>{escape(result.final_profile)} 유형 <span class="chip {chip}">{escape(result.decision)}</span></h1>
  <p class="sub">귀하의 응답은 <b>{escape(result.final_profile)} 유형</b>에 해당합니다(위험점수 {result.risk_score}).
  아래는 해당 유형의 예시이며 개인 지시가 아닙니다.</p>
  {_body(result, answers)}
  <div class="foot">
    ※ 본 리포트는 <b>유형별 교육·분석 정보</b>이며 개별 투자자문·투자권유가 아닙니다.
    원금 손실이 발생할 수 있으며 과거 성과는 미래 수익을 보장하지 않습니다. 레버리지·인버스 ETF 제외.<br>
    기준 데이터 시점 <b>{escape(result.data_version)}</b> · 동일 시점·동일 응답이면 결과가 동일합니다(재현성 해시 {escape(result.result_hash[:12])}…).
  </div>
</div></body></html>"""
