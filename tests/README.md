# Test layout

Group tests by the boundary they exercise; let directories carry repeated context
instead of encoding the whole hierarchy in each filename.

```text
tests/
  cli/              Command dispatch and output
  gitcore/          Private journal and persistence
  pub/              Public Python contracts and orchestration
    assets/         Independent skill/hook workflows
    plugins/        Plugin lifecycle, recovery, and artifact policy
  specs/            Native agent models and resolution
    plugins/        Native plugin adapters and revisions
  utils/            Shared agent-neutral mechanics
```

Use focused names such as `pub/assets/test_update.py` and
`pub/plugins/test_recovery.py`. Keep descriptive test function names: shortening
filenames should not obscure the behavior a failing test describes.

Each directory is a Python package so pytest can distinguish repeated filenames
such as `test_models.py` and `test_recovery.py`. Shared test helpers use qualified
`tests.…` imports; do not depend on collection order or add directories to
`sys.path` to resolve another test module.

Run the whole suite from the repository root:

```sh
uv run --extra cli pytest -q
uv run --extra cli behave --format progress
```

Run a focused area or file directly:

```sh
uv run --extra cli pytest tests/pub/assets -q
uv run --extra cli pytest tests/specs/plugins/test_adapters.py -q
```

The cross-component Behave scenarios remain under `features/`. Test fixtures use
temporary agent homes and registries; running tests must not modify real agent
settings. Archived verification records retain their historical filenames;
current change evidence uses the nested paths above.
