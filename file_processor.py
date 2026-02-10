"""
文件处理模块
处理不同类型的文件，提取文本内容
"""
import os
import logging
from typing import Optional, Dict, Any
import asyncio

logger = logging.getLogger(__name__)


class FileProcessor:
    """文件处理器"""

    # 支持的文本文件类型
    TEXT_EXTENSIONS = {
        '.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml',
        '.yaml', '.yml', '.ini', '.cfg', '.conf', '.log', '.csv'
    }

    # 支持的文档文件类型
    DOCUMENT_EXTENSIONS = {
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'
    }

    def __init__(self):
        """初始化文件处理器"""
        logger.info("[文件处理器] 文件处理器初始化完成")

    async def process_file(self, file_path: str, file_type: str = "file") -> Dict[str, Any]:
        """
        处理文件，提取内容

        Args:
            file_path: 文件路径
            file_type: 文件类型 (file/image/voice)

        Returns:
            处理结果字典，包含:
            - success: 是否成功
            - content: 文件内容或描述
            - file_info: 文件信息
        """
        try:
            logger.info(f"[文件处理器] 开始处理文件: {file_path}, 类型: {file_type}")

            # 获取文件信息
            file_info = self._get_file_info(file_path)

            # 根据文件类型处理
            if file_type == "image":
                result = await self._process_image(file_path, file_info)
            elif file_type == "voice":
                result = await self._process_voice(file_path, file_info)
            else:
                result = await self._process_document(file_path, file_info)

            logger.info(f"[文件处理器] 文件处理完成: {result['success']}")
            return result

        except Exception as e:
            logger.error(f"[文件处理器] 处理文件失败: {e}")
            return {
                "success": False,
                "content": f"处理文件时出错: {str(e)}",
                "file_info": {}
            }

    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            文件信息字典
        """
        try:
            file_stat = os.stat(file_path)
            file_ext = os.path.splitext(file_path)[1].lower()

            return {
                "path": file_path,
                "name": os.path.basename(file_path),
                "size": file_stat.st_size,
                "extension": file_ext,
                "size_mb": round(file_stat.st_size / (1024 * 1024), 2)
            }
        except Exception as e:
            logger.error(f"[文件处理器] 获取文件信息失败: {e}")
            return {}

    async def _process_image(self, file_path: str, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理图片文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            处理结果
        """
        logger.info(f"[文件处理器] 处理图片文件: {file_info['name']}")

        # 对于图片，返回描述信息
        content = f"""
我收到了一张图片文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}

请帮我分析这张图片的内容。如果能读取图片内容，请描述图片中的信息。
"""

        return {
            "success": True,
            "content": content,
            "file_info": file_info
        }

    async def _process_voice(self, file_path: str, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理语音文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            处理结果
        """
        logger.info(f"[文件处理器] 处理语音文件: {file_info['name']}")

        # 对于语音，返回描述信息
        content = f"""
我收到了一个语音文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}

请帮我处理这个语音文件。如果能转换语音为文字，请提取语音内容。
"""

        return {
            "success": True,
            "content": content,
            "file_info": file_info
        }

    async def _process_document(self, file_path: str, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理文档文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            处理结果
        """
        logger.info(f"[文件处理器] 处理文档文件: {file_info['name']}")

        # 检查文件大小
        if file_info['size'] > 10 * 1024 * 1024:  # 10MB
            logger.warning(f"[文件处理器] 文件过大: {file_info['size_mb']} MB")
            content = f"""
我收到了一个文档文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}

文件较大（超过 10MB），可能需要分批处理。请告诉我你希望如何处理这个文件。
"""
            return {
                "success": True,
                "content": content,
                "file_info": file_info
            }

        # 根据文件扩展名处理
        file_ext = file_info.get('extension', '').lower()

        if file_ext in self.TEXT_EXTENSIONS:
            # 文本文件，直接读取
            content = await self._read_text_file(file_path, file_info)
        elif file_ext in self.DOCUMENT_EXTENSIONS:
            # 文档文件，尝试读取
            content = await self._read_document_file(file_path, file_info)
        else:
            # 其他文件类型
            content = await self._read_generic_file(file_path, file_info)

        return {
            "success": True,
            "content": content,
            "file_info": file_info
        }

    async def _read_text_file(self, file_path: str, file_info: Dict[str, Any]) -> str:
        """
        读取文本文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            文件内容
        """
        try:
            # 尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']

            for encoding in encodings:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()

                    # 限制内容长度
                    max_length = 100000  # 100k 字符
                    if len(content) > max_length:
                        content = content[:max_length]
                        content += f"\n\n[文件内容过长，已截断到 {max_length} 字符]"

                    logger.info(f"[文件处理器] 使用 {encoding} 编码读取文本文件成功")

                    # 添加文件信息前缀
                    prefix = f"""
我收到了一个文本文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}

文件内容如下：

---

"""
                    return prefix + content

                except UnicodeDecodeError:
                    continue

            # 所有编码都失败
            logger.error(f"[文件处理器] 无法解码文本文件")
            return f"无法读取文件 {file_info['name']}，编码不支持"

        except Exception as e:
            logger.error(f"[文件处理器] 读取文本文件失败: {e}")
            return f"读取文件时出错: {str(e)}"

    async def _read_document_file(self, file_path: str, file_info: Dict[str, Any]) -> str:
        """
        读取文档文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            文件内容描述
        """
        logger.info(f"[文件处理器] 尝试读取文档文件: {file_info['name']}")

        # 对于文档文件，返回描述信息，让 iFlow CLI 的工具来处理
        content = f"""
我收到了一个文档文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}
- 文件路径: {file_path}

请使用适当的工具读取这个文档文件的内容，并进行分析。
"""

        return content

    async def _read_generic_file(self, file_path: str, file_info: Dict[str, Any]) -> str:
        """
        读取通用文件

        Args:
            file_path: 文件路径
            file_info: 文件信息

        Returns:
            文件描述
        """
        logger.info(f"[文件处理器] 处理通用文件: {file_info['name']}")

        content = f"""
我收到了一个文件：

- 文件名: {file_info['name']}
- 文件大小: {file_info['size_mb']} MB
- 文件格式: {file_info['extension']}
- 文件路径: {file_path}

这是一个 {file_info['extension']} 类型的文件。请告诉我你希望如何处理这个文件。
"""

        return content


# 全局文件处理器实例
file_processor = FileProcessor()