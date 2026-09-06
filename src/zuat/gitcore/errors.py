"""Domain errors raised by the internal Git registry layer."""


class RegistryError(RuntimeError):
    """A registry operation could not be completed safely."""


class GitUnavailableError(RegistryError):
    """The required Git executable is unavailable."""


class InvalidRegistryPathError(RegistryError):
    """A caller supplied a path outside the managed working tree."""


class RegistryLockedError(RegistryError):
    """Another Zuat operation owns the registry lock."""
