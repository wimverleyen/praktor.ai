from dotenv import load_dotenv

import os
import logging


load_dotenv()

MODEL = 'llama3.1'

MD = os.getenv('MD')
PDF = os.getenv('PDF')

VECTOR_DB = os.getenv('VECTOR_DB')

# Create a logger
def create_log():
    """
    Create a logging object for a logging file.
    """
    log = logging.getLogger(__name__)
    logging.basicConfig(filename = 'praktor.ai.log', \
                    level=logging.DEBUG, \
                    format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
    return log