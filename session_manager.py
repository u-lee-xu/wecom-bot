"""
会话管理器
管理多个用户的独立 iFlow CLI 会话
"""

import asyncio
from typing import Dict, Optional
import logging
from database import db_manager

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器，为每个用户维护独立的 iFlow CLI 会话"""

    def __init__(self):
        # 用户 ID 到 IFlowClient 的映射
        self.sessions: Dict[str, object] = {}
        # 用户 ID 到会话配置的映射
        self.session_configs: Dict[str, dict] = {}
        # 用户 ID 到最近文件路径的映射
        self.user_files: Dict[str, dict] = {}

    async def get_or_create_session(self, user_id: str) -> object:
        """
        获取或创建用户会话

        Args:
            user_id: 用户 ID

        Returns:
            IFlowClient 实例
        """
        if user_id not in self.sessions:
            # 先从数据库查找已有的 session_id
            existing_session_id = db_manager.get_user_session(user_id)
            
            if existing_session_id:
                logger.info(f"[会话管理器] 为用户 {user_id} 恢复历史会话: {existing_session_id}")
                session_id = await self._create_session(user_id, existing_session_id)
            else:
                logger.info(f"[会话管理器] 为用户 {user_id} 创建新会话")
                session_id = await self._create_session(user_id)
                # 保存会话到数据库
                db_manager.save_user_session(user_id, session_id)
        else:
            logger.info(f"[会话管理器] 用户 {user_id} 会话已存在，复用现有会话")

        return self.sessions[user_id]

    async def _create_session(self, user_id: str, session_id: str = None) -> str:
        """
        创建新的用户会话

        Args:
            user_id: 用户 ID
            session_id: 可选的会话 ID，如果不提供则生成新的

        Returns:
            会话 ID
        """
        try:
            # 延迟导入，避免循环依赖
            from iflow_sdk import IFlowClient, IFlowOptions

            # 使用提供的 session_id 或生成新的
            if session_id is None:
                session_id = f"wecom_user_{user_id}"

            # 为每个用户创建独立的会话配置
            options = IFlowOptions(
                session_id=session_id,
                auto_start_process=True
            )

            # 创建 IFlowClient 实例
            client = IFlowClient(options)
            
            # 建立连接
            await client.connect()
            
            self.sessions[user_id] = client

            logger.info(f"[会话管理器] 用户 {user_id} 会话创建成功，session_id: {session_id}")

            return session_id

        except Exception as e:
            logger.error(f"[会话管理器] 创建用户 {user_id} 会话失败: {e}")
            raise

    def save_user_file(self, user_id: str, file_type: str, file_path: str, original_filename: str = ""):
        """
        保存用户最近发送的文件信息

        Args:
            user_id: 用户 ID
            file_type: 文件类型（image/file）
            file_path: 文件路径
            original_filename: 原始文件名
        """
        import time
        self.user_files[user_id] = {
            'type': file_type,
            'path': file_path,
            'filename': original_filename,
            'timestamp': int(time.time())
        }
        logger.info(f"[会话管理器] 用户 {user_id} 文件已保存: {file_type} - {file_path}")

    def get_user_file(self, user_id: str) -> Optional[dict]:
        """
        获取用户最近发送的文件信息

        Args:
            user_id: 用户 ID

        Returns:
            文件信息字典，如果没有则返回 None
        """
        return self.user_files.get(user_id)

    def clear_user_file(self, user_id: str):
        """
        清除用户的文件信息

        Args:
            user_id: 用户 ID
        """
        if user_id in self.user_files:
            del self.user_files[user_id]
            logger.info(f"[会话管理器] 用户 {user_id} 文件信息已清除")

    async def close_session(self, user_id: str):
        """
        关闭用户会话

        Args:
            user_id: 用户 ID
        """
        if user_id in self.sessions:
            try:
                client = self.sessions[user_id]
                # 关闭连接
                if hasattr(client, '__aexit__'):
                    await client.__aexit__(None, None, None)
                del self.sessions[user_id]
                # 清除文件信息
                self.clear_user_file(user_id)
                logger.info(f"[会话管理器] 用户 {user_id} 会话已关闭")
            except Exception as e:
                logger.error(f"[会话管理器] 关闭用户 {user_id} 会话失败: {e}")

    async def close_all_sessions(self):
        """关闭所有会话"""
        logger.info(f"[会话管理器] 关闭所有会话，共 {len(self.sessions)} 个")
        for user_id in list(self.sessions.keys()):
            await self.close_session(user_id)

    def get_session_count(self) -> int:
        """获取当前会话数量"""
        return len(self.sessions)

    def has_session(self, user_id: str) -> bool:
        """检查用户是否有会话"""
        return user_id in self.sessions


# 全局会话管理器实例
session_manager = SessionManager()