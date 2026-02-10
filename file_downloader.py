"""
文件下载模块
用于从企业微信下载文件
"""
import os
import requests
import logging
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


class FileDownloader:
    """文件下载器"""

    def __init__(self, download_dir: str = "downloads"):
        """
        初始化文件下载器

        Args:
            download_dir: 文件下载目录
        """
        self.download_dir = download_dir
        self._ensure_download_dir()

    def _ensure_download_dir(self):
        """确保下载目录存在"""
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)
            logger.info(f"[文件下载器] 创建下载目录: {self.download_dir}")

    def download_file(self, file_url: str, filename: Optional[str] = None) -> Optional[str]:
        """
        下载文件

        Args:
            file_url: 文件 URL
            filename: 可选的文件名，如果不提供则自动生成

        Returns:
            下载后的文件路径，失败返回 None
        """
        try:
            logger.info(f"[文件下载器] 开始下载文件: {file_url}")

            # 下载文件
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()

            # 确定文件名
            if filename is None:
                # 尝试从 URL 或 Content-Disposition 获取文件名
                filename = self._extract_filename(response, file_url)

            # 生成唯一文件名
            file_ext = os.path.splitext(filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join(self.download_dir, unique_filename)

            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(response.content)

            file_size = len(response.content)
            logger.info(f"[文件下载器] 文件下载成功: {file_path} ({file_size} bytes)")

            return file_path

        except Exception as e:
            logger.error(f"[文件下载器] 下载文件失败: {e}")
            return None

    def _extract_filename(self, response: requests.Response, url: str) -> str:
        """
        从响应中提取文件名

        Args:
            response: HTTP 响应对象
            url: 文件 URL

        Returns:
            文件名
        """
        # 尝试从 Content-Disposition 获取
        content_disposition = response.headers.get('Content-Disposition', '')
        if 'filename=' in content_disposition:
            filename = content_disposition.split('filename=')[-1].strip('"')
            return filename

        # 尝试从 URL 获取
        filename = url.split('/')[-1]
        if filename:
            return filename

        # 默认文件名
        return "downloaded_file"

    def cleanup_file(self, file_path: str):
        """
        清理已下载的文件

        Args:
            file_path: 文件路径
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"[文件下载器] 文件已清理: {file_path}")
        except Exception as e:
            logger.error(f"[文件下载器] 清理文件失败: {e}")

    def cleanup_old_files(self, max_age_hours: int = 24):
        """
        清理旧文件

        Args:
            max_age_hours: 最大保留时间（小时）
        """
        try:
            import time
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600

            for filename in os.listdir(self.download_dir):
                file_path = os.path.join(self.download_dir, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        logger.info(f"[文件下载器] 清理旧文件: {filename}")

        except Exception as e:
            logger.error(f"[文件下载器] 清理旧文件失败: {e}")


# 全局文件下载器实例
file_downloader = FileDownloader()