"""Resolver selection without cross-agent fallback."""

from pathlib import Path

from zuat.specs.claude import ClaudeResolver
from zuat.specs.codex import CodexResolver
from zuat.specs.interface import AgentResolver, ResolutionError
from zuat.specs.kimi import KimiResolver
from zuat.specs.pi import PiResolver

_RESOLVERS = {
    "codex": CodexResolver,
    "claude": ClaudeResolver,
    "kimi": KimiResolver,
    "pi": PiResolver,
}


def resolver_for(
    agent: str,
    *,
    home: str | Path | None = None,
    project_root: str | Path | None = None,
    state_root: str | Path | None = None,
    plugins: object | None = None,
    trust_project: bool = False,
) -> AgentResolver:
    try:
        implementation = _RESOLVERS[agent]
    except KeyError as error:
        raise ResolutionError(f"unsupported agent: {agent}") from error
    return implementation(
        home=home,
        project_root=project_root,
        state_root=state_root,
        plugins=plugins,
        trust_project=trust_project,
    )


def resolvers_for(
    agents: tuple[str, ...],
    *,
    home: str | Path | None = None,
    project_root: str | Path | None = None,
    state_root: str | Path | None = None,
) -> tuple[AgentResolver, ...]:
    return tuple(
        resolver_for(
            agent,
            home=home,
            project_root=project_root,
            state_root=state_root,
        )
        for agent in agents
    )
