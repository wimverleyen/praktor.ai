from abc import ABC, abstractmethod

class LLM(ABC):
    """
    Abstract class with interface for LLMs
    """
    @abstractmethod
    def generate_text(self, prompt):
        pass

    @abstractmethod
    def generate_text_data(self, data):
        pass

    @abstractmethod
    def get_model_info(self):
        pass