"""Step 0/3 DoD — 결정론 경계 CI 게이트 (v2 §5·§8-2).

"배분·판정에 AI 금지"를 PDF가 아니라 **통과하는 테스트**로.
- anthropic(LLM)은 오직 Advisory Plane(`advisory.py`)에만 허용.
- apex.advisory import는 오직 serving bridge(`serving.py`)와 advisory 자신에만 허용.
- 결정론 코어(investor/optimizer/allocation/risk/compliance/cma/forward/…)는 둘 다 금지.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "apex"

# anthropic(LLM) import 허용 파일 = Advisory Plane만
_ANTHROPIC_ALLOWED = {"advisory.py"}
# apex.advisory import 허용 파일 = serving bridge + advisory 자신
_ADVISORY_IMPORT_ALLOWED = {"serving.py", "advisory.py"}


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
    """anthropic은 advisory.py에만, apex.advisory는 serving/advisory에만(AST 정적 검사)."""
    offenders: list[str] = []
    for py in _SRC.rglob("*.py"):
        name = py.name
        for mod in _imports(py):
            is_anthropic = mod == "anthropic" or mod.startswith("anthropic.")
            is_advisory = mod == "apex.advisory" or mod.startswith("apex.advisory.")
            if is_anthropic and name not in _ANTHROPIC_ALLOWED:
                offenders.append(f"{py.relative_to(_SRC)} → {mod}")
            if is_advisory and name not in _ADVISORY_IMPORT_ALLOWED:
                offenders.append(f"{py.relative_to(_SRC)} → {mod}")
    assert not offenders, "결정론 경계 위반: " + "; ".join(offenders)


def test_importing_core_does_not_load_anthropic():
    """pipeline·serving import 시 anthropic이 sys.modules에 실리지 않는다(런타임 경계).

    serving은 advisory를 import하지만 기본 Narrator가 룰 템플릿이라 anthropic 미로드.
    """
    import apex.pipeline  # noqa: F401
    import apex.serving  # noqa: F401

    assert not any(m == "anthropic" or m.startswith("anthropic.") for m in sys.modules)
