"""
数据库管理
提供会话持久化功能
"""

import sqlite3
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: str = "wecom_bot.db"):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """初始化数据库表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 创建用户会话表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_sessions (
                        user_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        message_count INTEGER DEFAULT 0
                    )
                """)

                # 创建消息记录表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        message_type TEXT NOT NULL,
                        content TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user_sessions(user_id)
                    )
                """)

                # 创建文件映射表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS file_mappings (
                        hash_filename TEXT PRIMARY KEY,
                        original_filename TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                conn.commit()
                logger.info(f"[数据库] 数据库初始化成功: {self.db_path}")

        except Exception as e:
            logger.error(f"[数据库] 初始化失败: {e}")
            raise

    def save_user_session(self, user_id: str, session_id: str):
        """
        保存用户会话

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 检查会话是否存在
                cursor.execute(
                    "SELECT session_id FROM user_sessions WHERE user_id = ?",
                    (user_id,)
                )
                existing = cursor.fetchone()

                if existing:
                    # 更新最后活跃时间
                    cursor.execute("""
                        UPDATE user_sessions
                        SET last_active = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    """, (user_id,))
                else:
                    # 插入新会话
                    cursor.execute("""
                        INSERT INTO user_sessions (user_id, session_id)
                        VALUES (?, ?)
                    """, (user_id, session_id))

                conn.commit()
                logger.info(f"[数据库] 用户会话已保存: {user_id} -> {session_id}")

        except Exception as e:
            logger.error(f"[数据库] 保存用户会话失败: {e}")

    def get_user_session(self, user_id: str) -> Optional[str]:
        """
        获取用户会话 ID

        Args:
            user_id: 用户 ID

        Returns:
            会话 ID，如果不存在则返回 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT session_id FROM user_sessions WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()
                return result[0] if result else None

        except Exception as e:
            logger.error(f"[数据库] 获取用户会话失败: {e}")
            return None

    def log_message(self, user_id: str, message_type: str, content: str = None, file_path: str = None):
        """
        记录消息

        Args:
            user_id: 用户 ID
            message_type: 消息类型（user_message/bot_message/image_message/file_message）
            content: 消息内容
            file_path: 文件路径（可选）
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 如果有文件路径，将文件路径信息添加到内容中
                if file_path and message_type in ['image_message', 'file_message']:
                    import os
                    file_info = f"[文件路径: {file_path} | 文件名: {os.path.basename(file_path)}]"
                    if content:
                        content = f"{content} | {file_info}"
                    else:
                        content = file_info
                
                cursor.execute("""
                    INSERT INTO messages (user_id, message_type, content)
                    VALUES (?, ?, ?)
                """, (user_id, message_type, content))

                # 更新消息计数
                cursor.execute("""
                    UPDATE user_sessions
                    SET message_count = message_count + 1,
                        last_active = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (user_id,))

                conn.commit()
                logger.debug(f"[数据库] 消息已记录: {user_id} - {message_type}")

        except Exception as e:
            logger.error(f"[数据库] 记录消息失败: {e}")

    def get_recent_file_message(self, user_id: str) -> Optional[dict]:
        """
        获取用户最近的文件/图片消息（包含文件路径）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            文件信息字典，如果没有则返回 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT content, created_at
                    FROM messages
                    WHERE user_id = ? AND message_type IN ('image_message', 'file_message')
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                
                result = cursor.fetchone()
                if not result:
                    return None
                
                content = result[0]
                
                # 解析文件路径信息
                if '[文件路径:' in content:
                    import re
                    match = re.search(r'\[文件路径:\s*([^\|]+)\s*\|\s*文件名:\s*([^\]]+)\]', content)
                    if match:
                        file_path = match.group(1).strip()
                        filename = match.group(2).strip()
                        
                        # 判断文件类型
                        file_ext = os.path.splitext(filename)[1].lower()
                        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                            file_type = 'image'
                        else:
                            file_type = 'file'
                        
                        return {
                            'file_type': file_type,
                            'file_path': file_path,
                            'filename': filename,
                            'created_at': result[1]
                        }
                
                return None
                
        except Exception as e:
            logger.error(f"[数据库] 获取最近文件消息失败: {e}")
            return None

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计信息

        Args:
            user_id: 用户 ID

        Returns:
            用户统计信息字典
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 获取会话信息
                cursor.execute("""
                    SELECT session_id, created_at, last_active, message_count
                    FROM user_sessions
                    WHERE user_id = ?
                """, (user_id,))
                session = cursor.fetchone()

                # 获取消息总数
                cursor.execute("""
                    SELECT COUNT(*)
                    FROM messages
                    WHERE user_id = ?
                """, (user_id,))
                total_messages = cursor.fetchone()[0]

                if session:
                    return {
                        "user_id": user_id,
                        "session_id": session[0],
                        "created_at": session[1],
                        "last_active": session[2],
                        "message_count": session[3],
                        "total_messages": total_messages
                    }
                else:
                    return {
                        "user_id": user_id,
                        "session_id": None,
                        "created_at": None,
                        "last_active": None,
                        "message_count": 0,
                        "total_messages": 0
                    }

        except Exception as e:
            logger.error(f"[数据库] 获取用户统计失败: {e}")
            return {}

    def cleanup_old_sessions(self, days: int = 7):
        """
        清理旧会话

        Args:
            days: 保留天数
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_sessions
                    WHERE datetime(last_active) < datetime('now', '-' || ? || ' days')
                """, (days,))
                deleted_count = cursor.rowcount
                conn.commit()
                logger.info(f"[数据库] 清理了 {deleted_count} 个旧会话")

        except Exception as e:
            logger.error(f"[数据库] 清理旧会话失败: {e}")

    def save_file_mapping(self, hash_filename: str, original_filename: str, user_id: str):
        """
        保存文件映射关系

        Args:
            hash_filename: 哈希文件名
            original_filename: 原始文件名
            user_id: 用户 ID
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 检查映射是否已存在
                cursor.execute("""
                    SELECT original_filename FROM file_mappings
                    WHERE hash_filename = ?
                """, (hash_filename,))
                
                existing = cursor.fetchone()
                
                if existing:
                    # 更新最后访问时间
                    cursor.execute("""
                        UPDATE file_mappings
                        SET last_seen = CURRENT_TIMESTAMP
                        WHERE hash_filename = ?
                    """, (hash_filename,))
                else:
                    # 插入新映射
                    cursor.execute("""
                        INSERT INTO file_mappings (hash_filename, original_filename, user_id)
                        VALUES (?, ?, ?)
                    """, (hash_filename, original_filename, user_id))
                
                conn.commit()
                logger.debug(f"[数据库] 文件映射已保存: {hash_filename} -> {original_filename}")

        except Exception as e:
            logger.error(f"[数据库] 保存文件映射失败: {e}")

    def get_original_filename(self, hash_filename: str) -> Optional[str]:
        """
        获取原始文件名

        Args:
            hash_filename: 哈希文件名

        Returns:
            原始文件名，如果不存在则返回 None
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT original_filename FROM file_mappings
                    WHERE hash_filename = ?
                """, (hash_filename,))
                
                result = cursor.fetchone()
                return result[0] if result else None

        except Exception as e:
            logger.error(f"[数据库] 获取原始文件名失败: {e}")
            return None

    def get_all_file_mappings(self, user_id: str = None) -> list:
        """
        获取所有文件映射

        Args:
            user_id: 可选的用户 ID，如果提供则只返回该用户的文件

        Returns:
            文件映射列表，每个元素包含 hash_filename, original_filename, user_id, first_seen, last_seen
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if user_id:
                    cursor.execute("""
                        SELECT hash_filename, original_filename, user_id, first_seen, last_seen
                        FROM file_mappings
                        WHERE user_id = ?
                        ORDER BY last_seen DESC
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT hash_filename, original_filename, user_id, first_seen, last_seen
                        FROM file_mappings
                        ORDER BY last_seen DESC
                    """)
                
                mappings = []
                for row in cursor.fetchall():
                    mappings.append({
                        'hash_filename': row[0],
                        'original_filename': row[1],
                        'user_id': row[2],
                        'first_seen': row[3],
                        'last_seen': row[4]
                    })
                
                return mappings

        except Exception as e:
            logger.error(f"[数据库] 获取文件映射失败: {e}")
            return []


# 全局数据库管理器实例
db_manager = DatabaseManager()