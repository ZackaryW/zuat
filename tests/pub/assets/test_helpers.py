from zuat import pub


def test_module_helpers_share_explicit_home_and_project_context(tmp_path):
    source = tmp_path / "package/reviewer"
    source.mkdir(parents=True)
    document = source / "SKILL.md"
    initial = "---\nname: reviewer\ndescription: Review\n---\nA\n"
    document.write_text(initial, encoding="utf-8")
    context = {
        "root": tmp_path / "registry",
        "home": tmp_path / "home",
        "project_root": tmp_path / "a",
        "trust_project": True,
    }
    asset = pub.AssetInput("kimi", "skill", scope="project", source=str(source))
    assert pub.inspect_asset(asset, **context).classification == "absent"
    installed = pub.install(
        pub.ZuatRequest(agents=("kimi",), assets=(asset,)), **context
    )
    assert installed.ok, installed.diagnostics
    selected = pub.AssetSelector("kimi", kind="skill", scope="project")
    assert pub.list_assets(selected, **context).assets[0].ref == installed.assets[0].ref
    document.write_text(initial + "B", encoding="utf-8")
    updated = pub.update_asset(asset, **context)
    assert updated.ok, updated.diagnostics
    assert pub.restore_all(updated.operation_id, selected, force=True, **context).ok
    assert pub.uninstall_all(selected, **context).ok
    assert pub.inspect_asset(asset, **context).classification == "absent"
    assert not (tmp_path / "home/.kimi-code/skills/reviewer").exists()


def test_install_and_inspect_accept_the_same_skill_document_input(tmp_path):
    source = tmp_path / "package/SKILL.md"
    source.parent.mkdir()
    source.write_text(
        "---\nname: reviewer\ndescription: Review\n---\nA", encoding="utf-8"
    )
    asset = pub.AssetInput("kimi", "skill", scope="project", source=str(source))
    with pub.Zuat(
        root=tmp_path / "registry", home=tmp_path / "home", project_root=tmp_path / "a"
    ) as state:
        assert state.inspect_asset(asset).classification == "absent"
        installed = state.install(pub.ZuatRequest(agents=("kimi",), assets=(asset,)))
        assert installed.ok, installed.diagnostics
        assert state.inspect_asset(asset).classification == "current"
