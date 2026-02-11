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
            from iflow_sdk.types import SessionSettings
            import os

            # 使用提供的 session_id 或生成新的
            if session_id is None:
                session_id = f"wecom_user_{user_id}"

            # 项目根目录（用于迁移兼容性）
            project_root = os.path.dirname(os.path.abspath(__file__))

            # 创建用户独立的目录结构
            base_dir = os.path.join(project_root, 'user_data', user_id)
            workspace_dir = os.path.join(base_dir, 'workspace')
            files_dir = os.path.join(base_dir, 'files')

            # 确保目录存在
            os.makedirs(workspace_dir, exist_ok=True)
            os.makedirs(files_dir, exist_ok=True)

            logger.info(f"[会话管理器] 用户 {user_id} 目录: workspace={workspace_dir}, files={files_dir}")

            # 系统提示词：禁止提及技术细节和环境信息
            system_prompt = """你是一个专业的AI助手。请严格遵循以下规则：

1. 在回复中只关注内容本身，不要提及任何技术细节
2. 绝对不要提及：文件格式、文件大小、文件路径、加密、解密、下载、AES密钥、哈希等技术术语
3. 不要解释如何获取、处理或传输文件
4. 当被问及上传了什么文件时，只列出文件名和内容主题
5. 保持回复自然，像正常对话一样
6. 即使看到文件名包含技术信息（如哈希值），也不要在回复中提及
7. 绝对不要从工作目录、项目结构、文件路径等环境信息推断用户的情况或项目信息
8. 不要提及用户的职业、工作内容或项目类型，除非用户明确告诉你

【重要原则】：除非用户在对话中明确提供信息，否则不要做任何关于用户身份、工作或项目的假设或推断。

【文件路径说明】当用户上传文件或引用文件时，消息中会包含 [FILE_PATH] 标记，该标记后面的路径是相对于项目根目录的相对路径（如 user_data/xxx/files/xxx.jpg），iFlow SDK 会自动解析为绝对路径。不要在回复中提及这个路径或 [FILE_PATH] 标记。"""

            # 创建会话设置
            session_settings = SessionSettings(system_prompt=system_prompt)

            # 为每个用户创建独立的会话配置
            # 使用项目根目录作为 cwd，便于迁移
            # 通过 file_allowed_dirs 允许访问用户的 files 目录（使用相对路径）
            # 相对路径会自动解析为绝对路径
            options = IFlowOptions(
                session_id=session_id,
                cwd=project_root,
                file_access=True,
                file_allowed_dirs=[f'user_data/{user_id}/files'],
                file_read_only=True,
                auto_start_process=True,
                session_settings=session_settings
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

    async def reset_user_session(self, user_id: str):
        """
        重置用户会话（关闭旧会话、删除会话历史文件、创建新会话）

        Args:
            user_id: 用户 ID
        """
        try:
            # 获取旧的 session_id
            old_session_id = db_manager.get_user_session(user_id)
            
            # 关闭旧会话
            if user_id in self.sessions:
                await self.close_session(user_id)
            
            # 删除 iFlow 会话历史文件
            if old_session_id:
                import os
                import shutil
                iflow_history_dir = os.path.expanduser(f"~/.iflow/history/{old_session_id}")
                if os.path.exists(iflow_history_dir):
                    try:
                        shutil.rmtree(iflow_history_dir)
                        logger.info(f"[会话管理器] 已删除 iFlow 会话历史: {iflow_history_dir}")
                    except Exception as e:
                        logger.error(f"[会话管理器] 删除 iFlow 会话历史失败: {e}")
            
            # 清除用户的文件信息
            self.clear_user_file(user_id)
            
            logger.info(f"[会话管理器] 用户 {user_id} 会话已重置")
            
        except Exception as e:
            logger.error(f"[会话管理器] 重置用户 {user_id} 会话失败: {e}")
            raise


# 全局会话管理器实例
session_manager = SessionManager()