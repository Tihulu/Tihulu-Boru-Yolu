"""TIHULU Boru Yolu — native, independent Boru Core (P1 offline slice).

This package has **no dependency** on TIHULU-AUTO, OpenCode, Kandev or
Langflow.  Jan is an optional, explicitly configured local provider.
"""
from .config import CoreConfig, ProviderConfig, default_config
from .core import BoruCore
from .errors import (
    BoruError, ContractError, ConfigurationError, DuplicateTask, InvalidTransition,
    PolicyViolation, ProviderUnavailable, QueueFull, StoreError, VerificationError,
)
from .policy import Policy
from .state import TaskState, TaskRecord, can_transition
from .store import TaskStore
from .types import AgentResult, TaskEnvelope

__all__ = [
    "AgentResult", "BoruCore", "BoruError", "ContractError", "ConfigurationError",
    "CoreConfig", "DuplicateTask", "InvalidTransition", "Policy", "PolicyViolation",
    "ProviderConfig", "ProviderUnavailable", "QueueFull", "StoreError", "TaskEnvelope",
    "TaskRecord", "TaskState", "TaskStore", "VerificationError", "can_transition",
    "default_config",
]
__version__ = "0.1.0"
