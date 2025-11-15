"""Utilities for creating instrumented pydantic-ai agents."""

import logging
import os
from typing import Optional, Type, TypeVar, Union

from pydantic import BaseModel
from pydantic_ai import Agent

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T", bound=Union[BaseModel, str])


def _resolve_output_type(output_type: Optional[Type[T]]) -> Type[Union[BaseModel, str]]:
    if output_type is None or output_type is str:
        return str
    if issubclass(output_type, BaseModel):
        return output_type
    raise ValueError(
        f"output_type must be str or a Pydantic BaseModel subclass, got {output_type}"
    )


def _ensure_anthropic_key(model: str) -> None:
    if not model.startswith("anthropic:"):
        return
    if "ANTHROPIC_API_KEY" in os.environ:
        return
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key or ""


def _default_system_prompt(output_type: Type[Union[BaseModel, str]]) -> str:
    if output_type is str:
        return "You are a helpful AI assistant."
    return (
        "You are a helpful AI assistant that extracts and structures data into "
        f"{output_type.__name__} format."
    )


def create_agent(
    model: str,
    output_type: Optional[Type[T]] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    retries: int = 2,
) -> Agent[None, T]:
    """
    Create a flexible pydantic-ai agent for any LLM task.

    This factory function creates agents that work with any model and any output type.
    The agent automatically uses Logfire instrumentation for observability.

    Args:
        model: Model identifier in pydantic-ai format. Examples:
            - "anthropic:claude-sonnet-4-5-20250929"
            - "anthropic:claude-haiku-4-5"
            - "openai:gpt-4"
            - "openai:gpt-3.5-turbo"
        output_type: Output type for the agent. Options:
            - None or str: Returns plain text (default)
            - YourPydanticModel: Returns validated Pydantic model instance
        system_prompt: System prompt to define agent behavior. If not provided,
            uses a default based on result_type
        temperature: Sampling temperature (0.0-1.0)
            - Lower (0.0-0.3): More deterministic, good for structured output
            - Medium (0.4-0.7): Balanced creativity and consistency
            - Higher (0.8-1.0): More creative and varied
        max_tokens: Maximum tokens in the response
        retries: Number of retries on failure (uses exponential backoff)

    Returns:
        Agent configured with automatic Logfire instrumentation

    Examples:
        # Text generation with Sonnet:
        >>> agent = create_agent(
        ...     model="anthropic:claude-sonnet-4-5-20250929",
        ...     system_prompt="You are a professional email writer",
        ...     temperature=0.7,
        ...     max_tokens=2000
        ... )
        >>> result = await agent.run("Write a follow-up email...")
        >>> print(result.output)  # Plain text email

        # Structured output with Haiku (faster, cheaper):
        >>> from pydantic import BaseModel
        >>>
        >>> class TemplateAnalysis(BaseModel):
        ...     template_type: str
        ...     search_terms: list[str]
        >>>
        >>> agent = create_agent(
        ...     model="anthropic:claude-haiku-4-5",
        ...     output_type=TemplateAnalysis,
        ...     system_prompt="Extract search parameters from email templates",
        ...     temperature=0.1,
        ...     max_tokens=1500
        ... )
        >>> result = await agent.run("Template: Research on {topic}...")
        >>> analysis = result.output  # Type: TemplateAnalysis

        # Use any model for any task:
        >>> summarizer = create_agent(
        ...     model="anthropic:claude-haiku-4-5",  # Fast model for summarization
        ...     temperature=0.3,
        ...     max_tokens=3000
        ... )
        >>> composer = create_agent(
        ...     model="anthropic:claude-sonnet-4-5-20250929",  # High-quality model
        ...     temperature=0.7,
        ...     max_tokens=2000
        ... )
    """
    resolved_output_type = _resolve_output_type(output_type)
    _ensure_anthropic_key(model)
    prompt = system_prompt or _default_system_prompt(resolved_output_type)

    agent = Agent(
        model=model,
        output_type=resolved_output_type,
        system_prompt=prompt,
        retries=retries,
        model_settings={
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
    )

    logger.debug(
        "Created agent: model=%s, output_type=%s, temperature=%s, max_tokens=%s, retries=%s",
        model,
        getattr(resolved_output_type, "__name__", str(resolved_output_type)),
        temperature,
        max_tokens,
        retries,
    )

    return agent


async def run_agent(
    prompt: str,
    model: str,
    output_type: Optional[Type[T]] = None,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2000,
    retries: int = 2,
) -> T:
    """
    Convenience helper that creates an agent, runs it, and returns the output.

    Args:
        prompt: The user prompt/question
        model: Model identifier (e.g., "anthropic:claude-sonnet-4-5-20250929")
        output_type: Output type (str or Pydantic model class)
        system_prompt: Optional system prompt
        temperature: Sampling temperature (0.0-1.0)
        max_tokens: Maximum tokens in response
        retries: Number of retries on failure

    Returns:
        - str if output_type is None or str
        - Validated Pydantic model instance if output_type is a BaseModel

    """
    agent = create_agent(
        model=model,
        output_type=output_type,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
    )

    result = await agent.run(prompt)
    return result.output


# Usage examples:
#
# >>> agent = create_agent(
# ...     model="anthropic:claude-sonnet-4-5-20250929",
# ...     system_prompt="You are a professional email writer",
# ...     temperature=0.7,
# ...     max_tokens=2000,
# ... )
# >>> result = await agent.run("Write a follow-up email...")
# >>> print(result.output)  # Plain text email
#
# >>> class TemplateAnalysis(BaseModel):
# ...     template_type: str
# ...     search_terms: list[str]
#
# >>> agent = create_agent(
# ...     model="anthropic:claude-haiku-4-5",
# ...     output_type=TemplateAnalysis,
# ...     system_prompt="Extract search parameters from email templates",
# ...     temperature=0.1,
# ...     max_tokens=1500,
# ... )
# >>> analysis = await agent.run("Template: Research on {topic}...")
# >>> print(analysis.template_type)
#
# >>> text = await run_agent(
# ...     prompt="Summarize this article...",
# ...     model="anthropic:claude-haiku-4-5",
# ...     temperature=0.3,
# ... )
# >>> print(text)
