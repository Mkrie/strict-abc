from importlib.metadata import PackageNotFoundError, version

from ._meta import DescriptorKind, StrictABC, StrictABCMeta, StrictOptions

__all__ = [
    "DescriptorKind",
    "StrictABC",
    "StrictABCMeta",
    "StrictOptions",
    "__version__",
]

try:
    __version__ = version("strict-abc-lsp")
except PackageNotFoundError:
    __version__ = "0.0.0"