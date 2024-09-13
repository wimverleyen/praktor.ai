from LLM.llm_factory import LLMFactory, OllamaLLMFactory
from LLM.llm_interface import LLM

from settings import MODEL

from unittest import TestCase, TestLoader, TextTestRunner



class Agent:

    def __init__(self) -> None:
        self.llm_factory = OllamaLLMFactory()
    def create_llm(self, llm_type: str) -> LLM:
        return self.llm_factory.create_llm(llm_type)
    
    def process(self):
        ### producer
        pass




class TestAgent(TestCase):
    def setUp(self):
        pass
    
    def tearDown(self):
        pass
           
    def testAAgent(self):

        agent = Agent()

        #llm = agent.create_llm(MODEL)
        llm = agent.create_llm('gpt-3.5-turbo-instruct')
        print(llm.get_model_info())
        #print(llm.generate_text(["Hello, world!"]))
    
    def testBAgent(self):

        pass





if __name__ == '__main__':
    loader = TestLoader()
    suite = loader.loadTestsFromTestCase(TestAgent)
    runner = TextTestRunner().run(suite)