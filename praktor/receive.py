from pika import ConnectionParameters, BlockingConnection, BasicProperties

import time
import random
from json import loads

from functools import partial
from typing import Callable, Any

from agent_method import WriteCoverLetter, JobApplication, KeywordsExtraction, JobInterview, ThankYouEmail

from settings import create_log

log = create_log()

def on_message_received(ch, method, properties: BasicProperties, body, args):
    """
    Execute agent method with the body as json structure.

    """
    
    data = loads(body)
    log.debug(f'callback function - data keys: {data.keys()}')

    args(data)

    ch.basic_ack(delivery_tag=method.delivery_tag)
    print(f'finished processing and acknowledged message')

connection_parameters = ConnectionParameters('localhost')
connection = BlockingConnection(connection_parameters)
channel = connection.channel()
channel.queue_declare(queue='agentic')
channel.basic_qos(prefetch_count=1)

## JobApplication - agent_method


#on_message_callback = partial(on_message_received, args=(JobApplication))
#on_message_callback = partial(on_message_received, args=(JobInterview))
on_message_callback = partial(on_message_received, args=(ThankYouEmail))
#on_message_callback = partial(on_message_received, args=(KeywordsExtraction))
channel.basic_consume(queue='agentic', on_message_callback=on_message_callback)

print('Ready to receive[agentic]')
channel.start_consuming()