"""
存储模块 - SQLite 数据库操作
负责：
- 初始化数据库和表结构
- 记录已见过的条目（去重）
- 检测页面变化（content_hash 比对）
"""

import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, List, Tuple
import logging

logger = logging.getLogger(__name__)


class Storage:
    """SQLite 存储类，管理监测数据的持久化"""
    
    def __init__(self, db_path: str = "monitor.db"):
        """
        初始化数据库连接
        
        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 让结果可以用列名访问
        return conn
    
    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 创建 seen_items 表
            # 用于存储已见过的条目，实现去重和变化检测
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_items (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,      -- 来源名称
                    item_type   TEXT NOT NULL,      -- 类型：policy/job/registry
                    unique_key  TEXT NOT NULL UNIQUE, -- 唯一键：URL 或内容哈希
                    title       TEXT,               -- 标题
                    url         TEXT,               -- 链接
                    content_hash TEXT,              -- 页面内容哈希（page_change 用）
                    first_seen  TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 首次发现时间
                    notified    INTEGER DEFAULT 0,  -- 是否已通知：0=否，1=是
                    extra_data  TEXT,               -- 额外数据（JSON 格式）
                    priority    TEXT DEFAULT 'normal', -- 优先级：critical/high/normal
                    notify_channels TEXT,           -- 通知渠道：comma-separated (email,discord)
                    tags        TEXT                -- 标签：comma-separated (政策，签证，招聘，etc)
                )
            """)
            
            # 创建索引加速查询
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_type 
                ON seen_items(source_name, item_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_unique_key 
                ON seen_items(unique_key)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_notified 
                ON seen_items(notified)
            """)
            
            conn.commit()
            logger.info(f"数据库初始化完成：{self.db_path}")
            
        except sqlite3.Error as e:
            logger.error(f"数据库初始化失败：{e}")
            raise
        finally:
            conn.close()
    
    def compute_content_hash(self, content: str) -> str:
        """
        计算页面内容的 SHA256 哈希值
        
        Args:
            content: 页面文本内容
            
        Returns:
            哈希字符串
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def is_new_item(self, source_name: str, item_type: str, unique_key: str) -> bool:
        """
        检查是否是新的条目（库里没有）
        
        Args:
            source_name: 来源名称
            item_type: 类型 (policy/job/registry)
            unique_key: 唯一键（通常是 URL）
            
        Returns:
            True=新条目，False=已存在
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM seen_items WHERE source_name=? AND item_type=? AND unique_key=?",
                (source_name, item_type, unique_key)
            )
            result = cursor.fetchone()
            return result is None
        except sqlite3.Error as e:
            logger.error(f"检查新条目失败：{e}")
            return False  # 出错时保守处理，视为已存在
        finally:
            conn.close()
    
    def check_page_change(self, source_name: str, new_hash: str) -> bool:
        """
        检查页面是否有变化（对比 content_hash）
        
        Args:
            source_name: 来源名称
            new_hash: 新的内容哈希
            
        Returns:
            True=有变化，False=无变化
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            # page_change 类型的 unique_key 固定为源名称
            unique_key = f"page:{source_name}"
            cursor.execute(
                "SELECT content_hash FROM seen_items WHERE source_name=? AND item_type='page_change' AND unique_key=?",
                (source_name, unique_key)
            )
            result = cursor.fetchone()
            
            if result is None:
                # 第一次监测，视为有变化
                return True
            
            old_hash = result['content_hash']
            return old_hash != new_hash
            
        except sqlite3.Error as e:
            logger.error(f"检查页面变化失败：{e}")
            return False
        finally:
            conn.close()
    
    def add_item(self, source_name: str, item_type: str, unique_key: str,
                 title: str = None, url: str = None, content_hash: str = None,
                 extra_data: str = None, priority: str = 'normal', 
                 notify_channels: list = None, tags: list = None) -> bool:
        """
        添加新条目到数据库
        
        Args:
            source_name: 来源名称
            item_type: 类型
            unique_key: 唯一键
            title: 标题
            url: 链接
            content_hash: 内容哈希
            extra_data: 额外数据（JSON 字符串）
            priority: 优先级 (critical/high/normal)
            notify_channels: 通知渠道列表 ['email', 'discord']
            tags: 标签列表 ['政策', '签证']
            
        Returns:
            True=成功，False=失败（如重复）
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 转换列表为逗号分隔字符串
            channels_str = ','.join(notify_channels) if notify_channels else None
            tags_str = ','.join(tags) if tags else None
            
            cursor.execute("""
                INSERT OR IGNORE INTO seen_items 
                (source_name, item_type, unique_key, title, url, content_hash, extra_data, priority, notify_channels, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (source_name, item_type, unique_key, title, url, content_hash, extra_data, priority, channels_str, tags_str))
            
            if cursor.rowcount > 0:
                conn.commit()
                logger.debug(f"添加新条目：{source_name} - {title or unique_key} [priority={priority}]")
                return True
            else:
                logger.debug(f"条目已存在，跳过：{source_name} - {title or unique_key}")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"添加条目失败：{e}")
            return False
        finally:
            conn.close()
    
    def update_page_hash(self, source_name: str, new_hash: str, title: str = None):
        """
        更新页面的内容哈希（检测到变化后调用）
        
        Args:
            source_name: 来源名称
            new_hash: 新的哈希值
            title: 可选的标题
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            unique_key = f"page:{source_name}"
            
            # 先检查是否存在
            cursor.execute(
                "SELECT id FROM seen_items WHERE source_name=? AND item_type='page_change' AND unique_key=?",
                (source_name, unique_key)
            )
            exists = cursor.fetchone()
            
            if exists:
                # 更新现有记录
                cursor.execute("""
                    UPDATE seen_items 
                    SET content_hash=?, title=?, notified=0
                    WHERE source_name=? AND item_type='page_change' AND unique_key=?
                """, (new_hash, title, source_name, unique_key))
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO seen_items 
                    (source_name, item_type, unique_key, title, content_hash)
                    VALUES (?, 'page_change', ?, ?, ?)
                """, (source_name, unique_key, title, new_hash))
            
            conn.commit()
            logger.info(f"更新页面哈希：{source_name}")
            
        except sqlite3.Error as e:
            logger.error(f"更新页面哈希失败：{e}")
            raise
        finally:
            conn.close()
    
    def mark_as_notified(self, source_name: str, item_type: str, unique_key: str):
        """标记条目为已通知"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE seen_items 
                SET notified=1 
                WHERE source_name=? AND item_type=? AND unique_key=?
            """, (source_name, item_type, unique_key))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"标记已通知失败：{e}")
        finally:
            conn.close()
    
    def get_stats(self) -> dict:
        """获取数据库统计信息"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # 总条目数
            cursor.execute("SELECT COUNT(*) as count FROM seen_items")
            total = cursor.fetchone()['count']
            
            # 按类型统计
            cursor.execute("""
                SELECT item_type, COUNT(*) as count 
                FROM seen_items 
                GROUP BY item_type
            """)
            by_type = {row['item_type']: row['count'] for row in cursor.fetchall()}
            
            # 按来源统计
            cursor.execute("""
                SELECT source_name, COUNT(*) as count 
                FROM seen_items 
                GROUP BY source_name
            """)
            by_source = {row['source_name']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total': total,
                'by_type': by_type,
                'by_source': by_source
            }
            
        except sqlite3.Error as e:
            logger.error(f"获取统计信息失败：{e}")
            return {}
        finally:
            conn.close()
