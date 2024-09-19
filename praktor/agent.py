from langchain_community.document_loaders import PyPDFLoader

from settings import MODEL

import pika

import time
import random
from json import dumps

from settings import create_log, MD, PDF
from utils import save_markdown

from unittest import TestCase, TestLoader, TextTestRunner

log = create_log()



class Agent:

    def __init__(self) -> None:
        #self.llm_factory = LLMFactory()
        pass

    #def create_llm(self, llm_type: str) -> LLM:
    #    return self.llm_factory.create_llm(llm_type)
    
    def process(self):
        ### producer        

        connection_parameters = pika.ConnectionParameters('localhost')
        connection = pika.BlockingConnection(connection_parameters)
        channel = connection.channel()
        if connection.is_open and channel.is_open:
            channel.queue_declare(queue='agentic')
        else:
            ValueError('RabbitMQ: Connection/channel not open')

        agents = range(0, 1)

        for _ in agents:

            # Abstract away the data class for an agent - different agents; not sure many to many (1-1)?
            data = {}


            data['job_title'] = 'Director of Data Science'
            data['company'] = 'Peloton'
            # for the coverletter agent!
            #data['skills']
            ##data['skills'] = '- B.S. in Electrical Engineering, Computer Science, or other STEM discipline and 8+ years of relevant work experience. - Analytical, project management, problem-solving, interpersonal, leadership skills. - Self-starter with willingness to take initiative, support strategic priorities, take ownership of delegated projects/initiatives and contribute to results, and ability to work with a minimum supervision - Proﬁcient in a combination of the following areas: AI assurance, automated reasoning, logic, programming languages, assurance cases, hardware-software co-design, optimization, and system dynamics & control. - Familiarity with model-based system engineering and software engineering. - Familiarity with formal analysis, veriﬁcation tools and methodologies for cyber-physical systems including AI-enabled systems.'

            # Read job description
            loader = PyPDFLoader(PDF+'Peloton_job_description.pdf')
            pages = loader.load()
            job_description = ''
            for page in pages:
                job_description += page.page_content
            log.debug(f'DEBUG: urls read_pdf %s', job_description)
            del loader
            
            data['job_description'] = job_description
            save_markdown(MD+'job_description.md', job_description)

            channel.basic_publish(exchange='', routing_key='agentic', body=dumps(data))
                        
    
            #time.sleep(random.randint(1, 4))
    #def parallel_clone(self): clone agent across similar tasks, e.g., apply for 10 jobs
    def thankyou(self):
        ### Producer: sent agent request

        connection_parameters = pika.ConnectionParameters('localhost')
        connection = pika.BlockingConnection(connection_parameters)
        channel = connection.channel()
        if connection.is_open and channel.is_open:
            channel.queue_declare(queue='agentic')
        else:
            ValueError('RabbitMQ: Connection/channel not open')

        #data = {'adjective':'professional', 'position': 'AVP Data Science', 'content':'Write a thank you email after an interview. Her expertise in IT Strategy, digital transformation, very thoughtful questions around value proposition were outstanding and great example for the organization.'}
        data = {'adjective':'professional', 'position': 'AVP Data Science', 'content':'Write a thank you email after an interview. Her expertise in IT Strategy, digital transformation, very thoughtful questions around value proposition were outstanding and great example for the organization.'}
        channel.basic_publish(exchange='', routing_key='agentic', body=dumps(data))



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



        #agent.process()

        #llm = agent.create_llm(MODEL)
        #llm = agent.create_llm('gpt-3.5-turbo-instruct')
        #print(llm.get_model_info())
        #print(llm.generate_text(["Hello, world!"]))
    
    def testBAgent(self):

        agent = Agent()
        agent.thankyou()





if __name__ == '__main__':
    loader = TestLoader()
    suite = loader.loadTestsFromTestCase(TestAgent)
    runner = TextTestRunner().run(suite)