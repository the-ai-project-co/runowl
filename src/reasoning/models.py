"""Data models for the Recursive Reasoning Engine."""

from dataclasses import dataclass, field
from enum import StrEnum


class StepType(StrEnum):
    REASONING = "reasoning"
    CODE_EXECUTION = "code_execution"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    OUTPUT = "output"
    ERROR = "error"


@dataclass
class ReasoningStep:
    type: StepType
    content: str
    iteration: int
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ConversationMessage:
    role: str  # "user" | "model"
    content: str


@dataclass
class ReasoningTrace:
    steps: list[ReasoningStep] = field(default_factory=list)
    iterations: int = 0
    llm_calls: int = 0
    tool_calls: int = 0

    def add_step(self, step: ReasoningStep) -> None:
        self.steps.append(step)
        if step.type == StepType.LLM_CALL:
            self.llm_calls += 1
        elif step.type == StepType.TOOL_CALL:
            self.tool_calls += 1


@dataclass
class RLMResult:
    output: str
    trace: ReasoningTrace
    conversation: list[ConversationMessage]
    success: bool
    error: str | None = None
