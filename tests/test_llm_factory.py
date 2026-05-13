import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from praktor.LLM.llm_factory import LLMFactory


class TestLLMFactory:

    def setup_method(self):
        self.factory = LLMFactory()

    @patch('langchain_ollama.llms.OllamaLLM')
    def test_create_ollama_model(self, mock_ollama):
        mock_ollama.return_value = MagicMock()
        self.factory.create_llm('qwen2.5')
        mock_ollama.assert_called_once_with(model='qwen2.5', temperature=0.0)

    def test_create_gpt_instruct(self):
        fake_openai = MagicMock()
        fake_module = MagicMock()
        fake_module.OpenAI = fake_openai
        with patch.dict('sys.modules', {'langchain_openai': MagicMock(), 'langchain_openai.llms': fake_module}):
            self.factory.create_llm('gpt-3.5-turbo-instruct')
        fake_openai.assert_called_once_with(model='gpt-3.5-turbo-instruct', temperature=0.0)

    def test_create_claude_sonnet(self):
        pytest.importorskip("langchain_anthropic")
        with patch('langchain_anthropic.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            self.factory.create_llm('claude-sonnet-4-6')
            mock_anthropic.assert_called_once_with(model='claude-sonnet-4-6', temperature=0.0)

    def test_create_claude_opus(self):
        pytest.importorskip("langchain_anthropic")
        with patch('langchain_anthropic.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            self.factory.create_llm('claude-opus-4-6')
            mock_anthropic.assert_called_once_with(model='claude-opus-4-6', temperature=0.0)

    @patch('langchain_ollama.llms.OllamaLLM')
    def test_unknown_prefix_falls_back_to_ollama(self, mock_ollama):
        """Unrecognized model names are routed to Ollama by design."""
        mock_ollama.return_value = MagicMock()
        self.factory.create_llm('some-local-model')
        mock_ollama.assert_called_once_with(model='some-local-model', temperature=0.0)

    def test_create_gpt4o_uses_chat_completions(self):
        """Modern GPT-4/o-series must use ChatOpenAI, not legacy OpenAI."""
        fake_chat = MagicMock()
        fake_langchain_openai = MagicMock()
        fake_langchain_openai.ChatOpenAI = fake_chat
        with patch.dict('sys.modules', {
            'langchain_openai': fake_langchain_openai,
            'langchain_openai.llms': MagicMock(),
        }):
            self.factory.create_llm('gpt-4o')
        fake_chat.assert_called_once_with(model='gpt-4o', temperature=0.0)

    def test_create_o1_preview_uses_chat_completions(self):
        """o1/o3-series models are routed to ChatOpenAI."""
        fake_chat = MagicMock()
        fake_langchain_openai = MagicMock()
        fake_langchain_openai.ChatOpenAI = fake_chat
        with patch.dict('sys.modules', {
            'langchain_openai': fake_langchain_openai,
            'langchain_openai.llms': MagicMock(),
        }):
            self.factory.create_llm('o1-preview')
        fake_chat.assert_called_once_with(model='o1-preview', temperature=0.0)

    @patch('langchain_ollama.llms.OllamaLLM')
    def test_temperature_forwarded_to_ollama(self, mock_ollama):
        mock_ollama.return_value = MagicMock()
        self.factory.create_llm('llama3.1', temperature=0.7)
        mock_ollama.assert_called_once_with(model='llama3.1', temperature=0.7)

    def test_temperature_forwarded_to_anthropic(self):
        pytest.importorskip("langchain_anthropic")
        with patch('langchain_anthropic.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            self.factory.create_llm('claude-sonnet-4-6', temperature=0.4)
            mock_anthropic.assert_called_once_with(model='claude-sonnet-4-6', temperature=0.4)

    def test_claude_shorthand_normalized(self):
        """'sonnet-4.6' expands to 'claude-sonnet-4-6' before dispatch."""
        pytest.importorskip("langchain_anthropic")
        with patch('langchain_anthropic.ChatAnthropic') as mock_anthropic:
            mock_anthropic.return_value = MagicMock()
            self.factory.create_llm('sonnet-4.6')
            args, _ = mock_anthropic.call_args
            assert mock_anthropic.call_args[1]['model'] == 'claude-sonnet-4-6'
