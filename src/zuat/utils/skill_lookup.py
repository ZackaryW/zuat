"""Agent-neutral, read-only mechanics for locating an installed skill.

Nothing here selects behavior by agent identity or writes anything: agent
resolvers supply roots and policy, and this module only reads skill metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zuat.specs.native import InvalidAssetError
from zuat.utils.assets import _NAME, _frontmatter


def directory_chain(cwd: str | Path, *, marker: str = ".git") -> tuple[Path, ...]:
    """Directories from ``cwd`` up to the nearest ancestor holding ``marker``.

    The marker may be a directory or a file (worktrees). Without any marker only
    ``cwd`` is returned: hosts do not search above a non-repository directory.
    """
    start = Path(cwd).expanduser().resolve()
    chain: list[Path] = []
    for directory in (start, *start.parents):
        chain.append(directory)
        if (directory / marker).exists():
            return tuple(chain)
    return (start,)


class SkillIdentityError(Exception):
    """A skill entrypoint whose declared identity cannot be established.

    ``kind`` is ``missing``, ``unreadable``, or ``malformed`` so callers can map
    each to an outcome without parsing messages.
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True, slots=True)
class SkillTier:
    """One native skills directory an agent searches, supplied by its resolver."""

    label: str
    scope: str
    root: Path
    follow_symlinks: bool = False


def tiers_under(
    bases: tuple[Path, ...],
    relative: str,
    *,
    scope: str,
    follow_symlinks: bool,
    label: str | None = None,
) -> tuple[SkillTier, ...]:
    """One tier per base directory, each rooted at ``base / relative``."""
    return tuple(
        SkillTier(label or scope, scope, base / relative, follow_symlinks)
        for base in bases
    )


@dataclass(frozen=True, slots=True)
class Candidate:
    """An installed copy of the requested skill; ``root`` is its canonical location."""

    tier: str
    scope: str
    path: Path
    root: Path
    via_symlink: bool = False


@dataclass(frozen=True, slots=True)
class TierScan:
    candidates: tuple[Candidate, ...] = ()
    invalid: tuple[tuple[Path, str], ...] = ()
    unsupported: tuple[tuple[Path, str], ...] = ()


def scan_tier(tier: SkillTier, name: str) -> TierScan:
    """Find copies of ``name`` in one tier, reading only identity metadata.

    Entries that cannot be the requested skill never matter, however broken. An
    entry whose folder is named for the skill but whose identity cannot be
    verified is reported invalid, since a host may still select it.
    """
    root = tier.root
    if not root.is_dir():
        return TierScan()
    candidates: list[Candidate] = []
    invalid: list[tuple[Path, str]] = []
    unsupported: list[tuple[Path, str]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except OSError as error:
        return TierScan(invalid=((root, f"cannot list skills in {root}: {error}"),))
    for entry in entries:
        if entry.name.startswith("."):
            continue
        linked = root.is_symlink() or entry.is_symlink()
        if not entry.is_dir():
            if entry.is_symlink() and entry.name == name:
                invalid.append((entry, f"dangling symbolic link for skill {name}: {entry}"))
            continue
        try:
            declared = read_skill_identity(entry)
        except SkillIdentityError as error:
            if entry.name == name:
                invalid.append((entry, str(error)))
            continue
        if declared != name:
            continue
        if linked and not tier.follow_symlinks:
            unsupported.append(
                (entry, f"symbolic link is not supported for this agent: {entry}")
            )
            continue
        candidates.append(
            Candidate(tier.label, tier.scope, entry, entry.resolve(), linked)
        )
    return TierScan(tuple(candidates), tuple(invalid), tuple(unsupported))


@dataclass(frozen=True, slots=True)
class SkillSearch:
    """An agent's native search description for one invocation.

    ``tiers`` are scanned for candidates. ``unmodeled`` locations are scanned
    only so a match there can prevent a confident answer. ``prefer`` is the
    native scope order for same-named copies; empty means the agent has no
    verified rule. ``disabled`` holds canonical roots natively switched off.
    ``blocking`` always prevents selection (evidence the agent could not read);
    ``evidence_errors`` prevent it only when several copies compete.
    """

    tiers: tuple[SkillTier, ...]
    unmodeled: tuple[SkillTier, ...] = ()
    prefer: tuple[str, ...] = ()
    disabled: frozenset[Path] = frozenset()
    blocking: tuple[str, ...] = ()
    evidence_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Selection:
    outcome: str
    selected: Candidate | None = None
    provenance: str | None = None
    candidates: tuple[Candidate, ...] = ()
    diagnostics: tuple[str, ...] = ()


def _deduplicate(candidates: list[Candidate]) -> tuple[Candidate, ...]:
    """One installation reached through several paths is still one installation."""
    seen: set[Path] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        if candidate.root not in seen:
            seen.add(candidate.root)
            unique.append(candidate)
    return tuple(unique)


def _listing(candidates: tuple[Candidate, ...]) -> tuple[str, ...]:
    return tuple(f"{candidate.tier} copy: {candidate.path}" for candidate in candidates)


def _canonical(path: str | Path) -> Path:
    given = Path(path).expanduser()
    if given.name == "SKILL.md":
        given = given.parent
    return given.resolve()


def _validate_selected(
    selected: str | Path,
    name: str,
    agent: str,
    candidates: tuple[Candidate, ...],
    problems: list[tuple[Path, str]],
) -> Selection:
    target = _canonical(selected)
    for candidate in candidates:
        if candidate.root == target:
            return Selection("located", candidate, "caller-evidence", candidates)
    for path, message in problems:
        if path.resolve() == target:
            return Selection("invalid", candidates=candidates, diagnostics=(message,))
    return Selection(
        "invalid",
        candidates=candidates,
        diagnostics=(
            f"selected path is not an installed {agent} candidate for skill {name}: {selected}",
            *_listing(candidates),
        ),
    )


def select_skill(
    search: SkillSearch,
    name: str,
    *,
    agent: str,
    selected: str | Path | None = None,
) -> Selection:
    """Classify the lookup: caller evidence, then verified native evidence, else unresolved.

    A choice is made only from evidence; when none applies the result is
    ``unresolved`` with every candidate listed rather than a guessed winner.
    """
    scans = [scan_tier(tier, name) for tier in search.tiers]
    shadows = [scan_tier(tier, name) for tier in search.unmodeled]
    candidates = _deduplicate([c for scan in scans for c in scan.candidates])
    hidden = _deduplicate([c for scan in shadows for c in scan.candidates])
    problems = [item for scan in (*scans, *shadows) for item in scan.invalid]
    if selected is not None:
        return _validate_selected(
            selected, name, agent, _deduplicate([*candidates, *hidden]), problems
        )
    invalid = [item for scan in scans for item in scan.invalid]
    if invalid:
        return Selection(
            "invalid", candidates=candidates, diagnostics=tuple(m for _, m in invalid)
        )
    unsupported = [item for scan in scans for item in scan.unsupported]
    if unsupported:
        return Selection(
            "unsupported",
            candidates=candidates,
            diagnostics=tuple(m for _, m in unsupported),
        )
    shadowing = [
        *(f"{c.tier} copy: {c.path}" for c in hidden),
        *(f"{path}" for scan in shadows for path, _ in (*scan.invalid, *scan.unsupported)),
    ]
    if shadowing:
        roots = ", ".join(str(tier.root) for tier in search.unmodeled)
        return Selection(
            "unresolved",
            candidates=candidates,
            diagnostics=(
                f"{agent} skill {name} may be shadowed by an unmodeled location ({roots}); "
                "pass the installed path the host selected",
                *shadowing,
                *_listing(candidates),
            ),
        )
    if search.blocking:
        return Selection(
            "unresolved",
            candidates=candidates,
            diagnostics=(*search.blocking, *_listing(candidates)),
        )
    active = tuple(c for c in candidates if c.root not in search.disabled)
    removed = tuple(c for c in candidates if c.root in search.disabled)
    if not active:
        notes = tuple(f"skill {name} is disabled natively: {c.path}" for c in removed)
        return Selection(
            "missing",
            candidates=candidates,
            diagnostics=(f"no installed {agent} skill named {name}", *notes),
        )
    if len(active) == 1:
        return Selection(
            "located",
            active[0],
            "native-config" if removed else "single-candidate",
            candidates,
        )
    if search.evidence_errors:
        return Selection(
            "unresolved",
            candidates=candidates,
            diagnostics=(*search.evidence_errors, *_listing(active)),
        )
    for scope in search.prefer:
        group = tuple(c for c in active if c.scope == scope)
        if len(group) == 1:
            return Selection("located", group[0], "native-rule", candidates)
        if group:
            break
    return Selection(
        "unresolved",
        candidates=candidates,
        diagnostics=(
            f"{agent} has no verified rule selecting among {len(active)} copies of skill {name}",
            *_listing(active),
        ),
    )


def read_skill_identity(skill_dir: Path) -> str:
    """Return the name declared in ``SKILL.md`` reading only that one file.

    Identity is the declared name, not the folder name. Supporting resources are
    neither listed nor read, so cost does not grow with skill size.
    """
    entrypoint = skill_dir / "SKILL.md"
    if not skill_dir.is_dir():
        raise SkillIdentityError("missing", f"skill directory not found: {skill_dir}")
    if not entrypoint.is_file():
        raise SkillIdentityError("missing", f"skill requires SKILL.md: {skill_dir}")
    try:
        content = entrypoint.read_bytes()
    except OSError as error:
        raise SkillIdentityError(
            "unreadable", f"cannot read skill {skill_dir}: {error}"
        ) from error
    try:
        name = _frontmatter(content).get("name")
    except InvalidAssetError as error:
        raise SkillIdentityError("malformed", f"{entrypoint}: {error}") from error
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise SkillIdentityError(
            "malformed", f"{entrypoint}: frontmatter requires a valid name"
        )
    return name
