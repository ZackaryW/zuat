import subprocess
import sys


def test_public_types_are_exported_without_loading_implementation_adapters() -> None:
    script = """
import sys
import zuat.pub
from zuat import AssetInput, OperationResult, OperationStatus, ZuatRequest
assert ZuatRequest().force is False
assert AssetInput and OperationStatus
assert OperationResult
assert 'zuat.pub' in sys.modules
assert 'zuat.utils.resolvers' not in sys.modules
assert 'git' not in sys.modules
assert 'zuat.gitcore.repository' not in sys.modules
assert 'zuat.specs.codex' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_base_import_does_not_import_optional_click_or_internal_adapters() -> None:
    script = """
import sys
import zuat
assert 'click' not in sys.modules
assert 'git' not in sys.modules
assert 'zuat.gitcore.repository' not in sys.modules
assert 'zuat.specs.codex' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_cli_imports_public_surface_without_loading_internal_resolvers() -> None:
    script = """
import sys
import zuat.cli.app
assert 'zuat.pub' in sys.modules
assert 'zuat.utils.resolvers' not in sys.modules
assert 'zuat.specs.registry' not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_internal_utils_are_not_an_alternate_public_command_surface() -> None:
    script = """
import zuat.pub as public
import zuat.utils as internal
assert callable(public.status)
assert not hasattr(internal, 'status')
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_missing_cli_extra_has_guidance_without_traceback() -> None:
    script = """
import sys
sys.modules['click'] = None
from zuat import main
main([])
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert completed.returncode != 0
    assert "install 'zuat[cli]'" in completed.stderr
    assert "Traceback" not in completed.stderr
