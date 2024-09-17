from settings import MODEL

from abc import ABC#, abstractmethod
#from typing import 

from langchain_openai.llms import OpenAI
from langchain_ollama.llms import OllamaLLM
#from langchain_anthropic import ChatAnthropic

from settings import MODEL

class LLMFactory(ABC):
    """
    Abstract class as interface for LLM factory
    """
    def __init__(self):
        #self._llms = {}
        pass
    
    #@abstractmethod
    def create_llm(self, llm_type: str):
        if llm_type == MODEL:
            return OllamaLLM(model=MODEL, temperature=0.0)
            #return OllamaLLM(model='llama3.1', temperature=0.0)
        elif llm_type == 'gpt-3.5-turbo-instruct':
            return OpenAI(model='gpt-3.5-turbo-instruct', temperature=0.0)
        elif llm_type == 'gpt-3.5-turbo':
            return OpenAI(model='gpt-3.5-turbo', temperature=0.0)
        #elif llm_type == 'claude-3-opus-20240229':
        #    return ChatAnthropic(model='claude-3-opus-20240229', temperature=0.0)
        else:
            raise ValueError(f"Unsupported LLM type: {llm_type}")

    #def register_llm(self, name: str, llm_class: type) -> None:
    #    """Register an LLM class with a unique name"""
    #    if name in self._llms:
    #        raise ValueError(f"LLM '{name}' already registered")
    #    self._llms[name] = llm_class

    #def get_llm(self, name: str) -> type:
    #    """Get an LLM instance by its registered name"""
    #    return self._llms.get(name)
