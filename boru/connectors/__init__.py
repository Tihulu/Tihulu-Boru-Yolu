"""Optional repository connectors (P8 source slice)."""
from .base import (
    OPERATION_CAPABILITIES, WRITE_OPERATIONS, Capability, Grant, RepositoryProvider,
)
from .github import GitHubProvider
from .gitlab import GitLabProvider

__all__ = [
    "OPERATION_CAPABILITIES", "WRITE_OPERATIONS", "Capability", "GitHubProvider", "GitLabProvider",
    "Grant", "RepositoryProvider",
]
