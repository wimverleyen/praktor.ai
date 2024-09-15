from LLM.prompt import (CoverLetter,
                         CoverLetterImprove, 
                         Keywords, 
                         KeywordsImprove, 
                         WorkExperience,
                         JobRequirements,
                         Resume,
                         ResumeImprove)
from LLM.llm_interface import LLMAdapter

from settings import create_log, MD, PDF
from utils import save_markdown, read_markdown

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


def JobApplication(data: Dict) -> None:
    """
    Extract keywords for a job description
    - get work experience from the resume
    - get job requirements from resume
    """

    resume = read_markdown(MD+'Verleyen_Wim_resume.md')
    log.debug('DEBUG: resume: %s', resume)

    llm = LLMAdapter(Keywords())

    response = llm.generate(data=data)
    log.debug(f'Keywords: {response}')
    save_markdown(MD+'keywords.md', response)

    llm = LLMAdapter(KeywordsImprove())

    data['keywords'] = response
    data['resume'] = resume

    response = llm.generate(data=data)
    log.debug(f'KeywordsImprove: {response}')
    save_markdown(MD+'keywords_improved.md', response)

    data['keywords_improved'] = response

    #llm = LLMAdapter(WorkExperience())
    #response = llm.generate(data=data)
    #log.debug(f'WorkExperience: {response}')
    #save_markdown(MD+'work_experience.md', response)

    experience = read_markdown(MD+'work_experience.md')
    log.debug('DEBUG: resume: %s', experience)

    data['work_experience'] = experience

    llm = LLMAdapter(JobRequirements())
    response = llm.generate(data=data)
    log.debug(f'JobRequirements: {response}')
    save_markdown(MD+'job_requirements.md', response)

    data['job_requirments'] = response

    llm = LLMAdapter(Resume())
    response = llm.generate(data=data)
    log.debug(f'Resume: {response}')
    save_markdown(MD+'resume_update.md', response)

    data['resume_update'] = response

    llm = LLMAdapter(ResumeImprove())
    response = llm.generate(data=data)
    log.debug(f'ResumeImprove: {response}')
    save_markdown(MD+'resume_update_2.md', response)

    data['resume_update_2'] = response
