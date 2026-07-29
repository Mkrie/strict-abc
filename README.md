# strict-abc

![CI](https://github.com/Mkrie/strict-abc/actions/workflows/ci.yml/badge.svg)
[![PyPI version](https://img.shields.io/pypi/v/strict-abc-lsp.svg)](https://pypi.org/project/strict-abc-lsp/)
[![Python versions](https://img.shields.io/pypi/pyversions/strict-abc.svg)](https://pypi.org/project/strict-abc/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/mypy-checked-2A6DB2.svg)](http://mypy-lang.org/)

`strict-abc` provides `StrictABCMeta` and `StrictABC`, which validate concrete
implementations of abstract methods at class definition time.

The goal is to fail fast when a subclass violates LSP-friendly signature rules.

## Installation

```bash
pip install strict-abc-lsp
```

## Usage

```python
from abc import abstractmethod

from strict_abc import StrictABC


class BaseService(StrictABC):
    @abstractmethod
    def process(self, data: dict, cache: bool = True) -> str:
        ...


class ValidService(BaseService):
    def process(self, data: dict, cache: bool = True) -> str:
        return "ok"
```

This works.

But this raises `TypeError` at class definition time:

```python
class InvalidService(BaseService):
    def process(self, data: dict, cache: bool) -> str:
        return "ok"
```

Because removing a default value strengthens the precondition.

## Options

Configure validation with `__strict_options__`:

```python
class Base(StrictABC):
    __strict_options__ = {
        "check_names": True,
        "check_defaults": True,
        "check_types": True,
        "check_return_type": True,
    }

    @abstractmethod
    def fetch(self, url: str) -> bytes:
        ...
```

Default options:

```python
{
    "check_names": False,
    "check_defaults": True,
    "check_types": False,
    "check_return_type": False,
}
```

## Development

Install dependencies:

```bash
make install
```

Run lint, type check, tests, build and dist check:

```bash
make all
```

Install pre-commit hooks:

```bash
make pre-commit-install
```

Run tests with coverage:

```bash
make cov
```

## Publishing

For TestPyPI:

```bash
poetry config repositories.testpypi https://test.pypi.org/legacy/
poetry config pypi-token.testpypi <YOUR_TESTPYPI_TOKEN>
make publish-test
```

For PyPI:

```bash
poetry config pypi-token.pypi <YOUR_PYPI_TOKEN>
make publish
```

## License

MIT
