import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from praktor.schemas import (
    parse_message,
    JobApplicationMessage,
    CoverLetterMessage,
    ThankYouMessage,
    SearchMessage,
    MessageMessage,
    KeywordsExtractionMessage,
    JobInterviewMessage,
)


class TestParseMessage:

    def test_job_application_valid(self):
        data = {
            'agent_type': 'job_application',
            'job_title': 'Director of Data Science',
            'company': 'Acme Corp',
            'job_description': 'Lead data science initiatives...',
        }
        msg = parse_message(data)
        assert isinstance(msg, JobApplicationMessage)
        assert msg.job_title == 'Director of Data Science'

    def test_cover_letter_valid(self):
        data = {
            'agent_type': 'cover_letter',
            'job_title': 'VP Engineering',
            'company': 'Startup Inc',
            'job_description': 'Build and scale the eng team...',
        }
        msg = parse_message(data)
        assert isinstance(msg, CoverLetterMessage)

    def test_thank_you_valid(self):
        data = {
            'agent_type': 'thank_you',
            'adjective': 'professional',
            'position': 'AVP Data Science',
            'content': 'Great interview about GenAI strategy.',
        }
        msg = parse_message(data)
        assert isinstance(msg, ThankYouMessage)
        assert msg.adjective == 'professional'

    def test_search_valid(self):
        data = {
            'agent_type': 'search',
            'search': 'GenAI ROI in healthcare',
            'content': 'focus on insurance sector',
        }
        msg = parse_message(data)
        assert isinstance(msg, SearchMessage)

    def test_message_valid(self):
        data = {
            'agent_type': 'message',
            'topic': 'Leadership transition',
            'emotion': 'care, empathy',
        }
        msg = parse_message(data)
        assert isinstance(msg, MessageMessage)

    def test_keywords_extraction_valid(self):
        data = {
            'agent_type': 'keywords_extraction',
            'job_title': 'Data Scientist',
            'company': 'HealthCo',
            'job_description': 'Extract insights from claims data...',
        }
        msg = parse_message(data)
        assert isinstance(msg, KeywordsExtractionMessage)

    def test_job_interview_valid(self):
        data = {
            'agent_type': 'job_interview',
            'search': 'GenAI ROI estimates',
            'content': 'healthcare sector',
        }
        msg = parse_message(data)
        assert isinstance(msg, JobInterviewMessage)

    def test_unknown_agent_type_raises(self):
        with pytest.raises(ValueError, match="Unknown or missing agent_type"):
            parse_message({'agent_type': 'nonexistent'})

    def test_missing_agent_type_raises(self):
        with pytest.raises(ValueError, match="Unknown or missing agent_type"):
            parse_message({'job_title': 'Data Scientist'})

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            parse_message({
                'agent_type': 'thank_you',
                'adjective': 'professional',
                # missing 'position' and 'content'
            })

    def test_model_dump_roundtrip(self):
        data = {
            'agent_type': 'search',
            'search': 'concept drift',
            'content': 'production ML systems',
        }
        msg = parse_message(data)
        dumped = msg.model_dump()
        assert dumped['agent_type'] == 'search'
        assert dumped['search'] == 'concept drift'
