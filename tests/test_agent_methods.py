"""
Integration-style tests for agent_method functions.

These tests mock the LLM and file I/O so they run without a live Ollama
instance or filesystem paths. Each test verifies that the agent method:
  - calls the LLM with the right prompt
  - writes output to the expected markdown file
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest


class TestMessage:

    @patch('praktor.agent_method.MD', '/tmp/')
    @patch('praktor.agent_method.save_markdown')
    @patch('praktor.agent_method.LLMAdapter')
    def test_message_calls_llm_and_saves(self, mock_adapter_cls, mock_save):
        from praktor.agent_method import Message

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = 'Generated message text'
        mock_adapter_cls.return_value = mock_adapter

        data = {'topic': 'leadership', 'emotion': 'empathy', 'agent_type': 'message'}
        Message(data)

        mock_adapter.generate.assert_called_once_with(data=data)
        mock_save.assert_called_once()
        saved_content = mock_save.call_args[0][1]
        assert saved_content == 'Generated message text'


class TestThankYouEmail:

    @patch('praktor.agent_method.MD', '/tmp/')
    @patch('praktor.agent_method.save_markdown')
    @patch('praktor.agent_method.LLMAdapter')
    def test_thank_you_calls_llm_and_saves(self, mock_adapter_cls, mock_save):
        from praktor.agent_method import ThankYouEmail

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = 'Thank you email text'
        mock_adapter_cls.return_value = mock_adapter

        data = {
            'adjective': 'professional',
            'position': 'AVP Data Science',
            'content': 'Great conversation about AI strategy',
            'agent_type': 'thank_you',
        }
        ThankYouEmail(data)

        mock_adapter.generate.assert_called_once_with(data=data)
        mock_save.assert_called_once()


class TestSearch:

    @patch('praktor.agent_method.MD', '/tmp/')
    @patch('praktor.agent_method.save_markdown')
    @patch('praktor.agent_method.LLMAdapter')
    def test_search_calls_llm_and_saves(self, mock_adapter_cls, mock_save):
        from praktor.agent_method import Search

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = 'Search result'
        mock_adapter_cls.return_value = mock_adapter

        data = {'search': 'concept drift', 'content': 'production ML', 'agent_type': 'search'}
        Search(data)

        mock_adapter.generate.assert_called_once_with(data=data)
        mock_save.assert_called_once()


class TestWriteCoverLetter:

    @patch('praktor.agent_method.MD', '/tmp/')
    @patch('praktor.agent_method.save_markdown')
    @patch('praktor.agent_method.LLMAdapter')
    def test_cover_letter_multi_pass(self, mock_adapter_cls, mock_save):
        from praktor.agent_method import WriteCoverLetter

        mock_adapter = MagicMock()
        mock_adapter.generate.side_effect = ['Draft 1', 'Improved draft', 'Final draft']
        mock_adapter_cls.return_value = mock_adapter

        data = {
            'job_title': 'Director of Data Science',
            'company': 'Acme',
            'job_description': 'Lead AI/ML...',
            'agent_type': 'cover_letter',
        }
        WriteCoverLetter(data)

        # Three passes: initial + two improvements
        assert mock_adapter.generate.call_count == 3
        # Three markdown files saved
        assert mock_save.call_count == 3


class TestJobApplication:

    @patch('praktor.agent_method.MD', '/tmp/')
    @patch('praktor.agent_method.save_markdown')
    @patch('praktor.agent_method.LLMAdapter')
    def test_job_application_saves_resume(self, mock_adapter_cls, mock_save):
        from praktor.agent_method import JobApplication

        mock_adapter = MagicMock()
        mock_adapter.generate.return_value = 'Tailored resume content'
        mock_adapter_cls.return_value = mock_adapter

        data = {
            'job_title': 'VP Data Science',
            'company': 'HealthCo',
            'job_description': 'Drive AI strategy...',
            'agent_type': 'job_application',
        }
        JobApplication(data)

        mock_adapter.generate.assert_called_once_with(data=data)
        mock_save.assert_called_once()
