from dotenv import load_dotenv

import os
import logging


load_dotenv()

MODEL = 'llama3.1'

VECTOR_DB = os.getenv('VECTOR_DB')

# Create a logger
def create_log():
    log = logging.getLogger(__name__)
    logging.basicConfig(filename = 'praktor.ai.log', \
                    level=logging.DEBUG, \
                    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
    return log