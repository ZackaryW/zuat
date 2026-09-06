import json
import tomllib
from pathlib import Path

from zuat.pub import AssetInput, OperationStatus, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for
from zuat.gitcore import GitRegistry


class EmptyPlugins:
    def discover(self):
        return ()


def claude_service(tmp_path: Path, commands: tuple[str, ...]):
    home = tmp_path / "home"
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps(
            {
                "model": "unrelated",
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": command}]}
                        for command in commands
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "claude",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    return Zuat(registry=registry, resolvers={"claude": resolver}), registry, settings


def hook_at(service: Zuat, index: int, agent: str = "claude"):
    observed = service.status(ZuatRequest(agents=(agent,))).assets
    return next(item for item in observed if item.ref.locator.endswith(f"/{index}"))


def kimi_service(tmp_path: Path, commands: tuple[tuple[str, str], ...]):
    home = tmp_path / "home"
    settings = home / ".kimi-code/config.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        'model = "unrelated"\n\n'
        + "\n".join(
            f'[[hooks]]\nevent = "{event}"\ncommand = "{command}"\n'
            for event, command in commands
        ),
        encoding="utf-8",
    )
    registry = GitRegistry(tmp_path / "registry")
    resolver = resolver_for(
        "kimi",
        home=home,
        state_root=registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    return Zuat(registry=registry, resolvers={"kimi": resolver}), registry, settings


def test_adopt_and_uninstall_one_hook_preserve_neighbors_and_settings(
    tmp_path: Path,
) -> None:
    service, registry, settings = claude_service(tmp_path, ("one", "two"))
    try:
        first = hook_at(service, 0)
        adopted = service.install(
            ZuatRequest(agents=("claude",), asset_refs=(first.ref.id,))
        )
        assert adopted.status is OperationStatus.SUCCESS

        removed = service.uninstall(
            ZuatRequest(agents=("claude",), asset_refs=(first.ref.id,))
        )
        assert removed.status is OperationStatus.SUCCESS
        document = json.loads(settings.read_text(encoding="utf-8"))
        assert document["model"] == "unrelated"
        assert [
            item["hooks"][0]["command"]
            for item in document["hooks"]["SessionStart"]
        ] == ["two"]
    finally:
        registry.close()


def test_force_replaces_changed_hook_at_its_locator_without_duplication(
    tmp_path: Path,
) -> None:
    service, registry, settings = claude_service(tmp_path, ("original",))
    desired = tmp_path / "desired.json"
    desired.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "original"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    try:
        first = hook_at(service, 0)
        assert service.install(
            ZuatRequest(agents=("claude",), asset_refs=(first.ref.id,))
        ).ok
        document = json.loads(settings.read_text(encoding="utf-8"))
        document["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "user-edit"
        settings.write_text(json.dumps(document), encoding="utf-8")
        request = ZuatRequest(
            agents=("claude",),
            assets=(
                AssetInput(
                    agent="claude",
                    kind="hook",
                    name="SessionStart-000",
                    locator=first.ref.locator,
                    source=str(desired),
                ),
            ),
        )

        rejected = service.install(request)
        assert rejected.status is OperationStatus.FAILED
        forced = service.install(
            ZuatRequest(agents=request.agents, assets=request.assets, force=True)
        )
        assert forced.status is OperationStatus.SUCCESS
        updated = json.loads(settings.read_text(encoding="utf-8"))
        assert updated["model"] == "unrelated"
        assert updated["hooks"]["SessionStart"] == [
            {"hooks": [{"type": "command", "command": "original"}]}
        ]

        reverted = service.revert(
            ZuatRequest(
                agents=("claude",),
                operation_id=forced.operation_id,
                force=True,
            )
        )
        assert reverted.status is OperationStatus.SUCCESS
        restored = json.loads(settings.read_text(encoding="utf-8"))
        assert restored["model"] == "unrelated"
        assert restored["hooks"]["SessionStart"] == [
            {"hooks": [{"type": "command", "command": "user-edit"}]}
        ]
    finally:
        registry.close()


def test_force_restores_owned_hook_when_its_recorded_locator_is_missing(
    tmp_path: Path,
) -> None:
    service, registry, settings = claude_service(tmp_path, ("original",))
    desired = tmp_path / "SessionStart-000.json"
    try:
        first = hook_at(service, 0)
        source = registry.observation_root / str(
            first.evidence["normalized_path"]
        )
        desired.write_bytes(source.read_bytes())
        assert service.install(
            ZuatRequest(agents=("claude",), asset_refs=(first.ref.id,))
        ).ok
        document = json.loads(settings.read_text(encoding="utf-8"))
        document.pop("hooks")
        settings.write_text(json.dumps(document), encoding="utf-8")

        restored = service.install(
            ZuatRequest(
                agents=("claude",),
                assets=(
                    AssetInput(
                        agent="claude",
                        kind="hook",
                        name="SessionStart-000",
                        locator=first.ref.locator,
                        source=str(desired),
                    ),
                ),
                force=True,
            )
        )

        assert restored.status is OperationStatus.SUCCESS
        updated = json.loads(settings.read_text(encoding="utf-8"))
        assert updated["model"] == "unrelated"
        assert updated["hooks"]["SessionStart"] == [
            {"hooks": [{"type": "command", "command": "original"}]}
        ]
    finally:
        registry.close()


def test_force_restores_owned_hooks_to_their_stable_locators(
    tmp_path: Path,
) -> None:
    service, registry, settings = claude_service(tmp_path, ("one", "two"))
    try:
        observed = service.status(ZuatRequest(agents=("claude",))).assets
        hooks = tuple(item for item in observed if item.ref.kind == "hook")
        sources: list[Path] = []
        for item in hooks:
            source = registry.observation_root / str(
                item.evidence["normalized_path"]
            )
            copied = tmp_path / Path(str(item.evidence["normalized_path"])).name
            copied.write_bytes(source.read_bytes())
            sources.append(copied)
        assert service.install(
            ZuatRequest(
                agents=("claude",),
                asset_refs=tuple(item.ref.id for item in hooks),
            )
        ).ok
        document = json.loads(settings.read_text(encoding="utf-8"))
        document["hooks"]["SessionStart"].reverse()
        settings.write_text(json.dumps(document), encoding="utf-8")

        restored = service.install(
            ZuatRequest(
                agents=("claude",),
                assets=tuple(
                    AssetInput(
                        agent="claude",
                        kind="hook",
                        name=str(item.evidence["asset_name"]),
                        locator=item.ref.locator,
                        source=str(source),
                    )
                    for item, source in zip(hooks, sources)
                ),
                force=True,
            )
        )

        assert restored.status is OperationStatus.SUCCESS
        updated = json.loads(settings.read_text(encoding="utf-8"))
        assert [
            item["hooks"][0]["command"]
            for item in updated["hooks"]["SessionStart"]
        ] == ["one", "two"]
    finally:
        registry.close()


def test_installing_one_hook_does_not_remove_owned_unprofiled_skills(
    tmp_path: Path,
) -> None:
    service, registry, settings = claude_service(tmp_path, ("one",))
    native_skill = settings.parent / "skills/reviewer/SKILL.md"
    native_skill.parent.mkdir(parents=True)
    native_skill.write_text(
        "---\nname: reviewer\ndescription: Review\n---\nReview.\n",
        encoding="utf-8",
    )
    try:
        observed = service.status(ZuatRequest(agents=("claude",))).assets
        skill = next(item for item in observed if item.ref.kind == "skill")
        hook = next(item for item in observed if item.ref.kind == "hook")
        assert service.install(
            ZuatRequest(agents=("claude",), asset_refs=(skill.ref.id,))
        ).ok
        registry.set_profile_assets("default", ())

        installed = service.install(
            ZuatRequest(agents=("claude",), asset_refs=(hook.ref.id,))
        )

        assert installed.status is OperationStatus.SUCCESS
        assert native_skill.exists()
        assert native_skill.read_text(encoding="utf-8").endswith("Review.\n")
    finally:
        registry.close()


def test_toml_hook_adoption_and_uninstall_preserve_neighbor_and_settings(
    tmp_path: Path,
) -> None:
    service, registry, settings = kimi_service(
        tmp_path, (("Start", "one"), ("Stop", "two"))
    )
    try:
        first = hook_at(service, 0, "kimi")
        assert service.install(
            ZuatRequest(agents=("kimi",), asset_refs=(first.ref.id,))
        ).ok

        removed = service.uninstall(
            ZuatRequest(agents=("kimi",), asset_refs=(first.ref.id,))
        )

        assert removed.status is OperationStatus.SUCCESS
        document = tomllib.loads(settings.read_text(encoding="utf-8"))
        assert document["model"] == "unrelated"
        assert document["hooks"] == [{"event": "Stop", "command": "two"}]
    finally:
        registry.close()


def test_toml_hook_force_and_revert_restore_displaced_fragment(
    tmp_path: Path,
) -> None:
    service, registry, settings = kimi_service(tmp_path, (("Start", "original"),))
    desired = tmp_path / "desired.toml"
    desired.write_text(
        '[[hooks]]\nevent = "Start"\ncommand = "original"\n',
        encoding="utf-8",
    )
    try:
        first = hook_at(service, 0, "kimi")
        assert service.install(
            ZuatRequest(agents=("kimi",), asset_refs=(first.ref.id,))
        ).ok
        settings.write_text(
            'model = "unrelated"\n\n[[hooks]]\nevent = "Start"\ncommand = "user-edit"\n',
            encoding="utf-8",
        )
        forced = service.install(
            ZuatRequest(
                agents=("kimi",),
                assets=(
                    AssetInput(
                        agent="kimi",
                        kind="hook",
                        name="Start-000",
                        locator=first.ref.locator,
                        source=str(desired),
                    ),
                ),
                force=True,
            )
        )
        assert forced.status is OperationStatus.SUCCESS

        reverted = service.revert(
            ZuatRequest(
                agents=("kimi",),
                operation_id=forced.operation_id,
                force=True,
            )
        )

        assert reverted.status is OperationStatus.SUCCESS
        document = tomllib.loads(settings.read_text(encoding="utf-8"))
        assert document["model"] == "unrelated"
        assert document["hooks"] == [
            {"event": "Start", "command": "user-edit"}
        ]
    finally:
        registry.close()
