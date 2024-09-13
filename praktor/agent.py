from LLM.llm_factory import LLMFactory, OllamaLLMFactory
from LLM.llm_interface import LLM

from settings import MODEL

import pika

import time
import random

from unittest import TestCase, TestLoader, TextTestRunner



class Agent:

    def __init__(self) -> None:
        self.llm_factory = OllamaLLMFactory()
    def create_llm(self, llm_type: str) -> LLM:
        return self.llm_factory.create_llm(llm_type)
    
    def process(self):
        ### producer        

        connection_parameters = pika.ConnectionParameters('localhost')

        connection = pika.BlockingConnection(connection_parameters)

        channel = connection.channel()

        channel.queue_declare(queue='agentic')

        messageId = 1

        agents = range(0, 4)

        #while(True):
        for _ in agents:
            message = f"Sending Message Id: {messageId}"

            channel.basic_publish(exchange='', routing_key='agentic', body=message)

            print(f"sent message: {message}")
    
            time.sleep(random.randint(1, 4))

            messageId+=1





class TestAgent(TestCase):
    def setUp(self):
        pass
    
    def tearDown(self):
        pass
           
    def testAAgent(self):

        agent = Agent()
        agent.process()

        #llm = agent.create_llm(MODEL)
        #llm = agent.create_llm('gpt-3.5-turbo-instruct')
        #print(llm.get_model_info())
        #print(llm.generate_text(["Hello, world!"]))
    
    def testBAgent(self):

        pass





if __name__ == '__main__':
    loader = TestLoader()
    suite = loader.loadTestsFromTestCase(TestAgent)
    runner = TextTestRunner().run(suite)