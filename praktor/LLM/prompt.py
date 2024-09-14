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
        Improve a cover letter for a job application. One pass to the LLM.
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


def Keywords():
    """
        Extract keywords from a job description. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Based on this job description for a {{job_title}} role at {{company}}, 
                    extract the most important 75 keywords from the job description. 
                    This is the job description: {{job_description}}.
                '''
    
    print(f"\n{green}LOGGING: Extract keywords - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def KeywordsImprove():
    """
        Extract keywords from . One pass to the LLM.
        It does not really compare the keywords with the resume. It provides a high level overview
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Can your verify if these {{keywords}} are the most important for this job description 
                    for a {{job_title}} role at {{company}}, extract the most important 75 keywords from the job description. 
                    This is the job description: {{job_description}}.

                    Respond with two sections:
                    Section 1: Respond by an adjusted list of 50 keyword and make a summary for each of the keywords.
                    Section 2: Compare keywords between the job description: {{job_description}} and the resume: {{resume}}
                      and define critical differences in keyword usage.
                '''
    
    print(f"\n{green}LOGGING: Improve keywords - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def WorkExperience():
    """
        Extract keywords from resume. One pass to the LLM.
        
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Extract the work experience section from this {{resume}}. Present in an easily to follow format.

                '''
    
    print(f"\n{green}LOGGING: Work experience section from resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)


def Requirements():
    """
        Extract keywords from a job description. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Based on this job description for a {{job_title}} role at {{company}}, 
                    extract the requirements the job description. Generate a table with requirements and
                    how my experience fullfills these requirements.
                    This is the job description: {{job_description}} and my resume {{resume}}.
                '''
    
    print(f"\n{green}LOGGING: Write cover letter - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)


def Resume():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Based on this job description for a {{job_title}} role at {{company}}, 
                    write a resume for my past 10 years of work experience with 3-5 bullet points per role 
                    that include metrics and the most important 25 keywords from the job description. My past titles 
                    and companies were {{previous_job_titles}}. No need to include an objective statement. 
                    This is the job description: {{job_description}}.
                '''
    
    print(f"\n{green}LOGGING: Write cover letter - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)