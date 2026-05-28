"""
抓取模块 - 页面变化监测
负责：
- 抓取网页内容
- 提取文本并计算哈希
- 检测页面是否发生变化
"""

import requests
from bs4 import BeautifulSoup
import logging
from typing import Optional, Tuple
import hashlib

logger = logging.getLogger(__name__)


class PageChangeFetcher:
    """页面变化监测抓取器"""
    
    def __init__(self, user_agent: str = None, timeout: int = 10):
        """
        初始化页面抓取器
        
        Args:
            user_agent: User-Agent 字符串
            timeout: 请求超时时间（秒）
        """
        self.user_agent = user_agent or "JapanJobMonitor/1.0"
        self.timeout = timeout
    
    def fetch(self, url: str) -> Tuple[Optional[str], Optional[str]]:
        """
        抓取网页并提取文本内容和标题
        
        Args:
            url: 网页 URL
            
        Returns:
            (title, content_text) 元组，失败时返回 (None, None)
        """
        logger.info(f"抓取页面：{url}")
        
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ja,en-US;q=0.7,en;q=0.3',
            }
            
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            
            # 处理编码问题：服务器可能返回错误的编码信息
            # 优先使用 apparent_encoding 自动检测正确的编码
            if response.encoding == 'ISO-8859-1' or not response.encoding:
                # ISO-8859-1 通常是默认值，实际可能是 UTF-8 或其他
                response.encoding = response.apparent_encoding
                logger.debug(f"自动检测编码：{response.encoding}")
            
            # 强制使用 UTF-8 解码（如果检测失败）
            try:
                html_content = response.content.decode('utf-8')
            except UnicodeDecodeError:
                # 如果 UTF-8 失败，尝试用检测到的编码
                try:
                    html_content = response.content.decode(response.encoding or 'utf-8', errors='ignore')
                except Exception:
                    # 最后手段：直接忽略错误
                    html_content = response.text
            
            # 解析 HTML，使用 lxml 或 html.parser
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
            except Exception as e:
                logger.warning(f"html.parser 解析失败，尝试 lxml: {e}")
                try:
                    soup = BeautifulSoup(html_content, 'lxml')
                except Exception:
                    # 如果都失败，使用纯文本模式
                    soup = BeautifulSoup(html_content, 'html5lib')
            
            # 提取标题
            title = ""
            if soup.title:
                title = soup.title.string or ""
            # 尝试提取 h1
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text(strip=True) or title
            
            # 提取正文文本
            # 移除不需要的元素
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            # 获取文本内容
            content_text = soup.get_text(separator=' ', strip=True)
            
            # 清理空白字符
            content_text = ' '.join(content_text.split())
            
            logger.info(f"页面抓取完成：{url}, 内容长度：{len(content_text)}")
            return (title, content_text)
            
        except requests.exceptions.RequestException as e:
            logger.error(f"页面抓取失败：{url}, 错误：{e}")
            return (None, None)
        except Exception as e:
            logger.error(f"页面解析失败：{url}, 错误：{e}")
            return (None, None)
    
    def compute_hash(self, content: str) -> str:
        """
        计算内容的 SHA256 哈希
        
        Args:
            content: 文本内容
            
        Returns:
            哈希字符串
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def check_and_fetch(self, url: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        抓取页面并返回是否成功、标题、内容哈希、内容摘要
        
        Args:
            url: 网页 URL
            
        Returns:
            (success, title, content_hash, content_summary) 元组
        """
        title, content = self.fetch(url)
        
        if title is None or content is None:
            return (False, None, None, None)
        
        content_hash = self.compute_hash(content)
        
        # 生成内容摘要（前 200 字）
        content_summary = content[:200] + "..." if len(content) > 200 else content
        
        return (True, title, content_hash, content_summary)
