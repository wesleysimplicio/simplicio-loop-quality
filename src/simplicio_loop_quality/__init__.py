"""Testing and quality extension for :mod:`simplicio_loop`.

The package deliberately contains no scheduler or worker runtime.  It contributes
quality policy, agent profiles, evidence validation and a thin invocation boundary
to the authoritative Loop process.
"""

from .agents import AGENTS, AgentSpec
from .gate import GateVerdict, evaluate_receipt
from .policy import QualityPolicy, load_strict_policy

__all__ = [
    "AGENTS",
    "AgentSpec",
    "GateVerdict",
    "QualityPolicy",
    "evaluate_receipt",
    "load_strict_policy",
]

__version__ = "0.1.0"
