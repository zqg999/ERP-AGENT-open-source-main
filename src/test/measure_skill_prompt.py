"""Compare skill prompt characters against the pre-change Git baseline (not tokens)."""
import ast
import json
import logging
import subprocess
from pathlib import Path

from src.agent.progressive_skills import SkillCatalog


def main():
    root = Path(__file__).resolve().parents[2]
    source = subprocess.check_output([
        "git", "show", "baseline/pre-progressive-skills-20261009:src/agent/main_agent.py"
    ], cwd=root, text=True)
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == "_load_skills_prompt")
    namespace = {"Path": Path, "agent_logger": logging.getLogger(__name__)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "baseline", "exec"), namespace)
    skills = root / "src/skills"
    before = namespace["_load_skills_prompt"](skills)
    catalog = SkillCatalog(skills)
    after = catalog.index()
    print(json.dumps({
        "builtin_skills": len(catalog.entries()[0]),
        "before_characters": len(before), "after_characters": len(after),
        "reduction_percent": round((1-len(after)/len(before))*100, 2) if before else None,
        "scope": "skill system-prompt segment only; excludes tool schemas and subsequent reads; not token/cost measurement",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
