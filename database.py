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
                        msgid TEXT,
                        message_type TEXT NOT NULL,
                        content TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user_sessions(user_id)
                    )
                """)

                # 检查是否需要添加 msgid 字段（兼容旧数据库）
                cursor.execute("PRAGMA table_info(messages)")
                columns = [column[1] for column in cursor.fetchall()]
                if 'msgid' not in columns:
                    cursor.execute("ALTER TABLE messages ADD COLUMN msgid TEXT")
                    conn.commit()
                    logger.info("[数据库] 已添加 msgid 字段到 messages 表")

                # 检查是否需要添加 media_id 字段（兼容旧数据库）
                if 'media_id' not in columns:
                    cursor.execute("ALTER TABLE messages ADD COLUMN media_id TEXT")
                    conn.commit()
                    logger.info("[数据库] 已添加 media_id 字段到 messages 表")

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

    def log_message(self, user_id: str, message_type: str, content: str = None, file_path: str = None, msgid: str = None, media_id: str = None):
        """
        记录消息

        Args:
            user_id: 用户 ID
            message_type: 消息类型（user_message/bot_message/image_message/file_message）
            content: 消息内容
            file_path: 文件路径（可选）
            msgid: 消息唯一标识（可选）
            media_id: 企业微信媒体文件 ID（可选）
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # 如果有文件路径，记录哈希文件名（用于后续查询完整路径）
                if file_path and message_type in ['image_message', 'file_message']:
                    import os
                    # 从文件路径中提取哈希文件名
                    hash_filename = os.path.basename(file_path)
                    # 如果是解密后的文件，去掉 _decrypted 后缀查询原始文件名
                    if '_decrypted' in hash_filename:
                        original_name = self.get_original_filename(hash_filename)
                        display_name = original_name if original_name else hash_filename
                    else:
                        display_name = hash_filename

                    # 记录格式：[文件: 显示名] [HASH: 哈希文件名]
                    file_info = f"[文件: {display_name}] [HASH: {hash_filename}]"
                    if content:
                        content = f"{content} | {file_info}"
                    else:
                        content = file_info

                cursor.execute("""
                    INSERT INTO messages (user_id, msgid, message_type, content, media_id)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, msgid, message_type, content, media_id))

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
                
                # 解析哈希文件名
                import re
                hash_match = re.search(r'\[HASH:\s*([^\]]+)\]', content)
                if not hash_match:
                    return None
                
                hash_filename = hash_match.group(1).strip()
                
                # 根据哈希文件名判断完整路径（使用用户独立目录）
                import os
                user_files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data', user_id, 'files')
                
                # 如果是 _decrypted 文件，使用解密后的路径；否则使用加密路径
                if '_decrypted' in hash_filename:
                    file_path = os.path.join(user_files_dir, hash_filename)
                else:
                    # 检查是否存在解密版本
                    decrypted_path = os.path.join(user_files_dir, hash_filename.replace(os.path.splitext(hash_filename)[0], os.path.splitext(hash_filename)[0] + '_decrypted' + os.path.splitext(hash_filename)[1]))
                    if os.path.exists(decrypted_path):
                        file_path = decrypted_path
                    else:
                        file_path = os.path.join(user_files_dir, hash_filename)
                
                # 判断文件类型
                file_ext = os.path.splitext(hash_filename)[1].lower()
                if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                    file_type = 'image'
                else:
                    file_type = 'file'
                
                # 获取原始文件名
                original_filename = self.get_original_filename(hash_filename)
                display_filename = original_filename if original_filename else hash_filename
                
                return {
                    'file_type': file_type,
                    'file_path': file_path,
                    'filename': display_filename,
                    'hash_filename': hash_filename,
                    'created_at': result[1]
                }
                
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
        获取所有文件映射（简化格式，用于用户查询）

        Args:
            user_id: 可选的用户 ID，如果提供则只返回该用户的文件

        Returns:
            文件列表，每个元素只包含 original_filename 和 file_type
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                if user_id:
                    cursor.execute("""
                        SELECT hash_filename, original_filename, last_seen
                        FROM file_mappings
                        WHERE user_id = ?
                        ORDER BY last_seen DESC
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT hash_filename, original_filename, last_seen
                        FROM file_mappings
                        ORDER BY last_seen DESC
                    """)

                files = []
                for row in cursor.fetchall():
                    hash_filename = row[0]
                    original_filename = row[1]

                    # 根据文件扩展名判断文件类型
                    import os
                    file_ext = os.path.splitext(hash_filename)[1].lower()
                    if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                        file_type = '图片'
                    elif file_ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                        file_type = '文档'
                    elif file_ext in ['.mp3', '.wav', '.ogg', '.m4a']:
                        file_type = '音频'
                    elif file_ext in ['.mp4', '.avi', '.mov', '.mkv']:
                        file_type = '视频'
                    else:
                        file_type = '文件'

                    files.append({
                        'filename': original_filename,
                        'type': file_type
                    })

                return files

        except Exception as e:
            logger.error(f"[数据库] 获取文件映射失败: {e}")
            return []


# 全局数据库管理器实例
db_manager = DatabaseManager()