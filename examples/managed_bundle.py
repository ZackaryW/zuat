"""Public-only bundle example using a temporary home, never real agent settings."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from zuat.pub import PluginArtifactContext, Zuat, ZuatExtension


class ReviewTools(ZuatExtension):
    identifier = "review-tools"
    version = "1"

    def locate_artifacts(self, context: PluginArtifactContext) -> tuple[Path, ...]:
        return (context.runtime_root / "skills/reviewer/SKILL.md",)

    def bootstrap(self, state: Zuat, bundle_id: str, agent: str):
        """Hosts explicitly invoke this method; registration never invokes it."""
        return state.bootstrap_bundle(bundle_id, agents=(agent,), trust=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=("codex", "claude", "pi"), default="claude")
    agent = parser.parse_args().agent
    with TemporaryDirectory(prefix="zuat-bundle-example-") as temporary:
        base = Path(temporary)
        source = base / "source" / "reviewer"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            "---\nname: reviewer\ndescription: Review changes\n---\nReview carefully.\n",
            encoding="utf-8",
        )
        context = {"root": base / "tracking", "home": base / "home"}
        with Zuat(**context) as state:
            state.register_extension(ReviewTools())
            assert state.list_bundles() == ()
            build = state.build_bundle(source, name="review-tools")
            assert state.get_bundle(build.bundle_id).targets == ()
        with Zuat(**context) as state:
            extension = ReviewTools()
            state.register_extension(extension)
            assert state.resolve_bundle(build.bundle_id, agent=agent).is_dir()
            installed = extension.bootstrap(state, build.bundle_id, agent)
            assert installed.ok, installed
            assert installed.targets[0].installed_version == build.version
            artifacts = state.resolve_artifacts(agent, extension.identifier)
            assert artifacts and artifacts[0].paths[0].is_file()
            assert state.remove_bundle(build.bundle_id).ok
            assert state.list_bundles() == ()
        print(
            "Build, reopen, native bootstrap, artifact resolution and removal verified."
        )


if __name__ == "__main__":
    main()
