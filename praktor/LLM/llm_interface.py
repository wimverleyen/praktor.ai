from abc import ABC, abstractmethod
from typing import List, Dict

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