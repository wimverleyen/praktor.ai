
from langchain_community.embeddings import OllamaEmbeddings
from langchain_ollama.llms import OllamaLLM
from langchain_community.vectorstores import FAISS

#from LLM.llm_factory import LLM
from LLM.prompt import PromptSearch, PromptEmailThankYou

from settings import create_log, MODEL, VECTOR_DB

from typing import Dict, List
from operator import itemgetter
from unittest import TestCase, TestLoader, TextTestRunner

log = create_log()


class RAGTY:

    def __init__(self, prompt_method, temperature=0.0) -> None:
        self.__prompt = prompt_method
        self.__embeddings = OllamaEmbeddings(model=MODEL)

        self.__vector_store = FAISS.load_local(VECTOR_DB, self.__embeddings, \
                                                allow_dangerous_deserialization=True)
        self.__retriever = self.__vector_store.as_retriever(search_type="similarity", search_kwargs={"k":15})

        log.debug(f"DEBUG: retriever - {self.__retriever}")

        self.__llm = OllamaLLM(model=MODEL, temperature=temperature)

        self.__chain = (
            {"adjective": itemgetter("adjective"), "content": itemgetter("content"), "position": itemgetter("position") | self.__retriever,}
            | self.__prompt
            | self.__llm)

    def generate(self, adjective='', content='', position=''):

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(adjective=adjective, content=content, position=position)}')
    
        results = self.__vector_store.similarity_search_with_score(\
                                query=self.__prompt.format(adjective=adjective, content=content, position=position), k=25)
    
        log.debug(f'DEBUG: # of results: {len(results)}')
        for doc, score in results:
            log.debug(f"DEBUG: RAG - vector database [SIM={score:3f}] {doc.page_content} [{doc.metadata}]")

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(adjective=adjective, content=content, position=position)}')

        response = self.__chain.invoke(input={'adjective':adjective, 'content': content, 'position': position})
        return response

    def generate_data(self, data):

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(adjective=data['adjective'], content=data['content'], \
                                                             position=data['position'])}')
        results = self.__vector_store.similarity_search_with_score(query=self.__prompt.format(adjective=data['adjective'], content=data['content'], position=data['position']), k=25)
        log.debug(f'DEBUG: # of results: {len(results)}')
        for doc, score in results:
            log.debug(f"DEBUG: RAG - vector database [SIM={score:3f}] {doc.page_content} [{doc.metadata}]")

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(adjective=data['adjective'], content=data['content'], \
                                                             position=data['position'])}')

        response = self.__chain.invoke(input={'adjective':data['adjective'], 'content': data['content'], \
                                              'position': data['position']})
        return response
    
    def references(self, text=''):

        docs = self.__retriever.invoke(text)
        log.debug(f'DEBUG - RAG - references: # of docs {len(docs)}')
        for doc in docs:
            log.debug(f'DEBUG - RAG - references: docs {doc}')

        results = self.__vector_store.similarity_search_with_score(\
                                query=text, k=5)
        log.debug(f'DEBUG - RAG - references: # of docs {len(results)}')
        for doc, score in results:
            log.debug(f"DEBUG: RAG - vector database [SIM={score:3f}] {doc.page_content} [{doc.metadata}]")

class RAGSP:

    def __init__(self):
        
        self.__prompt = PromptSearch()

        self.__embeddings = OllamaEmbeddings(model=MODEL)
        self.__vector_store = FAISS.load_local(VECTOR_DB, self.__embeddings, \
                                                allow_dangerous_deserialization=True)
        self.__retriever = self.__vector_store.as_retriever(search_type="similarity", search_kwargs={"k":15})

        log.debug(f"DEBUG: retriever - {self.__retriever}")


        self.__llm = OllamaLLM(model=MODEL, temperature=0)

        self.__chain = (
            {"search": itemgetter("search"), "content": itemgetter("content") | self.__retriever,}
            | self.__prompt
            | self.__llm)

    def generate(self, search='', content=''):

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(search=search, content=content)}')
        results = self.__vector_store.similarity_search_with_score(\
                                query=self.__prompt.format(search=search, content=content), k=25)
        log.debug(f'DEBUG: # of results: {len(results)}')
        for doc, score in results:
            log.debug(f"DEBUG: RAG - vector database [SIM={score:3f}] {doc.page_content} [{doc.metadata}]")

        log.debug(f'DEBUG: RAG prompt: {self.__prompt.format(search=search, content=content)}')

        response = self.__chain.invoke(input={'search':search, 'content': content})
        return response
    
    def references(self, text=''):

        docs = self.__retriever.invoke(text)
        log.debug(f'DEBUG - RAG - references: # of docs {len(docs)}')
        for doc in docs:
            log.debug(f'DEBUG - RAG - references: docs {doc}')

        results = self.__vector_store.similarity_search_with_score(\
                                query=text, k=5)
        log.debug(f'DEBUG - RAG - references: # of docs {len(results)}')
        for doc, score in results:
            log.debug(f"DEBUG: RAG - vector database [SIM={score:3f}] {doc.page_content} [{doc.metadata}]")