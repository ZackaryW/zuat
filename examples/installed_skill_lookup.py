"""Locate installed skills read-only, using only a disposable home and project.

Run: python examples/installed_skill_lookup.py
Nothing outside the temporary directory is read or written, and Zuat creates no
registry: lookup is registry-independent.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from zuat.pub import locate_skill


def write_skill(root: Path, folder: str, name: str) -> Path:
    skill = root / folder
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: example\n---\nProcedure.\n", encoding="utf-8"
    )
    return skill


def main() -> None:
    with tempfile.TemporaryDirectory() as scratch:
        home = Path(scratch) / "home"
        project = Path(scratch) / "project"
        (project / ".git").mkdir(parents=True)
        nested = project / "src"
        nested.mkdir()

        # One copy under the user's Codex home: lookup succeeds from any directory.
        user = write_skill(home / ".codex" / "skills", "review-helper", "pspec-tdd")
        found = locate_skill("codex", "pspec-tdd", cwd=nested, home=home)
        print(found.outcome, found.provenance, found.root == user.resolve())

        # A same-named project copy: Codex never picks one, so selection is unresolved.
        mine = write_skill(project / ".agents" / "skills", "pspec-tdd", "pspec-tdd")
        both = locate_skill("codex", "pspec-tdd", cwd=nested, home=home)
        print(both.outcome, [candidate.path.name for candidate in both.candidates])

        # The host reported which copy it loaded; pass that path as evidence.
        chosen = locate_skill("codex", "pspec-tdd", cwd=nested, home=home, selected=mine)
        print(chosen.outcome, chosen.provenance, chosen.entrypoint == mine.resolve() / "SKILL.md")

        # Other agents and unknown names report classified outcomes, never exceptions.
        print(locate_skill("claude", "pspec-tdd", cwd=nested, home=home).outcome)
        print(locate_skill("gemini", "pspec-tdd", cwd=nested, home=home).outcome)


if __name__ == "__main__":
    main()
