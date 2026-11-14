"""Chat model factory. The model is set with LLM_MODEL in .env."""

from functools import lru_cache

from langchain.chat_models import init_chat_model

from app.config import settings


@lru_cache
def get_llm():
    return init_chat_model(settings.llm_model, temperature=0)


# Usage in a node:
#   llm = get_llm().with_structured_output(RecommendOutput)
#   result = await llm.ainvoke(messages)
