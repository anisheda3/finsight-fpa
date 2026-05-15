"""
Compatibility shim — produces real Agno Agent/Team objects when agno is
installed, otherwise lightweight stand-ins so the system is import-safe and
unit-testable in CI.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

try:
    from agno.agent import Agent as _AgnoAgent
    from agno.team import Team as _AgnoTeam
    from agno.tools import tool as _agno_tool
    HAS_AGNO = True
except Exception:
    HAS_AGNO = False
    _AgnoAgent = None
    _AgnoTeam = None

def _agno_tool(fn: Callable | None = None, **_: Any):
    if fn is None:
        return lambda f: f
    return fn

tool = _agno_tool

@dataclass
class StubAgent:
    name: str
    instructions: str
    model: Any | None = None
    tools: list[Any] = field(default_factory=list)
    output_schema: Any | None = None
    memory: Any | None = None
    guardrails: list[Any] = field(default_factory=list)
    evals: list[Any] = field(default_factory=list)
    hooks: dict[str, Any] = field(default_factory=dict)

    async def arun(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("StubAgent.arun name=%s keys=%s", self.name, list(payload.keys()))
        return payload

@dataclass
class StubTeam:
    name: str
    members: list[Any]
    instructions: str = ""
    output_schema: Any | None = None
    memory: Any | None = None
    guardrails: list[Any] = field(default_factory=list)

    async def arun(self, payload: dict[str, Any]) -> dict[str, Any]:
        logger.info("StubTeam.arun name=%s members=%s", self.name, [m.name for m in self.members])
        return payload

def make_agent(**kwargs: Any) -> Any:
    """Return a real Agno Agent if available, else a Stub."""
    if HAS_AGNO and _AgnoAgent is not None:
        # Agno's Agent does NOT accept: output_schema, guardrails, evals, hooks
        allowed = {"name", "instructions", "model", "tools", "memory"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        return _AgnoAgent(**filtered)
    # For Stub, we keep all args (so tests can still use output_schema, etc.)
    return StubAgent(**{k: v for k, v in kwargs.items()
                        if k in {"name", "instructions", "model", "tools",
                                 "output_schema", "memory", "guardrails",
                                 "evals", "hooks"}})

def make_team(**kwargs: Any) -> Any:
    if HAS_AGNO and _AgnoTeam is not None:
        allowed = {"name", "members", "instructions", "memory"}
        filtered = {k: v for k, v in kwargs.items() if k in allowed}
        return _AgnoTeam(**filtered)
    return StubTeam(**{k: v for k, v in kwargs.items()
                       if k in {"name", "members", "instructions",
                                "output_schema", "memory", "guardrails"}})