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


def KeywordsResume():
    """
        Extract keywords from a resume. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Based on this resume, extract the most important 75 keywords. 
                    This is the resume: {{resume}}.
                '''
    
    print(f"\n{green}LOGGING: Extract keywords resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def KeywordsJD():
    """
        Extract keywords from a job description. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Based on this job description for a {{job_title}} role at {{company}}, 
                    extract the most important 75 keywords from the job description. 
                    This is the job description: {{job_description}}.
                '''
    
    print(f"\n{green}LOGGING: Extract keywords job description- formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def KeywordsCompare():
    """
        Compare resume and job description keywords from a job description. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Compare the keywords for the resume:{{keywords_resume}}\n
                And the keywords for the job description {{keywords_JD}}. Specify the most important differences between these 2 lists
                of keywords.
                '''
    
    print(f"\n{green}LOGGING: Extract keywords job description- formatted prompt template string to an LLM model --------{white}")
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

def JobRequirements():
    """
        Extract job requirements from job description. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Extract the job requirements from this {{job_description}}. Present in an easily to follow format.
                '''
    
    print(f"\n{green}LOGGING: Job requirements from job description - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def WorkExperience():
    """
        Extract keywords from resume. One pass to the LLM. This prompt is not working well.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Extract the complete professional experience section from this resume: {{resume}}.
                    Do not incorporate any technical skills section.
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
    
    print(f"\n{green}LOGGING: Job requirements - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def Resume():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' You are an experienced resume writer who specializes in making resumes for leadership roles in Data Science, Artificial intelligence
                and Machine Learing, and Engineering. Help me to write a resume for the {{job_title}} role at {{company}}. Ask me questions if you need 
                to know anything else to write a professional resume.

                Write a resume for this job description:\n {{job_description}} \n and my work experience:\n {{work_experience}}

                Here is an example resume you can use as a template:\n
                {{resume}}
                '''
                    #including these keywords: 
                    #{{keywords}}. Write a resume as a top business executive, that include metrics and the most 
                    #important keywords: {{keywords_improved}}. Keep my past titles and companies from my work experience:
                    #  {{work_experience}}.
    
    print(f"\n{green}LOGGING: Rewrite resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeTailor():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Here is my current resume. How would you rewrite it as an expoeruenced resume writer for applying for a {{job_title}} role  at {{company}}.
                Include metrics in the achievements.
                Resume:
                {{resume}}

                Job Description:
                {{job_description}}


                '''
                    #including these keywords: 
                    #{{keywords}}. Write a resume as a top business executive, that include metrics and the most 
                    #important keywords: {{keywords_improved}}. Keep my past titles and companies from my work experience:
                    #  {{work_experience}}.
    
    print(f"\n{green}LOGGING: Rewrite resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeOptimize():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f'''Can you help to optimize my resume for a {{job_title}} role at {{company}}?  Highlight my relevant skills, experience, 
                and achievements to make my application stand out. Include metrics in the achievements.
                Resume: \n
                {{resume}}
                \n
                Job Description: \n
                {{job_description}}

                '''
                    #including these keywords: 
                    #{{keywords}}. Write a resume as a top business executive, that include metrics and the most 
                    #important keywords: {{keywords_improved}}. Keep my past titles and companies from my work experience:
                    #  {{work_experience}}.
    
    print(f"\n{green}LOGGING: Rewrite resume optimize - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeAchievements():
    """
        Write a resume achievements for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Here is my current resume. As an experience resume writer, write 5 resume achievements for this job description:

                {{job description}}


                '''
                    #including these keywords: 
                    #{{keywords}}. Write a resume as a top business executive, that include metrics and the most 
                    #important keywords: {{keywords_improved}}. Keep my past titles and companies from my work experience:
                    #  {{work_experience}}.
    
    print(f"\n{green}LOGGING: Rewrite resume 5 achievements - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeImprove():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' Update the resume: {{resume_update}} with this job description: 
                    {{job_description}}, including these keywords: {{keywords}}. 
                '''
    #Merge a first resume: {{resume}} and a second resume {{resume_update}}. Also include information from another version of this resume: {{resume}}.
    print(f"\n{green}LOGGING: Improve resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeAskImprove():
    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' You are an experienced resume writer who specializes in making resumes for leadership roles in Data Science, Artificial intelligence
                and Machine Learing, and Engineering. How would you improve this {{resume_update_2}} with this job description: 
                    {{job_description}}, including these keywords: {{keywords}}. Please advise and rewrite this resume.
                '''
    #Merge a first resume: {{resume}} and a second resume {{resume_update}}. Also include information from another version of this resume: {{resume}}.
    print(f"\n{green}LOGGING: Improve resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)


def ResumeCheckup():

    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' You are a senior hiring manager with years of experience hiring for leadership roles in Data Science, Artificial intelligence
                and Machine Learing, and Engineering. Please take a look at this job description for a Director of Data Science and identify the
                  10 most important qualifications and skills for candidates to have in this role. Here is the job listing:
                  {{job_description}}.
                '''
    #Merge a first resume: {{resume}} and a second resume {{resume_update}}. Also include information from another version of this resume: {{resume}}.
    print(f"\n{green}LOGGING: 10 improvements resume - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

def ResumeCheckin():

    """
        Write a resume for a job application. One pass to the LLM.
    """
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' You are looking to stand out with a very professional resume listing the most recent work experience. Please update this resume 
                    with 10 improvements: {{resume}} \n {{resume_update_4}}
                '''
    #Merge a first resume: {{resume}} and a second resume {{resume_update}}. Also include information from another version of this resume: {{resume}}.
    print(f"\n{green}LOGGING: Improve resume 10 improvements - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)

#Rewrite my {{work_experience}} by incorporating these keywords.
def ResumeJD():
    green = "\033[0;32m"
    white = "\033[0;39m"
    template = f''' You are an experienced resume writer who specializes in making resumes for leadership roles in Data Science, Artificial intelligence
                and Machine Learning, and Engineering. 1Please take a look at this job description for a {{job_title}} and {{company}} and write a resume 
                with bullet point achievements that show impact and metrics. Here is the job listing:
                {{job_description}}. 
                '''
    print(f"\n{green}LOGGING: Write resume from job description - formatted prompt template string to an LLM model --------{white}")
    return PromptTemplate.from_template(template)