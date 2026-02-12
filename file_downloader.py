"""
文件下载模块
用于从企业微信下载文件
"""
import os
import requests
import base64
from Crypto.Cipher import AES
import logging
from typing import Optional
import uuid
from WXBizJsonMsgCrypt import Prpcrypt
from database import db_manager

logger = logging.getLogger(__name__)


class FileDownloader:
    """文件下载器"""

    def __init__(self, download_dir: str = "downloads"):
        """
        初始化文件下载器

        Args:
            download_dir: 基础文件下载目录（用户目录会在此基础上创建）
        """
        # 使用 user_data/{user_id}/files/ 目录结构，保持与其他模块一致
        self.base_download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data')
        self._ensure_base_dir()

    def _ensure_base_dir(self):
        """确保基础下载目录存在"""
        if not os.path.exists(self.base_download_dir):
            os.makedirs(self.base_download_dir)
            logger.info(f"[文件下载器] 创建基础下载目录: {self.base_download_dir}")

    def _get_user_download_dir(self, user_id: str) -> str:
        """
        获取用户的下载目录

        Args:
            user_id: 用户 ID

        Returns:
            用户的下载目录路径
        """
        # 使用 user_data/{user_id}/files/ 目录
        user_files_dir = os.path.join(self.base_download_dir, user_id, 'files')
        if not os.path.exists(user_files_dir):
            os.makedirs(user_files_dir, exist_ok=True)
            logger.info(f"[文件下载器] 创建用户文件目录: {user_files_dir}")
        return user_files_dir

    def download_file(self, file_url: str, user_id: str = None, filename: Optional[str] = None, aes_key_base64: str = None) -> Optional[dict]:
        """
        下载文件

        Args:
            file_url: 文件 URL
            user_id: 用户 ID，用于指定保存到用户的目录
            filename: 可选的文件名，如果不提供则自动生成
            aes_key_base64: 可选的 AES 密钥，如果提供则自动解密文件

        Returns:
            包含 hash_path 和 original_filename 的字典，失败返回 None
        """
        try:
            # 确定下载目录
            if user_id:
                download_dir = self._get_user_download_dir(user_id)
            else:
                download_dir = self.base_download_dir

            logger.info(f"[文件下载器] 开始下载文件: {file_url}, 用户: {user_id}, 目录: {download_dir}")

            # 下载文件
            response = requests.get(file_url, timeout=30)
            response.raise_for_status()

            file_content = response.content

            # 计算文件内容的 SHA256 哈希
            import hashlib
            file_hash = hashlib.sha256(file_content).hexdigest()[:16]

            # 确定原始文件名
            if filename is None:
                # 尝试从 URL 或 Content-Disposition 获取文件名
                filename = self._extract_filename(response, file_url)

            # 生成基于哈希的文件名
            file_ext = os.path.splitext(filename)[1]
            hash_filename = f"{file_hash}{file_ext}"
            file_path = os.path.join(download_dir, hash_filename)

            # 检查文件是否已存在
            if os.path.exists(file_path):
                file_size = len(file_content)
                logger.info(f"[文件下载器] 文件已存在，复用现有文件: {file_path} ({file_size} bytes)")

                # 保存文件哈希（如果用户ID存在）
                if user_id:
                    db_manager.save_file_hash(user_id, file_hash, filename)

                # 如果存在解密版本，返回解密路径（绝对路径）
                decrypted_path = os.path.splitext(file_path)[0] + "_decrypted" + file_ext
                if os.path.exists(decrypted_path):
                    return {
                        'hash_path': os.path.abspath(decrypted_path),
                        'original_filename': filename,
                        'hash_filename': os.path.basename(decrypted_path),
                        'file_hash': file_hash
                    }
                
                # 如果只存在加密文件，尝试解密
                if aes_key_base64:
                    logger.info(f"[文件下载器] 检测到已存在的加密文件，尝试解密")
                    decrypted_path = self.decrypt_file(file_path, aes_key_base64)
                    if decrypted_path:
                        return {
                            'hash_path': os.path.abspath(decrypted_path),
                            'original_filename': filename,
                            'hash_filename': os.path.basename(decrypted_path),
                            'file_hash': file_hash
                        }

                return {
                    'hash_path': os.path.abspath(file_path),
                    'original_filename': filename,
                    'hash_filename': hash_filename,
                    'file_hash': file_hash
                }

            # 保存文件
            with open(file_path, 'wb') as f:
                f.write(file_content)

            file_size = len(file_content)
            logger.info(f"[文件下载器] 文件下载成功: {file_path} ({file_size} bytes)")

            # 检查文件是否需要解密
            final_path = file_path
            final_hash_filename = hash_filename

            # 检查文件头是否需要解密（企业微信的图片/文件都是加密的）
            if len(file_content) > 0:
                first_4_bytes = file_content[:4]
                # 检查是否是企业微信加密格式
                # 已知格式：
                # - 图片旧格式: f6 4d 2a 28
                # - 文件旧格式: 7b 1a 7a 03
                # - 图片新格式: 17 ef 79 e9
                # - 图片最新格式: 37 6a bc 6a
                if first_4_bytes == b'\xf6\x4d\x2a\x28' or first_4_bytes == b'\x7b\x1a\x7a\x03' or first_4_bytes == b'\x17\xef\x79\xe9' or first_4_bytes == b'\x37\x6a\xbc\x6a':
                    logger.info(f"[文件下载器] 检测到加密文件，尝试解密: {first_4_bytes.hex()}")

                    if aes_key_base64:
                        decrypted_path = self.decrypt_file(file_path, aes_key_base64)
                        if decrypted_path:
                            final_path = decrypted_path
                            final_hash_filename = os.path.basename(decrypted_path)
                            logger.info(f"[文件下载器] 文件解密成功: {final_path}")

            # 保存文件哈希（如果用户ID存在）
            if user_id:
                db_manager.save_file_hash(user_id, file_hash, filename)

            return {
                'hash_path': os.path.abspath(final_path),
                'original_filename': filename,
                'hash_filename': final_hash_filename,
                'file_hash': file_hash
            }

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

    def decrypt_file(self, file_path: str, aes_key_base64: str) -> Optional[str]:
        """
        解密加密的图片文件（企业微信图片需要解密）
        使用企业微信官方库的解密算法

        Args:
            file_path: 加密的文件路径
            aes_key_base64: Base64编码的AES密钥

        Returns:
            解密后的文件路径，失败返回 None
        """
        try:
            logger.info(f"[文件下载器] 开始解密文件: {file_path}")

            # 读取加密数据
            with open(file_path, 'rb') as f:
                encrypted_data = f.read()

            # 使用企业微信官方库的 Prpcrypt 类进行解密
            # 企业微信文件加密：纯文件内容 + PKCS#7 填充
            # 与消息加密不同，文件加密没有 random、msg_len、receiveid 封装

            # Base64解码密钥
            aes_key = base64.b64decode(aes_key_base64 + "=" * (-len(aes_key_base64) % 4))
            if len(aes_key) != 32:
                raise ValueError("无效的AES密钥长度: 应为32字节")

            # 使用 Prpcrypt 进行解密（企业微信官方算法）
            prpcrypt = Prpcrypt(aes_key)
            
            # 直接调用 AES-CBC 解密（不使用 Prpcrypt.decrypt，因为文件没有消息体封装）
            cryptor = AES.new(aes_key, AES.MODE_CBC, aes_key[:16])
            decrypted_data = cryptor.decrypt(encrypted_data)

            # 去除 PKCS#7 填充（与官方库相同的处理方式）
            pad_len = decrypted_data[-1]
            if pad_len > 32:
                raise ValueError("无效的填充长度")

            decrypted_data = decrypted_data[:-pad_len]

            # 根据文件头确定正确的扩展名
            # 常见文件魔数：
            # - JPEG: ffd8 ff
            # - PNG: 89 50 4e 47
            # - GIF: 47 49 46 38
            # - PDF: 25 50 44 46
            file_ext_map = {
                b'\xff\xd8\xff': '.jpg',
                b'\x89PNG': '.png',
                b'GIF8': '.gif',
                b'%PDF': '.pdf',
            }
            
            new_ext = None
            for magic, ext in file_ext_map.items():
                if decrypted_data.startswith(magic):
                    new_ext = ext
                    break
            
            # 如果无法识别，使用原扩展名
            if new_ext is None:
                new_ext = os.path.splitext(file_path)[1]

            # 保存解密后的文件
            original_filename = os.path.splitext(file_path)[0] + "_decrypted" + new_ext
            with open(original_filename, 'wb') as f:
                f.write(decrypted_data)

            logger.info(f"[文件下载器] 文件解密成功: {original_filename} (检测到扩展名: {new_ext})")
            return original_filename

        except Exception as e:
            logger.error(f"[文件下载器] 解密文件失败: {e}")
            return None

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

            for filename in os.listdir(self.base_download_dir):
                file_path = os.path.join(self.base_download_dir, filename)
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        logger.info(f"[文件下载器] 清理旧文件: {filename}")

        except Exception as e:
            logger.error(f"[文件下载器] 清理旧文件失败: {e}")


# 全局文件下载器实例
file_downloader = FileDownloader()