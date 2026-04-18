import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / 'praktor'))

import pytest

from LLM.llm_factory import LLMFactory


class TestLLMFactory:

    def setup_method(self):
        self.factory = LLMFactory()

    @patch('langchain_ollama.llms.OllamaLLM')
    def test_create_ollama_model(self, mock_ollama):
        mock_ollama.return_value = MagicMock()
        llm = self.factory.create_llm('qwen2.5')
        mock_ollama.assert_called_once_with(model='qwen2.5', temperature=0.0)

    def test_create_gpt_instruct(self):
        fake_openai = MagicMock()
        fake_module = MagicMock()
        fake_module.OpenAI = fake_openai
        with patch.dict('sys.modules', {'langchain_openai': MagicMock(), 'langchain_openai.llms': fake_module}):
            llm = self.factory.create_llm('gpt-3.5-turbo-instruct')
        fake_openai.assert_called_once_with(model='gpt-3.5-turbo-instruct', temperature=0.0)

    @patch('langchain_anthropic.ChatAnthropic')
    def test_create_claude_sonnet(self, mock_anthropic):
        mock_anthropic.return_value = MagicMock()
        llm = self.factory.create_llm('claude-sonnet-4-6')
        mock_anthropic.assert_called_once_with(model='claude-sonnet-4-6', temperature=0.0)

    @patch('langchain_anthropic.ChatAnthropic')
    def test_create_claude_opus(self, mock_anthropic):
        mock_anthropic.return_value = MagicMock()
        self.factory.create_llm('claude-opus-4-6')
        mock_anthropic.assert_called_once_with(model='claude-opus-4-6', temperature=0.0)

    @patch('langchain_ollama.llms.OllamaLLM')
    def test_unknown_model_falls_back_to_ollama(self, mock_ollama):
        mock_ollama.return_value = MagicMock()
        self.factory.create_llm('some-custom-model')
        mock_ollama.assert_called_once_with(model='some-custom-model', temperature=0.0)
