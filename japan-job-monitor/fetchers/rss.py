"""
抓取模块 - RSS 源处理
负责：
- 解析 RSS/Atom feed
- 提取条目信息
"""

import feedparser
import logging
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RSSFetcher:
    """RSS 源抓取器"""
    
    def __init__(self, user_agent: str = None, timeout: int = 10):
        """
        初始化 RSS 抓取器
        
        Args:
            user_agent: User-Agent 字符串
            timeout: 请求超时时间（秒）
        """
        self.user_agent = user_agent or "JapanJobMonitor/1.0"
        self.timeout = timeout
    
    def fetch(self, url: str) -> List[Dict]:
        """
        抓取并解析 RSS feed
        
        Args:
            url: RSS feed 的 URL
            
        Returns:
            条目列表，每个条目是包含 title/link/content_hash 等的字典
        """
        logger.info(f"抓取 RSS: {url}")
        
        try:
            # 设置 User-Agent
            headers = {'User-Agent': self.user_agent}
            
            # 解析 RSS
            feed = feedparser.parse(url, request_headers=headers, timeout=self.timeout)
            
            # 检查是否有错误
            if feed.bozo:
                logger.warning(f"RSS 解析警告：{feed.bozo_exception}")
            
            entries = []
            for item in feed.entries:
                # 提取基本信息
                title = item.get('title', '无标题')
                link = item.get('link', '')
                
                # 生成唯一键（使用链接）
                unique_key = link
                
                # 提取内容/摘要
                content = ""
                if hasattr(item, 'content') and item.content:
                    content = item.content[0].get('value', '')
                elif hasattr(item, 'summary'):
                    content = item.summary
                
                # 获取发布时间
                published = ""
                if hasattr(item, 'published'):
                    published = item.published
                elif hasattr(item, 'updated'):
                    published = item.updated
                
                # 计算内容哈希（用于去重比对）
                import hashlib
                content_hash = hashlib.sha256(
                    f"{title}:{content}:{link}".encode('utf-8')
                ).hexdigest()
                
                entry = {
                    'title': title,
                    'link': link,
                    'unique_key': unique_key,
                    'content': content,
                    'content_hash': content_hash,
                    'published': published,
                    'source_url': url
                }
                entries.append(entry)
            
            logger.info(f"RSS 抓取完成：{url}, 共 {len(entries)} 条")
            return entries
            
        except Exception as e:
            logger.error(f"RSS 抓取失败：{url}, 错误：{e}")
            return []
    
    def fetch_with_keywords(self, url: str, keywords: List[str]) -> List[Dict]:
        """
        抓取 RSS 并按关键词过滤
        
        Args:
            url: RSS feed URL
            keywords: 关键词列表
            
        Returns:
            命中关键词的条目列表
        """
        all_entries = self.fetch(url)
        
        if not keywords:
            return all_entries
        
        filtered = []
        for entry in all_entries:
            # 检查标题和内容是否命中任一关键词
            text_to_check = f"{entry['title']} {entry['content']}"
            for keyword in keywords:
                if keyword in text_to_check:
                    entry['matched_keyword'] = keyword
                    filtered.append(entry)
                    break
        
        logger.info(f"RSS 关键词过滤：{url}, 命中 {len(filtered)}/{len(all_entries)} 条")
        return filtered
