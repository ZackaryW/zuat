"""One target, one explicit attempt; force allows deletion, not reconciliation."""

from dataclasses import asdict, replace

from zuat.gitcore import RegistryError
from zuat.pub.bundles.models import BundleError, BundleOutputError, BundleTarget
from zuat.specs.interface import ResolutionError
from zuat.specs.native import PluginOperationError, UnsupportedNativeOperation


def observe(native, ref):
    """Incomplete or duplicate native inventory is never evidence of absence."""
    records = native.discover()
    if native.discovery_diagnostics:
        raise ValueError("native-inventory-incomplete")
    matches = [
        item
        for item in records
        if item.ref.native_ref == ref.native_ref
        and item.ref.scope == ref.scope
        and item.installed
    ]
    if len(matches) > 1:
        raise ValueError("foreign-or-ambiguous-target")
    return matches[0] if matches else None


def recover(service):
    """Existing recovery is observation-only; never bypass an unresolved marker."""
    if service.registry.recovery_marker.exists():
        service.recover_plugins()
    if service.registry.recovery_marker.exists():
        raise ValueError("native-operation-unresolved")


class TargetAttempt:
    def __init__(self, service, state, record, agent, build=None):
        self.service = service
        self.state = state
        self.record = record
        self.agent = agent
        self.build = build
        self.data = state["bundles"][record.bundle_id]
        self.prior = next(
            (t for t in self.data["targets"] if t["agent"] == agent), None
        )
        self.target = BundleTarget(
            agent,
            self.prior["plugin_id"] if self.prior else record.name,
            self.prior.get("build_revision") if self.prior else None,
            "indeterminate",
        )
        self.managed = bool(self.prior and self.prior.get("managed"))

    def save(self, *, status, reason=None, attempt=None, build_revision=None):
        self.target = replace(
            self.target,
            status=status,
            reason=reason,
            attempt=attempt,
            build_revision=build_revision
            if build_revision is not None
            else self.target.build_revision,
        )
        self.data["targets"] = [
            t for t in self.data["targets"] if t["agent"] != self.agent
        ] + [{**asdict(self.target), "managed": self.managed}]
        self.service._bundles.write(self.state)
        return self.target

    def bind(self):
        resolver = self.service._resolver(self.agent)
        self.adapter = resolver.bundle_adapter()
        if self.adapter is None:
            raise UnsupportedNativeOperation("bundle-bootstrap-unsupported")
        self.native = resolver.plugin_adapter()
        self.ref = self.adapter.reference(self.record)
        self.target = replace(self.target, plugin_id=self.ref.native_ref)

    def known(self, observed):
        if observed is None:
            return
        outputs = tuple(
            self.service._bundles.root
            / "builds"
            / self.record.bundle_id
            / b.build_revision
            / self.agent
            for b in self.record.builds
        )
        if (
            not self.managed
            or not self.adapter.matches(self.record, observed, outputs)
            or observed.installed_version not in {b.version for b in self.record.builds}
        ):
            raise ValueError("foreign-or-ambiguous-target")

    def observe(self):
        """Keep observed native version/activation separate from a proposed build."""
        current = observe(self.native, self.ref)
        self.target = replace(
            self.target,
            installed_version=current.installed_version if current else None,
            activation=current.activation.value if current else None,
        )
        return current

    def mutate(self, action, ref):
        recover(self.service)
        self.save(status="indeterminate", attempt=action)
        if action == "install":
            result = self.service.install_plugin(ref, trust=True)
        elif action == "update":
            result = self.service.update_plugin(ref)
        else:
            result = self.service.remove_plugin(ref)
        recover(self.service)
        return result

    def bootstrap(self, *, trust, force):
        try:
            self.bind()
            if not trust:
                return self.save(status="failed", reason="source-trust-required")
            output = self.service.resolve_bundle(
                self.record.bundle_id,
                build_revision=self.build.build_revision,
                agent=self.agent,
            )
            self.adapter.initialize(self.native)
            recover(self.service)
            current = self.observe()
            self.known(current)
            if current is not None and current.installed_version == self.build.version:
                return self.save(
                    status="current", build_revision=self.build.build_revision
                )
            self.save(status="indeterminate", attempt="prepare")
            route = self.adapter.prepare(
                self.native, self.record, output, self.service._bundles.root
            )
            if current is not None:
                result = self.mutate("update", self.ref)
                current = self.observe()
                self.known(current)
                if (
                    current is not None
                    and current.installed_version == self.build.version
                ):
                    if not result.ok:
                        return self.save(
                            status="indeterminate", reason="native-operation-unverified"
                        )
                    return self.save(
                        status="success", build_revision=self.build.build_revision
                    )
                if not force:
                    return self.save(status="failed", reason="update-unverified")
                # A failed update may have removed its target. Do not remove an
                # unrelated name match, and do not execute another update/retry.
                if current is not None:
                    removal = self.mutate("remove", self.ref)
                    current = self.observe()
                    if current is not None:
                        return self.save(status="failed", reason="removal-unverified")
                    if not removal.ok:
                        return self.save(
                            status="indeterminate", reason="removal-unverified"
                        )
            self.managed = True
            result = self.mutate("install", route)
            current = self.observe()
            if current is None:
                return self.save(status="failed", reason="installation-absent")
            self.known(current)
            if not result.ok:
                # Target presence cannot override the lower-level transaction's
                # failed neighbor/integrity checks; retain an honest outcome.
                return self.save(
                    status="indeterminate", reason="native-operation-unverified"
                )
            if current.installed_version != self.build.version:
                return self.save(
                    status="indeterminate", reason="installed-version-unverified"
                )
            return self.save(status="success", build_revision=self.build.build_revision)
        except BundleOutputError:
            return self.save(status="unavailable", reason="build-output-unavailable")
        except UnsupportedNativeOperation:
            return self.save(
                status="unsupported", reason="bundle-bootstrap-unsupported"
            )
        except PluginOperationError as error:
            return self.save(
                status="unavailable"
                if str(error) == "plugin manager unavailable"
                else "indeterminate",
                reason="native-manager-unavailable"
                if str(error) == "plugin manager unavailable"
                else "native-operation-unverified",
            )
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ResolutionError,
            RegistryError,
            BundleError,
        ) as error:
            reason = (
                str(error)
                if isinstance(error, ValueError)
                and str(error)
                in {
                    "foreign-or-ambiguous-target",
                    "native-inventory-incomplete",
                    "native-operation-unresolved",
                }
                else "bundle-attempt-unverified"
            )
            return self.save(status="indeterminate", reason=reason)

    def remove(self):
        if not self.managed:
            # An unsupported/untrusted selection never claimed an installation.
            # Forget that historical attempt without deleting a foreign plugin.
            return self.save(status="absent")
        try:
            self.bind()
            recover(self.service)
            current = self.observe()
            self.known(current)
            if current is not None:
                result = self.mutate("remove", self.ref)
                if self.observe() is not None:
                    return self.save(status="failed", reason="removal-unverified")
                if not result.ok:
                    return self.save(
                        status="indeterminate", reason="removal-unverified"
                    )
            self.managed = False
            return self.save(status="absent")
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ResolutionError,
            RegistryError,
            BundleError,
        ):
            return self.save(status="indeterminate", reason="removal-unverified")
