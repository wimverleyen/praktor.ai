from settings import MODEL

from abc import ABC

from langchain_openai.llms import OpenAI
from langchain_ollama.llms import OllamaLLM
from langchain_anthropic import ChatAnthropic


class LLMFactory(ABC):
    """
    Abstract class as interface for LLM factory
    """
    def __init__(self):
        pass

    def create_llm(self, llm_type: str):
        if llm_type == MODEL:
            return OllamaLLM(model=MODEL, temperature=0.0)
        elif llm_type == 'gpt-3.5-turbo-instruct':
            return OpenAI(model='gpt-3.5-turbo-instruct', temperature=0.0)
        elif llm_type == 'gpt-3.5-turbo':
            return OpenAI(model='gpt-3.5-turbo', temperature=0.0)
        elif llm_type.startswith('claude-'):
            return ChatAnthropic(model=llm_type, temperature=0.0)
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")
