"""
抓取模块初始化文件
"""

from .rss import RSSFetcher
from .page_change import PageChangeFetcher
from .email_inbox import EmailFetcher

__all__ = ['RSSFetcher', 'PageChangeFetcher', 'EmailFetcher']
