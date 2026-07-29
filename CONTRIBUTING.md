# Contributing

Contributions are welcome.

## Development setup

```bash
make install
make pre-commit-install
```

## Checks

Run all checks:

```bash
make all
```

Individual checks:

```bash
make lint
make format
make type
make test
make cov
make build
make check
```

## Coding style

This project uses:

- `ruff` for linting and formatting;
- `mypy` for strict type checking;
- `pytest` for tests.

Before opening a pull request, please make sure:

```bash
make all
```

passes.

## Tests

If you change behavior, please add or update tests in:

```text
tests/
```

Aim to keep coverage high.

## Pull request checklist

- [ ] Tests pass.
- [ ] Linting passes.
- [ ] Type checking passes.
- [ ] Documentation is updated if needed.
- [ ] `CHANGELOG.md` is updated if the change is user-facing.

## Commit messages

Please use clear commit messages.

Examples:

```text
Add support for keyword-only parameter validation
Fix false positive for classmethod signatures
Update documentation for check_return_type
```
