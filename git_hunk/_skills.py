"""Discovery and loading of bundled skill content for AI agents.

Skills live in a ``skills/<name>/SKILL.md`` tree shipped inside the package, so
the content an agent loads always matches the installed git-hunk version.
"""

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path
    content: str


def skills_root() -> Path:
    override = os.environ.get("GIT_HUNK_SKILLS_DIR")
    if override:
        return Path(override)
    return Path(__file__).parent / "skills"


def load_skills() -> list[Skill]:
    root = skills_root()
    if not root.is_dir():
        return []
    skills = []
    for child in sorted(root.iterdir()):
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"warning: could not read skill {skill_md}: {exc}", file=sys.stderr)
            continue
        meta = _parse_frontmatter(content)
        skills.append(
            Skill(
                name=meta.get("name") or child.name,
                description=meta.get("description", ""),
                path=child,
                content=content,
            )
        )
    return skills


def _parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    closed = False
    for line in lines[1:]:
        if line.strip() == "---":
            closed = True
            break
        match = re.match(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$", line)
        if match is not None:
            meta[match.group(1)] = match.group(2).strip()
    if not closed:
        # Frontmatter must be terminated; otherwise the body is not metadata.
        return {}
    return meta
