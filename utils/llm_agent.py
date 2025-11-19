"""Utilities for creating instrumented pydantic-ai agents."""

import logging
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
    timeout: Optional[float] = None,
) -> Agent[None, T]:
    """Create a pydantic-ai Agent with optional output validation."""
    resolved_output_type = _resolve_output_type(output_type)
    prompt = system_prompt or _default_system_prompt(resolved_output_type)

    model_settings = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if timeout is not None:
        model_settings["timeout"] = timeout

    agent = Agent(
        model=model,
        output_type=resolved_output_type,
        system_prompt=prompt,
        retries=retries,
        model_settings=model_settings,
    )

    logger.debug(
        "Created agent: model=%s, output_type=%s, temperature=%s, max_tokens=%s, retries=%s, timeout=%s",
        model,
        getattr(resolved_output_type, "__name__", str(resolved_output_type)),
        temperature,
        max_tokens,
        retries,
        timeout,
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
    timeout: Optional[float] = None,
) -> T:
    """Create an agent, invoke it with prompt, and return the result."""
    agent = create_agent(
        model=model,
        output_type=output_type,
        system_prompt=system_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        timeout=timeout,
    )

    result = await agent.run(prompt)
    return result.output
