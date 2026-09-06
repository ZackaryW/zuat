import json

from click.testing import CliRunner

from zuat import pub
from zuat.cli.app import cli
from tests.pub.bundles.test_build import source


def test_build_list_status_python_parity(tmp_path, source):
    runner = CliRunner()
    root, home, store = (tmp_path / part for part in ("tracking", "home", "bundles"))
    args = [
        "--root",
        str(root),
        "bundle",
        "--home",
        str(home),
        "--bundle-root",
        str(store),
    ]
    result = runner.invoke(
        cli, [*args, "build", str(source), "--name", "cli-bundle", "--json"]
    )
    assert result.exit_code == 0, result.output
    built = json.loads(result.output)["result"]
    record = pub.get_bundle(built["bundle_id"], root=root, home=home, bundle_root=store)
    assert record.builds[0].build_revision == built["build_revision"]
    listed = runner.invoke(cli, [*args, "list", "--json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["result"][0]["bundle_id"] == record.bundle_id
    status = runner.invoke(cli, [*args, "status", record.bundle_id, "--json"])
    assert status.exit_code == 0, status.output
    assert json.loads(status.output)["result"]["targets"] == []
    removed = runner.invoke(cli, [*args, "remove", record.bundle_id, "--json"])
    assert removed.exit_code == 0, removed.output
    assert pub.list_bundles(root=root, home=home, bundle_root=store) == ()


def test_bootstrap_forwards_selection_trust_and_force(tmp_path, monkeypatch):
    seen = []
    result = pub.BundleOperationResult(
        "example",
        "bootstrap",
        (pub.BundleTarget("kimi", "example", None, "unsupported"),),
    )

    def bootstrap(identifier, **kwargs):
        seen.append((identifier, kwargs))
        return result

    monkeypatch.setattr(pub, "bootstrap_bundle", bootstrap)
    command = CliRunner().invoke(
        cli,
        [
            "bundle",
            "--bundle-root",
            str(tmp_path),
            "bootstrap",
            "example",
            "--build-revision",
            "a" * 64,
            "--agent",
            "kimi",
            "--trust",
            "--force",
            "--json",
        ],
    )
    assert command.exit_code == 1
    assert seen[0][0] == "example"
    assert seen[0][1]["agents"] == ("kimi",)
    assert seen[0][1]["force"] is True
    assert seen[0][1]["trust"] is True
    assert seen[0][1]["bundle_root"] == tmp_path
    assert seen[0][1]["build_revision"] == "a" * 64
    assert json.loads(command.output)["result"]["targets"][0]["status"] == "unsupported"
