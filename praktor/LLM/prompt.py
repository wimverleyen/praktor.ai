from langchain.prompts import PromptTemplate


def CoverLetter():
    """
        Create a cover letter for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f'''I need a compelling cover letter for the position of {{job_title}} at {{company}}. 
                    The job description emphasizes {{skills}}.
                '''
    #template = f'''Rewrite adjusted for my resume for a {{job_description}}? Here's my current resume: {{resume}}.
    #            ACCURACY MODE: ENABLED and DO NOT HALLUCINATE
    #            '''
    print(f"\n{green}LOGGING: Write cover letter - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def CoverLetterImprove():
    """
        Create a cover letter for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f'''Write a more compelling cover letter for the position of {{job_title}} at {{company}}. 
                    The job description emphasizes {{skills}}. Improve the first draft of the cover letter {{cover_letter}}.
                '''
    #template = f'''Rewrite adjusted for my resume for a {{job_description}}? Here's my current resume: {{resume}}.
    #            ACCURACY MODE: ENABLED and DO NOT HALLUCINATE
    #            '''
    print(f"\n{green}LOGGING: Write improved cover letter - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)