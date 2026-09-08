import json
from dataclasses import asdict

import pytest
from click.testing import CliRunner

from zuat import pub
from zuat.cli.app import cli


def test_add_doctor_purge_public_workflow(tmp_path, source):
    root, home, store = (tmp_path / p for p in ("tracking", "home", "store"))
    context = {"root": root, "home": home, "bundle_root": store}
    args = [
        "--root",
        str(root),
        "bundle",
        "--home",
        str(home),
        "--bundle-root",
        str(store),
    ]
    runner = CliRunner()
    added = runner.invoke(
        cli,
        [*args, "add", str(source), "--name", "simple", "--agent", "kimi", "--json"],
    )
    assert added.exit_code == 1, added.output
    value = json.loads(added.output)["result"]
    assert value["targets"][0]["status"] == "unsupported"
    identifier = value["bundle_id"]
    output = pub.resolve_bundle(identifier, agent="claude", **context)
    checked = runner.invoke(
        cli, [*args, "doctor", identifier, "--agent", "kimi", "--json"]
    )
    assert checked.exit_code == 1, checked.output
    assert json.loads(checked.output)["result"] == json.loads(
        json.dumps(asdict(pub.doctor_bundle(identifier, agents=("kimi",), **context)))
    )
    removed = runner.invoke(cli, [*args, "remove", identifier, "--purge", "--json"])
    assert removed.exit_code == 0, removed.output
    assert json.loads(removed.output)["result"]["outputs_removed"]
    assert not output.exists()
    assert pub.list_bundles(**context) == ()


def test_add_forwards_all_options(tmp_path, monkeypatch):
    seen = []

    def add(source, **kwargs):
        seen.append((source, kwargs))
        return pub.BundleOperationResult(
            "example",
            "bootstrap",
            (pub.BundleTarget("claude", "example", None, "success"),),
        )

    monkeypatch.setattr(pub, "add_bundle", add)
    result = CliRunner().invoke(
        cli,
        [
            "bundle",
            "--bundle-root",
            str(tmp_path),
            "add",
            "source",
            "--name",
            "named",
            "--revision",
            "main",
            "--agent",
            "claude",
            "--trust",
            "--force",
        ],
    )
    assert result.exit_code == 0, result.output
    assert seen == [
        (
            "source",
            {
                "bundle_root": tmp_path,
                "home": None,
                "root": None,
                "name": "named",
                "revision": "main",
                "agents": ("claude",),
                "trust": True,
                "force": True,
            },
        )
    ]


@pytest.mark.parametrize("healthy", [True, False])
@pytest.mark.parametrize("json_output", [True, False])
def test_doctor_exit_and_presentation(monkeypatch, healthy, json_output):
    check = pub.BundleCheck("manager", "claude", "ok" if healthy else "unavailable")
    report = pub.BundleDiagnostics("example", (check,))
    monkeypatch.setattr(pub, "doctor_bundle", lambda *args, **kwargs: report)
    result = CliRunner().invoke(
        cli, ["bundle", "doctor", "example", *(["--json"] if json_output else [])]
    )
    assert result.exit_code == (0 if healthy else 1), result.output
    if json_output:
        assert json.loads(result.output)["result"]["checks"][0] == asdict(check)
    else:
        assert "claude" in result.output
        assert check.status in result.output
