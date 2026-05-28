"""
抓取模块 - 邮箱收件箱处理
负责：
- 通过 IMAP 登录邮箱
- 拉取未读邮件
- 解析求职提醒邮件
- 提取职位信息
"""

import imaplib
import email
from email.header import decode_header
import logging
from typing import List, Dict, Optional
from datetime import datetime
import re
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


class EmailFetcher:
    """邮箱收件箱抓取器"""
    
    def __init__(self):
        """
        初始化邮箱抓取器
        从环境变量读取 IMAP 配置
        """
        self.imap_server = os.getenv('IMAP_SERVER')
        self.imap_port = int(os.getenv('IMAP_PORT', '993'))
        self.imap_username = os.getenv('IMAP_USERNAME')
        self.imap_password = os.getenv('IMAP_PASSWORD')
        
        # 检查配置是否完整
        if not all([self.imap_server, self.imap_username, self.imap_password]):
            logger.warning("IMAP 配置不完整，邮箱抓取功能将不可用")
            logger.warning("请在 .env 文件中配置 IMAP_SERVER, IMAP_USERNAME, IMAP_PASSWORD")
    
    def _decode_mime_word(self, encoded_str) -> str:
        """解码 MIME 编码的字符串（用于邮件主题和发件人）"""
        if not encoded_str:
            return ""
        
        decoded_parts = decode_header(encoded_str)
        result = ""
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result += part.decode(encoding or 'utf-8', errors='ignore')
                except LookupError:
                    result += part.decode('utf-8', errors='ignore')
            else:
                result += part
        return result
    
    def _extract_email_body(self, msg) -> str:
        """
        提取邮件正文
        
        优先提取 HTML 正文，如果没有则提取纯文本
        """
        body = ""
        
        # 遍历邮件的所有部分
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                # 跳过附件
                if "attachment" in content_disposition:
                    continue
                
                if content_type == "text/plain":
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if payload:
                            body += payload.decode(charset, errors='ignore')
                    except Exception:
                        pass
                elif content_type == "text/html":
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        payload = part.get_payload(decode=True)
                        if payload:
                            # 简单去除 HTML 标签
                            from bs4 import BeautifulSoup
                            html = payload.decode(charset, errors='ignore')
                            soup = BeautifulSoup(html, 'html.parser')
                            body += soup.get_text(separator=' ', strip=True)
                    except Exception:
                        pass
        else:
            # 非多部分邮件
            try:
                charset = msg.get_content_charset() or 'utf-8'
                payload = msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(charset, errors='ignore')
            except Exception:
                pass
        
        return body
    
    def _identify_job_email(self, subject: str, from_addr: str, body: str) -> Optional[Dict]:
        """
        识别是否是求职提醒邮件，并提取平台信息
        
        Args:
            subject: 邮件主题
            from_addr: 发件人地址
            body: 邮件正文
            
        Returns:
            如果是求职邮件，返回包含平台信息的字典；否则返回 None
        """
        # 常见求职平台的标识
        platforms = {
            'Rikunabi': ['rikunabi', 'リクナビ'],
            'Mynavi': ['mynavi', 'マイナビ'],
            'doda': ['doda', 'デューダ'],
            'Indeed': ['indeed', 'インディード'],
            'BizReach': ['bizreach', 'ビズリーチ'],
            'LinkedIn': ['linkedin', 'LinkedIn'],
        }
        
        text_to_check = f"{subject} {from_addr} {body}".lower()
        
        for platform, keywords in platforms.items():
            for keyword in keywords:
                if keyword.lower() in text_to_check:
                    return {'platform': platform}
        
        # 如果无法识别具体平台，但看起来像求职邮件
        job_keywords = ['求人', 'job', '职位', '募集', '採用', 'new posting']
        for kw in job_keywords:
            if kw.lower() in text_to_check:
                return {'platform': 'Unknown'}
        
        return None
    
    def _extract_job_info(self, subject: str, body: str) -> List[Dict]:
        """
        从邮件中提取职位信息
        
        Args:
            subject: 邮件主题
            body: 邮件正文
            
        Returns:
            职位信息列表
        """
        jobs = []
        
        # 尝试提取链接
        url_pattern = r'https?://[^\s<>"]+'
        urls = re.findall(url_pattern, body)
        
        # 清理主题作为默认标题
        default_title = self._decode_mime_word(subject)
        
        # 如果有链接，每个链接视为一个职位
        if urls:
            for i, url in enumerate(urls[:5]):  # 最多提取 5 个链接
                job = {
                    'title': default_title,
                    'link': url,
                    'unique_key': url,
                    'content': body[:500],  # 保存部分正文
                    'source': 'email'
                }
                jobs.append(job)
        else:
            # 没有链接，使用主题作为唯一标识
            job = {
                'title': default_title,
                'link': '',
                'unique_key': f"email:{default_title}",
                'content': body[:500],
                'source': 'email'
            }
            jobs.append(job)
        
        return jobs
    
    def fetch_unread_emails(self, mark_as_read: bool = True) -> List[Dict]:
        """
        拉取未读邮件并提取职位信息
        
        Args:
            mark_as_read: 是否将处理过的邮件标记为已读
            
        Returns:
            职位信息列表
        """
        if not self.imap_server:
            logger.warning("IMAP 未配置，跳过邮箱抓取")
            return []
        
        logger.info(f"连接邮箱：{self.imap_server}")
        
        try:
            # 连接 IMAP 服务器
            if self.imap_port == 993:
                mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            else:
                mail = imaplib.IMAP4(self.imap_server, self.imap_port)
            
            # 登录
            mail.login(self.imap_username, self.imap_password)
            
            # 选择收件箱
            mail.select('INBOX')
            
            # 搜索未读邮件
            status, messages = mail.search(None, 'UNSEEN')
            
            if status != 'OK':
                logger.warning("搜索未读邮件失败")
                return []
            
            unread_ids = messages[0].split()
            logger.info(f"找到 {len(unread_ids)} 封未读邮件")
            
            all_jobs = []
            
            for msg_id in unread_ids:
                try:
                    # 获取邮件
                    status, msg_data = mail.fetch(msg_id, '(RFC822)')
                    
                    if status != 'OK':
                        continue
                    
                    # 解析邮件
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # 解码主题和发件人
                    subject = self._decode_mime_word(msg['Subject'])
                    from_addr = self._decode_mime_word(msg['From'])
                    date = msg['Date']
                    
                    # 提取正文
                    body = self._extract_email_body(msg)
                    
                    # 识别是否是求职邮件
                    platform_info = self._identify_job_email(subject, from_addr, body)
                    
                    if platform_info:
                        logger.info(f"识别到求职邮件：{subject[:50]}... (平台：{platform_info['platform']})")
                        
                        # 提取职位信息
                        jobs = self._extract_job_info(subject, body)
                        for job in jobs:
                            job['platform'] = platform_info['platform']
                            job['from'] = from_addr
                            job['date'] = date
                            all_jobs.append(job)
                    
                    # 标记为已读
                    if mark_as_read:
                        mail.store(msg_id, '+FLAGS', '\\Seen')
                    
                except Exception as e:
                    logger.error(f"处理邮件失败：{e}")
                    continue
            
            # 关闭连接
            mail.close()
            mail.logout()
            
            logger.info(f"邮箱抓取完成，共提取 {len(all_jobs)} 个职位")
            return all_jobs
            
        except imaplib.IMAP4.error as e:
            logger.error(f"IMAP 错误：{e}")
            return []
        except Exception as e:
            logger.error(f"邮箱抓取失败：{e}")
            return []
