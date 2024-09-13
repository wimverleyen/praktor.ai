from pika import ConnectionParameters, BlockingConnection, BasicProperties

import time
import random
from json import loads

from functools import partial
from typing import Callable, Any

from agent_method import WriteCoverLetter


#from settings import create_log

#log = create_log()

# run one or many consumers

HandleAgentFn = Callable[[Any], None]

def on_message_received(ch, method, properties: BasicProperties, body, args):#, handle_agent = HandleAgentFn):
    processing_time = random.randint(1, 6)
    #log.debug(f'received: "{body}", will take {processing_time} to process')
    #log.debug(f'properties: {properties}')
    #log.debug(f'method: {method}')
    #log.debug(f'channel: {channel}')
    #print(f'received: "{body}", will take {processing_time} to process')
    #print(f'properties: {properties}')
    #print(f'method: {method}')
    #print(f'channel: {channel}')

    data = loads(body)
    print('data keys: ', data.keys())

    time.sleep(processing_time)
    print('____ARGUMENTS')
    #print(args)
    print(type(args))
    #for arg in args:
    #    print(arg)
    
    args(data)

    #WriteCoverLetter(body)
    # chain, prompt, LLM
    #handle_agent()


    ch.basic_ack(delivery_tag=method.delivery_tag)
    print(f'finished processing and acknowledged message')


connection_parameters = ConnectionParameters('localhost')
connection = BlockingConnection(connection_parameters)
channel = connection.channel()
channel.queue_declare(queue='agentic')
channel.basic_qos(prefetch_count=1)




#on_message_callback = functools.partial(on_message, args=(connection, threads))
#on_message_callback = partial(on_message_received, args=(connection, WriteCoverLetter))
on_message_callback = partial(on_message_received, args=(WriteCoverLetter))
#trigger_agent = partial(on_message_received, agent_handler=WriteCoverLetter
#channel.basic_consume(on_message_callback=on_message_callback, queue='standard')

#channel.basic_consume(queue='agentic', on_message_callback=on_message_received)
channel.basic_consume(queue='agentic', on_message_callback=on_message_callback)
#channel.basic_consume(queue='agentic', on_message_callback=trigger_agent)
print('Starting Consuming')
channel.start_consuming()