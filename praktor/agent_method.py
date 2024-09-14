from LLM.prompt import CoverLetter, CoverLetterImprove
from LLM.llm_interface import LLMAdapter

from settings import create_log, MD, PDF
from utils import save_markdown

from typing import Dict

log = create_log()


#def WriteCoverLetter(resume_fn: str='', job_description_fn: str='') -> None:

def WriteCoverLetter(data: Dict) -> None:
    """
    Write cover letter agent method
    @data: dictionary argument
    """

    llm = LLMAdapter(CoverLetter())

    #llm.update(CoverLetter())

    response = llm.generate(data=data)
    log.debug(f'Cover letter: {response}')

    print(MD+'cover_letter.md')

    save_markdown(MD+'cover_letter.md', response)

    data['cover_letter'] = response
    llm = LLMAdapter(CoverLetterImprove())

    response = llm.generate(data=data)
    log.debug(f'Cover letter: {response}')

    save_markdown(MD+'cover_letter_improved.md', response)

    data['cover_letter'] = response

    response = llm.generate(data=data)
    log.debug(f'Cover letter: {response}')

    save_markdown(MD+'cover_letter_improved_2.md', response)
