#!/usr/bin/env python3
"""
赴日工作信息监测系统 - 主程序

功能：
- 读取配置文件 (sources.yaml, keywords.txt)
- 抓取各类信息源（RSS、页面变化、邮箱）
- 去重并检测变化
- 通过 Hermes 发送通知

用法：
    python main.py
    
定时执行（crontab 示例）：
    0 9 * * * cd /path/to/japan-job-monitor && /usr/bin/python3 main.py >> monitor.log 2>&1
    0 21 * * * cd /path/to/japan-job-monitor && /usr/bin/python3 main.py >> monitor.log 2>&1
"""

import os
import sys
import time
import logging
from datetime import datetime
from typing import List, Dict
import yaml
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 导入自定义模块
from storage import Storage
from notifier import notify
from fetchers import RSSFetcher, PageChangeFetcher, EmailFetcher


# ==================== 日志配置 ====================

def setup_logging(log_file: str = "monitor.log", level: str = "INFO"):
    """
    配置日志系统
    
    Args:
        log_file: 日志文件路径
        level: 日志级别
    """
    # 获取日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # 创建日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    
    # 根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)


# ==================== 配置加载 ====================

def load_config(config_dir: str = "config") -> dict:
    """
    加载配置文件
    
    Args:
        config_dir: 配置文件目录
        
    Returns:
        配置字典
    """
    sources_file = os.path.join(config_dir, "sources.yaml")
    keywords_file = os.path.join(config_dir, "keywords.txt")
    
    # 加载 sources.yaml
    with open(sources_file, 'r', encoding='utf-8') as f:
        sources_config = yaml.safe_load(f)
    
    # 加载 keywords.txt
    keywords = []
    if os.path.exists(keywords_file):
        with open(keywords_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    keywords.append(line)
    
    return {
        'sources': sources_config.get('sources', []),
        'keywords': keywords,
        'enable_translation': sources_config.get('enable_translation', False),
        'fetch_settings': sources_config.get('fetch_settings', {})
    }


# ==================== 关键词过滤 ====================

def contains_keyword(text: str, keywords: List[str]) -> bool:
    """
    检查文本是否包含任一关键词
    
    Args:
        text: 待检查的文本
        keywords: 关键词列表
        
    Returns:
        True=命中关键词，False=未命中
    """
    if not keywords:
        return True  # 没有关键词列表时，全部通过
    
    for keyword in keywords:
        if keyword in text:
            return True
    return False


def get_matched_keyword(text: str, keywords: List[str]) -> str:
    """
    获取命中的关键词
    
    Returns:
        命中的关键词，未命中返回空字符串
    """
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""


# ==================== 处理逻辑 ====================

def process_page_change_sources(sources: List[Dict], keywords: List[str], 
                                storage: Storage, fetch_settings: dict) -> int:
    """
    处理页面变化监测源（A 类和 C 类）
    
    Args:
        sources: 源配置列表
        keywords: 关键词列表
        storage: 存储实例
        fetch_settings: 抓取设置
        
    Returns:
        成功处理的源数量
    """
    fetcher = PageChangeFetcher(
        user_agent=fetch_settings.get('user_agent'),
        timeout=fetch_settings.get('timeout', 10)
    )
    
    success_count = 0
    request_interval = fetch_settings.get('request_interval', 3)
    
    for source in sources:
        source_type = source.get('type')
        
        # 只处理 page_change 类型
        if source_type != 'page_change':
            continue
        
        source_name = source.get('name', 'Unknown')
        url = source.get('url')
        channel = source.get('channel', 'both')
        
        if not url:
            logging.warning(f"跳过无 URL 的源：{source_name}")
            continue
        
        logging.info(f"\n{'='*60}")
        logging.info(f"处理页面监测源：{source_name}")
        logging.info(f"URL: {url}")
        
        # 抓取页面
        success, title, content_hash, content_summary = fetcher.check_and_fetch(url)
        
        if not success:
            logging.error(f"抓取失败：{source_name}")
            # 继续处理下一个源，不中断
            time.sleep(request_interval)
            continue
        
        logging.info(f"页面标题：{title}")
        
        # 检查是否有变化
        has_changed = storage.check_page_change(source_name, content_hash)
        
        if has_changed:
            logging.info("✓ 检测到页面变化！")
            
            # 判断是否需要推送
            # C 类（中介名录）：只要有变化就推送
            # A 类（政策）：需要命中关键词才推送
            
            is_registry = any(kw in source_name for kw in ['商务', '名录', '中介'])
            should_notify = is_registry or contains_keyword(f"{title} {content_summary}", keywords)
            
            if should_notify:
                matched_kw = get_matched_keyword(f"{title} {content_summary}", keywords)
                
                # 构建通知内容
                notification_title = f"【{'中介名录' if is_registry else '政策更新'}】{source_name}"
                notification_body = f"标题：{title}\n\n内容摘要：{content_summary}"
                if matched_kw:
                    notification_body += f"\n\n命中关键词：{matched_kw}"
                
                # 发送通知
                notify(channel, notification_title, notification_body, url)
                
                # 更新数据库
                storage.update_page_hash(source_name, content_hash, title)
                success_count += 1
                
                logging.info(f"已推送通知，渠道：{channel}")
            else:
                logging.info("页面有变化但未命中关键词，跳过推送")
                # 仍然更新哈希，避免下次重复检测
                storage.update_page_hash(source_name, content_hash, title)
        else:
            logging.info("页面无变化")
        
        # 限速
        time.sleep(request_interval)
    
    return success_count


def process_email_sources(sources: List[Dict], storage: Storage) -> int:
    """
    处理邮箱源（B 类 - 招聘职位）
    
    Args:
        sources: 源配置列表
        storage: 存储实例
        
    Returns:
        新职位的数量
    """
    fetcher = EmailFetcher()
    
    new_job_count = 0
    
    for source in sources:
        if source.get('type') != 'email':
            continue
        
        source_name = source.get('name', '求职邮箱')
        channel = source.get('channel', 'both')
        
        logging.info(f"\n{'='*60}")
        logging.info(f"处理邮箱源：{source_name}")
        
        # 拉取未读邮件
        jobs = fetcher.fetch_unread_emails(mark_as_read=True)
        
        if not jobs:
            logging.info("没有新的求职邮件")
            continue
        
        logging.info(f"提取到 {len(jobs)} 个职位")
        
        # 去重并推送新职位
        for job in jobs:
            unique_key = job.get('unique_key', '')
            title = job.get('title', '无标题')
            link = job.get('link', '')
            platform = job.get('platform', 'Unknown')
            
            # 检查是否是新职位
            if storage.is_new_item(source_name, 'job', unique_key):
                # 添加到数据库
                storage.add_item(
                    source_name=source_name,
                    item_type='job',
                    unique_key=unique_key,
                    title=title,
                    url=link,
                    extra_data=f'{{"platform": "{platform}"}}'
                )
                
                # 构建通知内容
                notification_title = f"【新职位】{platform}: {title[:50]}"
                notification_body = f"平台：{platform}\n标题：{title}"
                if link:
                    notification_body += f"\n链接：{link}"
                
                # 发送通知
                notify(channel, notification_title, notification_body, link)
                
                new_job_count += 1
                logging.info(f"新职位已推送：{title[:30]}...")
            else:
                logging.debug(f"职位已存在，跳过：{title[:30]}...")
    
    return new_job_count


def process_rss_sources(sources: List[Dict], keywords: List[str], 
                        storage: Storage, fetch_settings: dict) -> int:
    """
    处理 RSS 源（如果有）
    
    Args:
        sources: 源配置列表
        keywords: 关键词列表
        storage: 存储实例
        fetch_settings: 抓取设置
        
    Returns:
        新条目的数量
    """
    fetcher = RSSFetcher(
        user_agent=fetch_settings.get('user_agent'),
        timeout=fetch_settings.get('timeout', 10)
    )
    
    new_count = 0
    request_interval = fetch_settings.get('request_interval', 3)
    
    for source in sources:
        if source.get('type') != 'rss':
            continue
        
        source_name = source.get('name', 'Unknown')
        url = source.get('url')
        channel = source.get('channel', 'both')
        
        if not url:
            continue
        
        logging.info(f"\n{'='*60}")
        logging.info(f"处理 RSS 源：{source_name}")
        logging.info(f"URL: {url}")
        
        # 抓取并按关键词过滤
        entries = fetcher.fetch_with_keywords(url, keywords)
        
        if not entries:
            logging.info("没有匹配关键词的新条目")
            time.sleep(request_interval)
            continue
        
        logging.info(f"找到 {len(entries)} 条匹配的条目")
        
        # 去重并推送
        for entry in entries:
            unique_key = entry.get('unique_key', '')
            title = entry.get('title', '无标题')
            link = entry.get('link', '')
            
            if storage.is_new_item(source_name, 'policy', unique_key):
                storage.add_item(
                    source_name=source_name,
                    item_type='policy',
                    unique_key=unique_key,
                    title=title,
                    url=link
                )
                
                matched_kw = entry.get('matched_keyword', '')
                notification_title = f"【政策更新】{source_name}"
                notification_body = f"标题：{title}\n命中关键词：{matched_kw}"
                if link:
                    notification_body += f"\n链接：{link}"
                
                notify(channel, notification_title, notification_body, link)
                
                new_count += 1
                logging.info(f"新条目已推送：{title[:30]}...")
        
        time.sleep(request_interval)
    
    return new_count


# ==================== 主函数 ====================

def main():
    """主函数入口"""
    
    # 初始化日志
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    logger = setup_logging(level=log_level)
    
    logger.info("\n" + "="*70)
    logger.info("赴日工作信息监测系统 启动")
    logger.info(f"启动时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*70)
    
    try:
        # 加载配置
        logger.info("加载配置文件...")
        config = load_config()
        
        sources = config['sources']
        keywords = config['keywords']
        fetch_settings = config['fetch_settings']
        
        logger.info(f"加载 {len(sources)} 个信息源")
        logger.info(f"关键词数量：{len(keywords)}")
        if keywords:
            logger.info(f"关键词列表：{', '.join(keywords[:5])}...")
        
        # 初始化存储
        logger.info("初始化数据库...")
        storage = Storage()
        
        # 显示统计信息
        stats = storage.get_stats()
        if stats.get('total', 0) > 0:
            logger.info(f"数据库中已有 {stats['total']} 条记录")
        
        # 处理各类源
        total_notifications = 0
        
        # 1. 处理页面变化监测（A 类政策 + C 类名录）
        page_changes = process_page_change_sources(sources, keywords, storage, fetch_settings)
        total_notifications += page_changes
        logger.info(f"\n页面变化监测完成，推送 {page_changes} 次")
        
        # 2. 处理邮箱（B 类职位）
        new_jobs = process_email_sources(sources, storage)
        total_notifications += new_jobs
        logger.info(f"\n邮箱处理完成，新职位 {new_jobs} 个")
        
        # 3. 处理 RSS（如果有）
        rss_entries = process_rss_sources(sources, keywords, storage, fetch_settings)
        total_notifications += rss_entries
        logger.info(f"\nRSS 处理完成，新条目 {rss_entries} 个")
        
        # 总结
        logger.info("\n" + "="*70)
        logger.info("本次运行完成")
        logger.info(f"总推送次数：{total_notifications}")
        logger.info(f"结束时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*70)
        
    except Exception as e:
        logger.exception(f"程序运行出错：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
