import json

from test_plugin_adapters import Runner, adapter
from zuat.specs.codex_plugins import CodexPluginAdapter
from zuat.specs.claude_plugins import ClaudePluginAdapter
from zuat.specs.kimi_plugins import KimiPluginAdapter


def test_codex_resources_use_installed_cache_not_catalog_source(tmp_path):
    cached = tmp_path / "home/.codex/plugins/cache/team/review/1.0"
    (cached / "skills/review").mkdir(parents=True)
    (cached / "skills/review/SKILL.md").write_text("BUNDLED")
    (cached / "hooks").mkdir()
    (cached / "hooks/hooks.json").write_text('{"hooks":{"Stop":[{"hooks":[]}]}}')
    body = {"installed": [{"pluginId": "review@team", "name": "review", "installed": True, "enabled": True, "version": "1.0", "source": {"source": "local", "path": str(tmp_path / "catalog")}}]}
    native = adapter(CodexPluginAdapter, tmp_path, Runner([json.dumps(body)]))
    record = native.discover()[0]
    assert record.runtime_root == cached
    assert set(native.contributions(record)) == {("skill", "skills/review"), ("hook", "hooks/Stop/0")}


def test_codex_missing_cache_does_not_turn_catalog_version_into_revision(tmp_path):
    body = {"installed": [{"pluginId": "review@team", "name": "review", "installed": True, "enabled": True, "version": "catalog-version"}]}
    native = adapter(CodexPluginAdapter, tmp_path, Runner([json.dumps(body)]))
    record = native.discover()[0]
    assert record.revision is None
    assert record.runtime_root is None
    assert native.discovery_diagnostics


def test_claude_default_and_declared_resources_are_additive(tmp_path):
    root = tmp_path / "plugin"
    for directory in ["skills/default", "extra/extra", ".claude-plugin"]:
        (root / directory).mkdir(parents=True)
    (root / "skills/default/SKILL.md").write_text("DEFAULT")
    (root / "extra/extra/SKILL.md").write_text("EXTRA")
    (root / ".claude-plugin/plugin.json").write_text('{"skills":"./extra", "hooks":"./other.json"}')
    (root / "other.json").write_text('{"hooks":{"Stop":[{"hooks":[]}]}}')
    body = [{"id": "review@team", "scope": "user", "version": "1", "installPath": str(root)}]
    native = adapter(ClaudePluginAdapter, tmp_path, Runner([json.dumps(body)]))
    found = native.contributions(native.discover()[0])
    assert {item for item in found if item[0] == "skill"} == {("skill", "skills/default"), ("skill", "extra/extra")}
    assert any(kind == "hook" for kind, _ in found)


def test_kimi_installed_record_resolves_manifest_revision_and_contributions(tmp_path):
    root = tmp_path / "managed/review"
    (root / "skills/review").mkdir(parents=True)
    (root / "skills/review/SKILL.md").write_text("KIMI PLUGIN BODY")
    (root / "kimi.plugin.json").write_text('{"name":"review","version":"release-one","skills":"./skills", "hooks":[{"event":"Stop","command":"PRIVATE BODY"}]}')
    inventory = tmp_path / "home/.kimi-code/plugins/installed.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(json.dumps({"version":1,"plugins":[{"id":"review","root":str(root),"source":"local","enabled":False}]}))
    native = adapter(KimiPluginAdapter, tmp_path, Runner())
    record = native.discover()[0]
    assert record.revision.version == "release-one"
    assert record.runtime_root == root
    assert record.activation == "inactive"
    assert set(native.contributions(record)) == {("skill","skills/review"), ("hook","hooks/Stop/0")}


def test_kimi_root_skill_has_safe_provider_local_identifier(tmp_path):
    from zuat.specs.kimi import KimiResolver
    root = tmp_path / "managed/review"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("KIMI ROOT BODY")
    (root / "kimi.plugin.json").write_text('{"name":"review"}')
    inventory = tmp_path / "home/.kimi-code/plugins/installed.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(json.dumps({"version":1,"plugins":[{"id":"review","root":str(root),"enabled":True}]}))
    native = adapter(KimiPluginAdapter, tmp_path, Runner())
    record = native.discover()[0]
    assert record.revision is None
    assert native.contributions(record) == (("skill", "SKILL.md"),)


def test_pi_manifest_patterns_and_omitted_types_do_not_load_default_resources(tmp_path):
    from zuat.specs.pi_plugins import PiPluginAdapter
    root = tmp_path / "package"
    (root / "extensions").mkdir(parents=True)
    (root / "skills/default").mkdir(parents=True)
    (root / "skills/default/SKILL.md").write_text("NOT DECLARED")
    (root / "extensions/public.ts").write_text("PUBLIC EXTENSION")
    (root / "extensions/private.ts").write_text("NOT DECLARED")
    (root / "package.json").write_text('{"name":"review","version":"1","pi":{"extensions":["extensions/*.ts","!extensions/private.ts"]}}')
    native = adapter(PiPluginAdapter, tmp_path, Runner([f"User packages:\n  npm:review\n    {root}\n"]))
    assert native.contributions(native.discover()[0]) == (("hook", "extensions/public.ts"),)


def test_claude_command_skills_follow_manifest_override(tmp_path):
    root = tmp_path / "plugin"
    for directory in ("commands", "extra", ".claude-plugin"):
        (root / directory).mkdir(parents=True)
    (root / "commands/default.md").write_text("DEFAULT COMMAND")
    (root / "extra/review.md").write_text("DECLARED COMMAND")
    (root / ".claude-plugin/plugin.json").write_text('{"commands":["./extra/review.md"]}')
    body = [{"id":"review@team","scope":"user","version":"1","installPath":str(root)}]
    native = adapter(ClaudePluginAdapter, tmp_path, Runner([json.dumps(body)]))
    assert native.contributions(native.discover()[0]) == (("skill", "extra/review.md"),)
