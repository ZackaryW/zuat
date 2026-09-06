"""Agent-owned native plugin behavior."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

from zuat.specs.interface import PluginCapabilities
from zuat.specs.native import (
    Agent,
    PluginActivation,
    PluginLifecycleResult,
    PluginOperationError,
    PluginRecord,
    PluginRef,
    Scope,
    UnsupportedNativeOperation,
)
from zuat.utils.plugin_lifecycle import CommandPluginAdapter


class PiPluginAdapter(CommandPluginAdapter):
    agent = Agent.PI
    scopes = frozenset({Scope.USER, Scope.PROJECT})
    capabilities = PluginCapabilities(
        scopes, scopes, scopes, scopes, exact_versions=True
    )
    environment_variable = "PI_CODING_AGENT_DIR"
    config_directory = Path(".pi/agent")
    direct_sources = True

    def requested_version(self, ref):
        return (
            ref.native_ref.rsplit("@", 1)[1]
            if self.canonical_id(ref.native_ref) != ref.native_ref
            else None
        )

    @staticmethod
    def canonical_id(source: str) -> str:
        if source.startswith("npm:"):
            package = source[4:]
            split = package.rfind("@")
            return "npm:" + (package[:split] if split > 0 else package)
        return source

    def _find(self, records, ref):
        return next(
            (
                item
                for item in records
                if item.ref.native_ref == self.canonical_id(ref.native_ref)
                and item.ref.scope == ref.scope
            ),
            None,
        )

    def contextual_ref(self, ref):
        return replace(
            super().contextual_ref(ref), native_ref=self.canonical_id(ref.native_ref)
        )

    def install(self, ref, *, trust=False):
        self.validate_install(ref, trust=trust)
        canonical = self.canonical_id(ref.native_ref)
        if canonical != ref.native_ref:
            desired = PluginRecord(
                self.contextual_ref(ref),
                canonical.removeprefix("npm:").rsplit("/", 1)[-1],
                True,
                PluginActivation.PARTIAL,
                ref.native_ref.rsplit("@", 1)[1],
            )
            return self.reconcile(desired)
        return super().install(ref, trust=trust)

    def preflight(self, ref, operation, *, desired=None):
        self._validate(ref, operation)
        if desired is None:
            return
        current = self._find(self.discover(), ref)
        if current is not None and current.to_dict() == desired.to_dict():
            return
        if desired.revision is None:
            raise UnsupportedNativeOperation("plugin revision is unresolved")
        if (
            not ref.native_ref.startswith("npm:")
            or not re.fullmatch(
                r"\d+\.\d+\.\d+(?:-[\w.-]+)?(?:\+[\w.-]+)?", desired.revision.version
            )
            or desired.activation is not PluginActivation.PARTIAL
        ):
            raise UnsupportedNativeOperation(
                "exact plugin revision or activation restoration is unsupported"
            )

    def reconcile(self, desired):
        self.preflight(desired.ref, "install", desired=desired)
        before = self._find(self.discover(), desired.ref)
        if before and before.to_dict() == desired.to_dict():
            self._save_provenance(before.ref, before)
            return PluginLifecycleResult(
                "install", desired.ref, "current", before, before
            )
        pinned = PluginRef(
            self.agent,
            f"{desired.ref.native_ref}@{desired.revision.version}",
            desired.ref.scope,
            desired.ref.source,
        )
        if self._run(self.install_args(pinned)).returncode != 0:
            raise PluginOperationError("exact plugin installation failed")
        try:
            after = self._find(self.discover(), desired.ref)
        except PluginOperationError:
            return PluginLifecycleResult(
                "install", desired.ref, "indeterminate", before
            )
        verified = (
            after is not None
            and after.revision == desired.revision
            and after.activation == desired.activation
        )
        if verified:
            self._save_provenance(after.ref, after)
        return PluginLifecycleResult(
            "install",
            desired.ref,
            "installed" if verified else "indeterminate",
            before,
            after,
        )

    def contributions(self, record):
        from zuat.utils.plugin_resources import (
            json_document,
            skill_resources,
            declared_paths,
            excluded_resource,
        )
        from zuat.utils.runtime_paths import contained_path

        if record.runtime_root is None:
            return ()
        root = record.runtime_root
        manifest = json_document(root, "package.json").get("pi")
        if manifest is None:
            manifest = {"skills": ["skills"], "extensions": ["extensions"]}
        if not isinstance(manifest, dict):
            raise ValueError("invalid Pi resource manifest")
        skill_patterns = manifest.get("skills", [])
        hook_patterns = manifest.get("extensions", [])
        skill_roots = declared_paths(root, skill_patterns)
        found = list(
            skill_resources(
                root, [path.relative_to(root).as_posix() for path in skill_roots]
            )
        )
        for directory in skill_roots:
            if directory.is_dir():
                found.extend(
                    ("skill", contained_path(root, path).relative_to(root).as_posix())
                    for path in sorted(directory.glob("*.md"))
                    if path.name != "SKILL.md"
                )
        for path in declared_paths(root, hook_patterns):
            if path.exists():
                selected = contained_path(root, path)
                candidates = (selected,) if selected.is_file() else selected.iterdir()
                for candidate in candidates:
                    if candidate.suffix in {".js", ".ts"}:
                        found.append(
                            (
                                "hook",
                                contained_path(root, candidate)
                                .relative_to(root)
                                .as_posix(),
                            )
                        )
        return tuple(
            dict.fromkeys(
                (kind, identifier)
                for kind, identifier in found
                if not excluded_resource(
                    identifier, skill_patterns if kind == "skill" else hook_patterns
                )
            )
        )

    def _validate(self, ref: PluginRef, operation: str) -> None:
        super()._validate(ref, operation)
        if ref.scope is Scope.PROJECT and (
            not self.project_root or not self.trust_project
        ):
            raise PluginOperationError(
                "project plugin operations require project trust"
            )

    def discover(self, *, include_available: bool = False) -> tuple[PluginRecord, ...]:
        found = super().discover(include_available=include_available)
        if self.project_root and not self.trust_project:
            self.discovery_diagnostics += (
                "project plugin discovery requires project trust",
            )
        return found

    def _trust_flag(self, scope: Scope | None = None) -> str:
        return (
            "--approve"
            if self.trust_project and self.project_root and scope is not Scope.USER
            else "--no-approve"
        )

    def discovery_args(self) -> tuple[str, ...]:
        return ("pi", "list", self._trust_flag())

    def install_args(self, ref: PluginRef) -> tuple[str, ...]:
        return (
            "pi",
            "install",
            ref.native_ref,
            *(("--local",) if ref.scope is Scope.PROJECT else ()),
            self._trust_flag(ref.scope),
        )

    def remove_args(self, ref: PluginRef) -> tuple[str, ...]:
        return (
            "pi",
            "remove",
            ref.native_ref,
            *(("--local",) if ref.scope is Scope.PROJECT else ()),
            self._trust_flag(ref.scope),
        )

    def update_args(self, ref: PluginRef) -> tuple[tuple[str, ...], ...]:
        return (
            (
                "pi",
                "update",
                "--extension",
                ref.native_ref,
                self._trust_flag(ref.scope),
            ),
        )

    def update(self, ref: PluginRef) -> PluginLifecycleResult:
        self._validate(ref, "update")
        if ref.scope is Scope.PROJECT:
            records = self.discover()
            if any(
                item.ref.native_ref == ref.native_ref
                and item.ref.scope is not ref.scope
                for item in records
            ):
                raise UnsupportedNativeOperation(
                    "native update cannot isolate this plugin installation"
                )
        return super().update(ref)

    def decode(self, output: str) -> tuple[PluginRecord, ...]:
        if output.strip() == "No packages installed.":
            return ()
        records: list[PluginRecord] = []
        scope: Scope | None = None
        lines = output.splitlines()
        index = 0
        while index < len(lines):
            if lines[index] == "User packages:":
                scope = Scope.USER
            elif lines[index] == "Project packages:":
                scope = Scope.PROJECT
            elif (
                lines[index].startswith("  ")
                and not lines[index].startswith("    ")
                and scope is not None
            ):
                native_ref = lines[index].strip()
                if native_ref.endswith(" (filtered)"):
                    native_ref = native_ref.removesuffix(" (filtered)")
                if index + 1 >= len(lines) or not lines[index + 1].startswith("    "):
                    self.discovery_diagnostics += (
                        "configured plugin has no verified installation",
                    )
                    index += 1
                    continue
                runtime_root = Path(lines[index + 1].strip())
                if not runtime_root.is_dir():
                    self.discovery_diagnostics += (
                        "configured plugin has no verified installation",
                    )
                    index += 2
                    continue
                version = None
                manifest = runtime_root / "package.json"
                if manifest.is_file() and not manifest.is_symlink():
                    try:
                        version = json.loads(manifest.read_text(encoding="utf-8")).get(
                            "version"
                        )
                    except (
                        OSError,
                        UnicodeError,
                        json.JSONDecodeError,
                        AttributeError,
                    ) as error:
                        raise PluginOperationError(
                            "Pi plugin manifest has an unsupported shape"
                        ) from error
                canonical = self.canonical_id(native_ref)
                records.append(
                    PluginRecord(
                        PluginRef(
                            self.agent,
                            canonical,
                            scope,
                            native_ref.split(":", 1)[0] if ":" in native_ref else None,
                        ),
                        canonical.removeprefix("npm:").rsplit("/", 1)[-1],
                        True,
                        PluginActivation.PARTIAL,
                        installed_version=version,
                        runtime_root=runtime_root.resolve(),
                    )
                )
                index += 1
            index += 1
        if not any(line in {"User packages:", "Project packages:"} for line in lines):
            raise PluginOperationError("Pi plugin inventory has an unsupported shape")
        return tuple(records)
