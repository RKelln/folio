"""LLM provider abstraction.

Pluggable interface for LLM API calls. Default implementation
is OpenAI-compatible (covers DeepSeek, OpenAI, and any
OpenAI-compatible API).
"""

from folio.adapters.llm.base import LLMProvider
from folio.adapters.llm.openai_compatible import OpenAICompatibleProvider


def get_llm_provider(config) -> LLMProvider:
    """Return the configured LLM provider instance."""
    if config is None or not hasattr(config, 'llm'):
        return OpenAICompatibleProvider()
    return OpenAICompatibleProvider(
        base_url=config.llm.base_url,
        api_key_env=config.llm.api_key_env,
    )
