from pika import ConnectionParameters, BlockingConnection, BasicProperties

from json import loads

from praktor.agent_method import WriteCoverLetter, JobApplication, KeywordsExtraction, JobInterview, ThankYouEmail, Search, Message
from praktor.schemas import parse_message

from praktor.settings import create_log

log = create_log()

_DISPATCH = {
    "job_application": JobApplication,
    "cover_letter": WriteCoverLetter,
    "keywords_extraction": KeywordsExtraction,
    "job_interview": JobInterview,
    "thank_you": ThankYouEmail,
    "search": Search,
    "message": Message,
}


def on_message_received(ch, method, properties: BasicProperties, body):
    """Route an incoming queue message to the appropriate agent method."""
    try:
        raw = loads(body)
        log.debug(f'received message with keys: {list(raw.keys())}')

        msg = parse_message(raw)
        handler = _DISPATCH[msg.agent_type]
        log.debug(f'dispatching to handler: {handler.__name__}')

        handler(msg.model_dump())

        ch.basic_ack(delivery_tag=method.delivery_tag)
        log.debug(f'acknowledged message agent_type={msg.agent_type}')
        print(f'finished processing [{msg.agent_type}]')

    except Exception as e:
        log.error(f'error processing message: {e}', exc_info=True)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        print(f'failed to process message: {e}')


connection_parameters = ConnectionParameters('localhost')
connection = BlockingConnection(connection_parameters)
channel = connection.channel()
channel.queue_declare(queue='agentic')
channel.basic_qos(prefetch_count=1)

channel.basic_consume(queue='agentic', on_message_callback=on_message_received)

print('Ready to receive [agentic]')
channel.start_consuming()
