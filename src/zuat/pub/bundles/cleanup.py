"""Cleanup after complete native removal, never before or from cached success."""

from zuat.pub.bundles.models import BundleCleanupError
from zuat.pub.bundles.targets import observe
from zuat.specs.interface import ResolutionError
from zuat.utils.bundles.removal import remove_trees


def purge(service, record):
    """Keep the registration until both output trees are gone for explicit retry.

    Absence is checked again even after an earlier failed cleanup: a cached
    absent target may since have been installed manually. No native marketplace
    deregistration or cache deletion is implied by compiler-output cleanup.
    """
    try:
        for target in record.targets:
            resolver = service._resolver(target.agent)
            adapter = resolver.bundle_adapter()
            if (
                adapter is not None
                and observe(resolver.plugin_adapter(), adapter.reference(record))
                is not None
            ):
                raise ValueError("target still installed")
        root = service._bundles.root
        remove_trees(
            root,
            (root / "builds" / record.bundle_id, root / "catalogs" / record.bundle_id),
        )
    except (OSError, ValueError, TypeError, KeyError, ResolutionError):
        raise BundleCleanupError(
            "generated output cleanup failed; registration retained for explicit retry"
        ) from None
