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

    def log_message(self, user_id: str, message_type: str, content: str = None):
        """
        记录消息

        Args:
            user_id: 用户 ID
            message_type: 消息类型（user_message/bot_message）
            content: 消息内容
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
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


# 全局数据库管理器实例
db_manager = DatabaseManager()