from LLM.prompt import (CoverLetter,
                         CoverLetterImprove, 
                         KeywordsResume, 
                         KeywordsImprove,
                         KeywordsJD,
                         KeywordsCompare, 
                         JobRequirements,
                         Resume,
                         ResumeImprove,
                         ResumeAskImprove, 
                         ResumeCheckup,
                         ResumeCheckin,
                         ResumeJD,
                         ResumeTailor,
                         PromptEmailThankYou,
                         PromptSearch)
from LLM.llm_interface import LLMAdapter
from LLM.llm_factory import LLMFactory

from retrieve_generate import RAGSP, RAGTY

from settings import create_log, MODEL, MD, PDF
from utils import save_markdown, read_markdown

from typing import Dict

log = create_log()


#def WriteCoverLetter(resume_fn: str='', job_description_fn: str='') -> None:

def ThankYouEmail(data: Dict) -> None:

    llm = LLMAdapter(PromptEmailThankYou())
    response = llm.generate(data=data)
    log.debug(f'{response}')
    del llm

    save_markdown(MD+'communication_thank_you.md', response)

    #rag = RAGTY(PromptEmailThankYou())
    #log.debug(f'Start generate - data: {data}')
    #response = rag.generate(adjective=data['adjective'], position=data['position'], content=data['content'])
    #log.debug(f'Response - {response}')
    #del rag
    #save_markdown(MD+'communication_rag_thank_you.md', response)


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

def KeywordsExtraction(data: Dict) -> None:

    resume = read_markdown(MD+'Verleyen_Wim_resume_all.md')
    log.debug('DEBUG: resume: %s', resume)
    data['resume'] = resume

    factory = LLMFactory()
    #llm = factory.create_llm('gpt-3.5-turbo')
    llm = factory.create_llm(MODEL)
    #llm = factory.create_llm('claude-3-opus-20240229')
    
    prompt = KeywordsResume()
    chain = (prompt | llm)
    try:
        log.debug(f'generate: prompt variables: {prompt.input_variables}')
        response = chain.invoke(input=data)
    except Exception as e:
        response = {'error':str(e)}

    log.debug(f'Keywords: {response}')
    save_markdown(MD+'keywords_resume.md', response)
    data['keywords_resume'] = response

    prompt = KeywordsJD()
    chain = (prompt | llm)
    try:
        log.debug(f'generate: prompt variables: {prompt.input_variables}')
        response = chain.invoke(input=data)
    except Exception as e:
        response = {'error':str(e)}

    log.debug(f'Keywords: {response}')
    save_markdown(MD+'keywords_JD.md', response)
    data['keywords_JD'] = response

    prompt = KeywordsCompare()
    chain = (prompt | llm)
    try:
        log.debug(f'generate: prompt variables: {prompt.input_variables}')
        response = chain.invoke(input=data)
    except Exception as e:
        response = {'error':str(e)}

    log.debug(f'Keywords: {response}') 
    save_markdown(MD+'keywords_comparison.md', response)
    data['keywords_compare'] = response


def JobApplication(data: Dict) -> None:
    """
    Extract keywords for a job description
    - get work experience from the resume
    - get job requirements from resume
    """

    # Generate resume for job description
    llm = LLMAdapter(ResumeJD())
    response = llm.generate(data=data)
    log.debug(f'ResumeJD: {response}')
    save_markdown(MD+'resume_jd.md', response)
    data['resume_jd'] = response


    # generic resume
    #resume = read_markdown(MD+'Verleyen_Wim_resume.md')
    #log.debug('DEBUG: resume: %s', resume)
    
    #data['resume'] = resume

    #experience = read_markdown(MD+'work_experience.md')
    #experience = read_markdown('./markdowns/professional_experience.md')
    #log.debug('DEBUG: experience: %s', experience)

    #data['work_experience'] = experience

    #llm = LLMAdapter(JobRequirements())
    #response = llm.generate(data=data)
    #log.debug(f'JobRequirements: {response}')
    #save_markdown(MD+'job_requirements.md', response)

    #data['job_requirements'] = response

    #llm = LLMAdapter(Resume())
    #response = llm.generate(data=data)
    #log.debug(f'Updated resume: {response}')
    #save_markdown(MD+'resume_update.md', response)

    #data['resume_update'] = response

    #llm = LLMAdapter(ResumeImprove())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_2.md', response)

    #data['resume_update_2'] = response

    #llm = LLMAdapter(ResumeAskImprove())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_3.md', response)

    #data['resume_update_3'] = response

    #llm = LLMAdapter(ResumeCheckup())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_4.md', response)

    #data['resume_update_4'] = response

    #llm = LLMAdapter(ResumeCheckin())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_5.md', response)

    #data['resume_update_5'] = response

    #llm = LLMAdapter(ResumeJD())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_6.md', response)

    #data['resume_update_6'] = response

    #llm = LLMAdapter(ResumeTailor())
    #response = llm.generate(data=data)
    #log.debug(f'ResumeImprove: {response}')
    #save_markdown(MD+'resume_update_7.md', response)

    #data['resume_update_7'] = response

def JobInterview(data: Dict) -> None:

    # Haelthcare
    rag = RAGSP()
    log.debug('Question: How to assess data quality for text?')
    #data = {'search':"What are business value creation initiatives", 'content': " building an innovation team in a healthcare company?"}
    data = {'search':"What is the estimate on ROI for different GenAI projects", 'content': " building an innovation team in a healthcare company?"}
    log.debug(f'Question {data}')
    #llm.update(PromptSearch())
    #response = rag.generate(data=data)
    #response = rag.generate(search="How much business value GemAI can create", content=" in the healthcare sector specific?")
    response = rag.generate(search=data['search'], content=data['content'])
    log.debug(f'Question {response}')
    print(f'Question - RAG {response}')

    save_markdown(MD+'SP_RAG_question.md', response)

    rag.references(text=data['search']+data['content'])