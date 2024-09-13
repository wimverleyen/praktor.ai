import os

from langchain_ollama.llms import OllamaLLM
from langchain_openai.llms import OpenAI
from dotenv import load_dotenv

from LLM.llm_interface import LLM
from settings import create_log

from typing import List


log = create_log()



# Load the .env file
load_dotenv()
api_key = os.environ.get('OPENAI_API_KEY')
log.debug('OPENAI_API_KEY- %s'%api_key)




class OllamaLlama31(LLM):
    """
    Implementation for Llama 3.1 LLM with Ollama
    """
    def __init__(self, model: str='', temperature=0.0):
        super().__init__()
        self.__llm = OllamaLLM(model=model, temperature=temperature)

    def generate_text(self, prompt: List[str]):
        # implementation details omitted
        response = self.__llm.generate(prompt)
        return response

    def generate_text_data(self, data):
        # implementation details omitted
        response = self.__llm.generate(data)
        return response

    def get_model_info(self):
        return {"model_name": "Ollama - Llama3.1", "version": "1.0"}
    

class GPT35Turbo(LLM):
    """
    Implementation for ChatGPT 3.5
    """
    def __init__(self, model: str='', temperature=0.0):
        super().__init__()
            
        self.__llm = OpenAI(model=model, temperature=temperature)

    def generate_text(self, prompt: List[str]):
        # implementation details omitted
        response = self.__llm.generate(prompt)
        return response

    def generate_text_data(self, data):
        # implementation details omitted
        response = self.__llm.generate(data)
        return response

    def get_model_info(self):
        return {"model_name": "gpt-3.5-turbo-instruct", "version": "1.0"}