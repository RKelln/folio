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
