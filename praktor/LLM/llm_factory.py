from praktor.settings import MODEL

# OpenAI models that use the Completion API (instruct/legacy).
# Everything else under "gpt-" uses the Chat Completions API.
_OPENAI_COMPLETION_MODELS = {
    "gpt-3.5-turbo-instruct",
    "text-davinci-003",
    "text-davinci-002",
    "text-curie-001",
    "text-babbage-001",
    "text-ada-001",
}


class LLMFactory:
    """
    Factory for creating LangChain-compatible LLM instances by model string.

    Supported model strings:
      Ollama local:  any other string (e.g. "llama3.1", "qwen2.5", "mistral")
      OpenAI chat:   "gpt-4", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", ...
      OpenAI legacy: "gpt-3.5-turbo-instruct", "text-davinci-003", ...
      Anthropic:     any string starting with "claude-" (e.g. "claude-sonnet-4-6")

    Usage:
        factory = LLMFactory()
        llm = factory.create_llm("claude-sonnet-4-6", temperature=0.4)
    """

    _CLAUDE_SHORTHANDS = {"opus", "sonnet", "haiku"}

    def create_llm(self, llm_type: str, temperature: float = 0.0):
        # Normalize shorthands like "sonnet-4.6" → "claude-sonnet-4-6"
        if not llm_type.startswith("claude-"):
            prefix = llm_type.split("-")[0]
            if prefix in self._CLAUDE_SHORTHANDS:
                llm_type = "claude-" + llm_type.replace(".", "-")

        if llm_type.startswith("claude-"):
            return self._create_anthropic(llm_type, temperature)
        elif llm_type.startswith("gpt-") or llm_type.startswith("o1") or llm_type.startswith("o3"):
            return self._create_openai(llm_type, temperature)
        else:
            return self._create_ollama(llm_type, temperature)

    def _create_ollama(self, model: str, temperature: float):
        from langchain_ollama.llms import OllamaLLM
        return OllamaLLM(model=model, temperature=temperature)

    def _create_openai(self, model: str, temperature: float):
        if model in _OPENAI_COMPLETION_MODELS:
            from langchain_openai.llms import OpenAI
            return OpenAI(model=model, temperature=temperature)
        # All modern GPT-4/o-series models use the Chat Completions API.
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature)

    def _create_anthropic(self, model: str, temperature: float):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature)
