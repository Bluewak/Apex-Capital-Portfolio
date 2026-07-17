"""Step 0 DoD — 결정론 경계 CI 게이트 (v2 §5·§8-2).

"배분·판정에 AI 금지"를 PDF가 아니라 **통과하는 테스트**로. 결정론 코어 모듈의
import 그래프에 LLM(anthropic) / Advisory Plane(apex.advisory)이 없어야 한다.
LLM은 오직 격리된 Advisory Plane(미래 `apex.advisory`)에만 허용된다.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "apex"

# 결정론 코어(DETERMINISM_REQUIRED=True). report는 룰 템플릿 폴백이라 서술 계층이지만,
# 현 단계에선 그 역시 anthropic 비의존이어야 한다(향후 advisory 분리 시 예외 부여).
_FORBIDDEN_PREFIXES = ("anthropic", "apex.advisory")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_core_modules_do_not_import_llm():
    """모든 apex 모듈이 anthropic/apex.advisory를 import하지 않는다(AST 정적 검사)."""
    offenders: list[str] = []
    for py in _SRC.rglob("*.py"):
        for mod in _imports(py):
            if any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES):
                offenders.append(f"{py.relative_to(_SRC)} → {mod}")
    assert not offenders, "결정론 경계 위반(LLM import): " + "; ".join(offenders)


def test_importing_pipeline_does_not_load_anthropic():
    """pipeline import 시 anthropic이 sys.modules에 실리지 않는다(런타임 경계)."""
    import apex.pipeline  # noqa: F401

    assert not any(m == "anthropic" or m.startswith("anthropic.") for m in sys.modules)
