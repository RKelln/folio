"""OpenAI-compatible LLM provider.

Covers DeepSeek, OpenAI, and any API implementing the
OpenAI chat completions interface.
"""

from __future__ import annotations

import os

from folio.adapters.llm.base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider for OpenAI-compatible APIs."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        api_key_env: str | None = None,
    ):
        self._base_url = base_url
        self._api_key = api_key or (
            os.environ.get(api_key_env, '') if api_key_env else ''
        )
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                base_url=self._base_url,
                api_key=self._api_key,
            )
        return self._client

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        **extra_params,
    ) -> str:
        text, _ = self.complete_with_usage(
            system_prompt, user_prompt, model=model,
            max_tokens=max_tokens, **extra_params,
        )
        return text

    def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int | None = None,
        **extra_params,
    ) -> tuple[str, dict]:
        client = self._get_client()
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        kwargs: dict[str, Any] = {}
        if model:
            kwargs['model'] = model
        if max_tokens:
            kwargs['max_tokens'] = max_tokens
        kwargs['temperature'] = temperature

        reasoning_effort = extra_params.pop('reasoning_effort', None)
        thinking_enabled = extra_params.pop('thinking_enabled', None)

        model_lower = (model or '').lower()
        if reasoning_effort and model_lower.startswith("deepseek"):
            kwargs['reasoning_effort'] = reasoning_effort
        if thinking_enabled is not None and model_lower.startswith("deepseek"):
            kwargs['extra_body'] = {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}}

        kwargs.update(extra_params)

        response = client.chat.completions.create(messages=messages, **kwargs)
        text = response.choices[0].message.content or ''

        if response.usage is not None:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        else:
            usage = {"input_tokens": 0, "output_tokens": 0}

        return text, usage
