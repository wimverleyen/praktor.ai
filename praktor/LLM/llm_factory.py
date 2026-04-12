from abc import ABC

from settings import MODEL


class LLMFactory(ABC):
    """
    Factory for creating LangChain-compatible LLM instances by model string.

    Supported model strings:
      Ollama local:  any string that matches the configured MODEL env var,
                     or any other Ollama model name (e.g. "llama3.1", "qwen2.5")
      OpenAI:        "gpt-3.5-turbo-instruct", "gpt-3.5-turbo"
      Anthropic:     any string starting with "claude-" (e.g. "claude-sonnet-4-6")

    Usage:
        factory = LLMFactory()
        llm = factory.create_llm("claude-sonnet-4-6")
    """

    def __init__(self):
        pass

    def create_llm(self, llm_type: str):
        if llm_type.startswith("claude-"):
            return self._create_anthropic(llm_type)
        elif llm_type.startswith("gpt-"):
            return self._create_openai(llm_type)
        else:
            # Default: treat as an Ollama model name
            return self._create_ollama(llm_type)

    def _create_ollama(self, model: str):
        from langchain_ollama.llms import OllamaLLM
        return OllamaLLM(model=model, temperature=0.0)

    def _create_openai(self, model: str):
        from langchain_openai.llms import OpenAI
        return OpenAI(model=model, temperature=0.0)

    def _create_anthropic(self, model: str):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=0.0)
