from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from settings import Settings


def get_provider(settings: Settings) -> dict[str, OpenAIProvider]:
    """Get and LLM call provider openai compatible"""
    dict_providers: dict[str, OpenAIProvider] = {}

    for key in settings.openai:
        provider = settings.openai[key]
        dict_providers[key] = OpenAIProvider(
            base_url=provider.base_url, api_key=provider.secret_key.get_secret_value()
        )
    return dict_providers


def get_model(model_name: str, provider: OpenAIProvider, **kwargs) -> OpenAIChatModel:
    """Return a generic LLM model"""
    model: OpenAIChatModel = OpenAIChatModel(model_name, provider=provider, **kwargs)
    return model


def get_agent(model: Model, **kwargs) -> Agent:
    """Return a generic Agent from a defined model"""
    return Agent(model, **kwargs)
