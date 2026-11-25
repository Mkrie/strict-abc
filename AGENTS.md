# AGENTS.md

## Project shape

- Distribution name is `strict-abc-lsp`; import name is `strict_abc`.
- Single-package src layout. `src/strict_abc/__init__.py` only re-exports the public API.
- `_meta.py` orchestrates class creation and keeps compatibility delegates for private helpers.
- `_signatures.py` is the pure calling-contract engine; `_types.py` handles variance;
  `_annotations.py` normalizes annotations; `_descriptors.py` introspects attributes;
  `_options.py` and `_errors.py` contain configuration and `LSPViolation`.
- Tests are split by validation domain under `tests/`, with deterministic differential
  coverage in `tests/test_signature_differential.py`. There are no fixtures, services,
  or external test dependencies.
- Validation runs at class-definition time in `StrictABCMeta.__new__`. Options come from
  `__strict_options__` and are merged across `__mro__`, with subclass keys overriding parents.

## Commands

Poetry is the only dependency manager; there is no `requirements.txt`.

```bash
make install   # poetry install
make lint      # ruff check .
make type      # mypy (strict, only src/strict_abc)
make test      # pytest
make cov       # coverage, enforces 90% locally
make all       # lint -> type -> test -> build -> twine check
```

- Single test: `poetry run pytest tests/test_strict_abc.py::test_name`
- Focused run: `poetry run pytest tests/test_strict_abc.py -k keyword`
- `pytest` sets `pythonpath = ["src"]`, so tests exercise the working tree without reinstalling.
- Pre-commit hooks run Ruff (with `--fix`), Ruff format, and mypy on commit; pytest runs on push. Install with `make pre-commit-install`.
- CI (`.github/workflows/ci.yml`) runs Ruff, mypy, and pytest with `--cov-fail-under=85` on Python 3.10–3.13. `v*` tags publish to PyPI.

## Constraints and quirks

- Keep code compatible with Python 3.10+ (`target-version = "py310"`). Do not use 3.11+ syntax or APIs.
- Ruff: line length 100, rules `E F I UP B SIM C4`; tests ignore `B024`, `B027`, `F841`. Format with `make format`.
- mypy is `strict = true` but only checks `src/strict_abc`; tests are not type-checked.
- `_annotations.normalize_annotation` resolves string annotations via `eval` only after an AST safety filter. Preserve or strengthen that filter; never add unrestricted evaluation.
- Descriptor and signature inspection in `_descriptors.py` deliberately skips unsupported or unreadable attributes (`TypeError`, `ValueError`, `NameError`) instead of failing class creation. Preserve this defensive behavior when extending validation.
- Keep the private static-method delegates on `StrictABCMeta` unless a deliberate compatibility change is planned.

## Versioning and docs

- The version is duplicated and not read dynamically: bump both `pyproject.toml` (`[tool.poetry].version`) and `__version__` in `src/strict_abc/_meta.py`.
- Update `CHANGELOG.md` for user-facing changes; `README.md` documents the public behavior and every `__strict_options__` key.
- `make all` builds into `dist/` and runs `twine check dist/*`; `dist/` is gitignored.

## Local scratch files

- `collect_af.py` and `collected_*.txt` are untracked/gitignored local helpers. Do not commit them or treat them as project source.