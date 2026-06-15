"""OpenAI-compatible LLM provider.

Covers DeepSeek, OpenAI, and any API implementing the
OpenAI chat completions interface.
"""

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

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        **extra_params,
    ) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
        )
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        kwargs = {}
        if model:
            kwargs['model'] = model
        if max_tokens:
            kwargs['max_tokens'] = max_tokens
        kwargs.update(extra_params)

        response = client.chat.completions.create(messages=messages, **kwargs)
        return response.choices[0].message.content or ''
