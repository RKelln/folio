"""Abstract LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface for LLM API calls."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        **extra_params,
    ) -> str:
        """Send a prompt and return the completion text."""
        ...

    @abstractmethod
    def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int | None = None,
        **extra_params,
    ) -> tuple[str, dict]:
        """Send a prompt and return (completion_text, usage_dict).

        usage_dict has keys ``input_tokens`` and ``output_tokens`` (both int).
        """
        ...
