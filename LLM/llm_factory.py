from settings import MODEL

from abc import ABC, abstractmethod
from LLM.llm_interface import LLM
from LLM.llm_implementations import OllamaLlama31, GPT35Turbo


class LLMFactory(ABC):
    def __init__(self):
        self._llms = {}
    
    @abstractmethod
    def create_llm(llm_type: str) -> LLM:
        if llm_type == 'llama3.1':
            return OllamaLlama31(model='llama31', temperature=0.0)
        elif llm_type == 'gpt-3.5-turbo-instruct':
            return GPT35Turbo(model='gpt-3.5-turbo-instruct', temperature=0.0)
        #elif llm_type == "claude":
        #    return Claude()
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")

    def register_llm(self, name: str, llm_class: type):
        """Register an LLM class with a unique name"""
        if name in self._llms:
            raise ValueError(f"LLM '{name}' already registered")
        self._llms[name] = llm_class

    def get_llm(self, name: str) -> type:
        """Get an LLM instance by its registered name"""
        return self._llms.get(name)


class OllamaLLMFactory(LLMFactory):
    def create_llm(self, llm_type: str) -> LLM:
        return OllamaLlama31(model=MODEL, temperature=0.0)
        #return OllamaLLM(model=MODEL, temperature=0.0)


class GPT35TurboLLMFactory(LLMFactory):
    def create_llm(self, llm_type: str) -> LLM:
        return GPT35Turbo(model='gpt-3.5-turbo-instruct', temperature=0.0)
        #return GPT35Turbo(model=MODEL, temperature=0.0)


"""
#class LLMFactory(ABC):
#    @abstractmethod
#    def create_llm(self) -> LLM:
#        pass


class LLMFactory:
    @staticmethod
    def create_llm(llm_type: str) -> LLMInterface:
        if llm_type == "llama3.1":
            return OllamaLLM()
        elif llm_type == "openai":
            return OpenAI()
        elif llm_type == "claude":
            return Claude()
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")
"""