from abc import ABC, abstractmethod
from typing import List, Dict

from settings import MODEL, create_log

from langchain_ollama.llms import OllamaLLM

log = create_log()

class LLM(ABC):
    """
    Abstract class with interface for LLMs
    """
    @abstractmethod
    def generate_text(self, prompt: List[str]) -> Dict:
        pass

    @abstractmethod
    def generate_text_data(self, data):
        pass

    @abstractmethod
    def get_model_info(self) -> Dict:
        pass

    #@abstractmethod
    #def update(self) -> Dict:
    #    pass

    #def update(self, prompt_method):

    #    self.__prompt = prompt_method
    #    self.__chain = (
    #        self.__prompt
    #        | self.__llm)



class LLMAdapter:
    """
    Adapter design pattern for Ollama Llama3.1 model
    Not sure if adapter should be replaced with Factory
    """

    def __init__(self, prompt_method, temperature=0.0):

        self.__prompt = prompt_method
        self.__llm = OllamaLLM(model=MODEL, temperature=temperature)

        self.__chain = (
            self.__prompt
            | self.__llm)
        
    def update(self, prompt_method):
        """
        Update prompt method in the one-shot LLM
        Initialization of chain before inference
        """

        self.__prompt = prompt_method
        self.__chain = (
            self.__prompt
            | self.__llm)
        
    def generate(self, data={}):
        """
        we need a prompt related 
        """
        try:
            log.debug(f'generate: prompt variables: {self.__prompt.input_variables}')
            response = self.__chain.invoke(input=data)
        except Exception as e:
           response = {'error':str(e)}
        return response