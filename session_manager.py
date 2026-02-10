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

    async def get_or_create_session(self, user_id: str) -> object:
        """
        获取或创建用户会话

        Args:
            user_id: 用户 ID

        Returns:
            IFlowClient 实例
        """
        if user_id not in self.sessions:
            logger.info(f"[会话管理器] 为用户 {user_id} 创建新会话")
            session_id = await self._create_session(user_id)
            # 保存会话到数据库
            db_manager.save_user_session(user_id, session_id)
        else:
            logger.info(f"[会话管理器] 用户 {user_id} 会话已存在，复用现有会话")

        return self.sessions[user_id]

    async def _create_session(self, user_id: str) -> str:
        """
        创建新的用户会话

        Args:
            user_id: 用户 ID

        Returns:
            会话 ID
        """
        try:
            # 延迟导入，避免循环依赖
            from iflow_sdk import IFlowClient, IFlowOptions

            # 生成会话 ID
            session_id = f"wecom_user_{user_id}"

            # 为每个用户创建独立的会话配置
            options = IFlowOptions(
                session_id=session_id,
                auto_start_process=True
            )

            # 创建 IFlowClient 实例
            client = IFlowClient(options)
            self.sessions[user_id] = client

            logger.info(f"[会话管理器] 用户 {user_id} 会话创建成功，session_id: {session_id}")

            return session_id

        except Exception as e:
            logger.error(f"[会话管理器] 创建用户 {user_id} 会话失败: {e}")
            raise

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