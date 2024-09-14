from LLM.llm_factory import LLMFactory, OllamaLLMFactory
from LLM.llm_interface import LLM

from langchain_community.document_loaders import PyPDFLoader

from settings import MODEL

import pika

import time
import random
from json import dumps

from settings import create_log, MD, PDF

from unittest import TestCase, TestLoader, TextTestRunner

log = create_log()


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
        if connection.is_open and channel.is_open:
            channel.queue_declare(queue='agentic')
        else:
            ValueError('RabbitMQ: Connection/channel not open')

        messageId = 1

        agents = range(0, 1)

        for _ in agents:
            message = f"Sending Message Id: {messageId}"

            data = {}
            data['job_title'] = 'Director of Data Science'
            data['company'] = 'Peloton'

            loader = PyPDFLoader(PDF+'Peloton_job_description.pdf')
            pages = loader.load()
            job_description = ''
            for page in pages:
                job_description += page.page_content
            log.debug(f'DEBUG: urls read_pdf %s', job_description)
            del loader

            #data['skills'] = '- B.S. in Electrical Engineering, Computer Science, or other STEM discipline and 8+ years of relevant work experience. - Analytical, project management, problem-solving, interpersonal, leadership skills. - Self-starter with willingness to take initiative, support strategic priorities, take ownership of delegated projects/initiatives and contribute to results, and ability to work with a minimum supervision - Proﬁcient in a combination of the following areas: AI assurance, automated reasoning, logic, programming languages, assurance cases, hardware-software co-design, optimization, and system dynamics & control. - Familiarity with model-based system engineering and software engineering. - Familiarity with formal analysis, veriﬁcation tools and methodologies for cyber-physical systems including AI-enabled systems.'
            data['job_description'] = job_description

            channel.basic_publish(exchange='', routing_key='agentic', body=dumps(data))
            #channel.basic_publish(exchange='', routing_key='agentic', body=data)

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

        #data = {}
        #data['job_title'] = 'AI Assurance and Co-design Engineer'
        #data['company'] = 'Raytheon Technologies (RTX)'
        #data['skills'] = '- B.S. in Electrical Engineering, Computer Science, or other STEM discipline and 8+ years of relevant work experience. - Analytical, project management, problem-solving, interpersonal, leadership skills. - Self-starter with willingness to take initiative, support strategic priorities, take ownership of delegated projects/initiatives and contribute to results, and ability to work with a minimum supervision - Proﬁcient in a combination of the following areas: AI assurance, automated reasoning, logic, programming languages, assurance cases, hardware-software co-design, optimization, and system dynamics & control. - Familiarity with model-based system engineering and software engineering. - Familiarity with formal analysis, veriﬁcation tools and methodologies for cyber-physical systems including AI-enabled systems.'



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