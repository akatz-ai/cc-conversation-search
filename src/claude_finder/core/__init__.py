"""Core functionality for claude-finder"""

from .indexer import ConversationIndexer
from .search import ConversationSearch
from .summarization import MessageSummarizer
from .watcher import start_watcher

__all__ = ['ConversationIndexer', 'ConversationSearch', 'MessageSummarizer', 'start_watcher']
