"""
企业微信智能机器人主应用
"""

from flask import Flask, request
from WXBizJsonMsgCrypt import WXBizJsonMsgCrypt
import config
import json
import asyncio
import threading
import time
import os
import random
from session_manager import session_manager
from database import db_manager
from rate_limiter import rate_limiter
from file_downloader import file_downloader
from file_processor import file_processor
import logging

# 忙碌提示列表（随机选择）- 用于第二条及后续消息
_BUSY_MESSAGES = [
    "不好意思，我在忙，请稍后再试",
    "我还在处理上一条消息，请稍后再试",
]

# 处理中提示列表（随机选择）- 用于第一条消息
_PROCESSING_MESSAGES = [
    "收到，让我想想",
    "收到，正在处理中",
    "收到，稍等一下",
]

# 长时间处理提示列表（超过2分钟）
_LONG_WAIT_MESSAGES = [
    "任务比较复杂，请耐心等待",
    "正在深入分析，请稍候",
    "处理需要一些时间，请耐心等待",
]

def get_busy_message():
    """随机获取一个忙碌提示（第二条及后续消息）"""
    return random.choice(_BUSY_MESSAGES)

def get_processing_message():
    """随机获取一个处理中提示（第一条消息）"""
    return random.choice(_PROCESSING_MESSAGES)

def get_long_wait_message():
    """随机获取一个长等待提示（长时间运行的任务）"""
    return random.choice(_LONG_WAIT_MESSAGES)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 项目根目录（用于相对路径转换）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# 全局事件循环（用于所有异步操作）
_global_loop = None
_loop_lock = threading.Lock()

def to_relative_path(absolute_path: str) -> str:
    """
    将绝对路径转换为相对于项目根目录的相对路径
    
    Args:
        absolute_path: 绝对路径
        
    Returns:
        相对路径（如 user_data/XuLi/files/xxx.jpg）
    """
    try:
        # 转换为相对路径
        rel_path = os.path.relpath(absolute_path, PROJECT_ROOT)
        # 确保使用正斜杠（跨平台兼容）
        return rel_path.replace(os.sep, '/')
    except Exception as e:
        logger.error(f"[路径转换] 转换路径失败: {absolute_path}, 错误: {e}")
        return absolute_path

# 请求去重缓存（防止企业微信重试导致重复处理）
_request_cache = {}
_request_cache_lock = threading.Lock()

# 异步任务状态缓存
_task_status_cache = {}
_task_status_lock = threading.Lock()

# 消息内容去重缓存（防止短时间内重复发送相同消息）
_message_cache = {}
_message_cache_lock = threading.Lock()
_message_cache_ttl = 60  # 60秒内的相同消息视为重复

# 清理操作确认缓存（用于记录用户等待确认的清理操作）
_cleanup_confirm_cache = {}
_cleanup_confirm_lock = threading.Lock()
_cleanup_confirm_ttl = 300  # 5分钟内确认有效


def get_global_loop():
    """获取全局事件循环（单例）"""
    global _global_loop
    if _global_loop is None:
        with _loop_lock:
            if _global_loop is None:
                _global_loop = asyncio.new_event_loop()
                # 在新线程中运行事件循环
                def run_loop():
                    asyncio.set_event_loop(_global_loop)
                    _global_loop.run_forever()
                
                loop_thread = threading.Thread(target=run_loop, daemon=True)
                loop_thread.start()
    return _global_loop


def run_async(coro):
    """在全局事件循环中运行异步函数"""
    loop = get_global_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=300)  # 5分钟超时


def MakeTextStream(stream_id, content, finish):
    """
    生成文本流消息
    """
    plain = {
        "msgtype": "stream",
        "stream": {
            "id": stream_id,
            "finish": finish,
            "content": content
        }
    }
    return json.dumps(plain, ensure_ascii=False)


def extract_media_id(url: str) -> str:
    """
    从企业微信文件 URL 中提取 media_id

    Args:
        url: 企业微信文件 URL

    Returns:
        media_id 字符串，如果提取失败则返回 None
    """
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        
        # 首先尝试从查询参数中提取
        query_params = parse_qs(parsed.query)
        media_id = query_params.get('media_id', [None])[0]
        if media_id:
            return media_id
        
        # 如果查询参数中没有，尝试从路径中提取
        # 企业微信 URL 格式: https://ww-aibot-img-1258476243.cos.ap-guangzhou.myqcloud.com/yQQ1DwE/{media_id}?sign=...
        path_parts = parsed.path.strip('/').split('/')
        if path_parts:
            # media_id 通常是路径的最后一部分
            potential_media_id = path_parts[-1]
            # 验证是否为纯数字（企业微信的 media_id 通常是数字）
            if potential_media_id.isdigit():
                return potential_media_id
        
        return None
    except Exception as e:
        logger.error(f"[提取 media_id] 失败: {e}")
        return None


def EncryptMessage(receiveid, nonce, timestamp, stream):
    """
    加密消息（按照官方 demo 方式）
    """
    logger.info(f"[加密消息] receiveid={receiveid}, nonce={nonce}, timestamp={timestamp}")
    logger.debug(f"[加密消息] 发送流消息: {stream[:200]}...")

    wxcpt = WXBizJsonMsgCrypt(config.WECOM_TOKEN, config.WECOM_ENCODING_AES_KEY, receiveid)
    ret, resp = wxcpt.EncryptMsg(stream, nonce, timestamp)
    if ret != 0:
        logger.error(f"[加密消息] 加密失败，错误码: {ret}")
        return None

    stream_data = json.loads(stream)
    stream_id = stream_data['stream']['id']
    finish = stream_data['stream']['finish']
    logger.info(f"[加密消息] 回调处理完成, 返回加密的流消息, stream_id={stream_id}, finish={finish}")

    return resp


# 初始化加解密工具（延迟初始化，避免配置无效时无法启动）
wxcpt = None


def get_wxcpt():
    """获取加解密工具实例"""
    global wxcpt
    if wxcpt is None:
        # 智能机器人的 receiveid 是空字符串
        wxcpt = WXBizJsonMsgCrypt(
            config.WECOM_TOKEN,
            config.WECOM_ENCODING_AES_KEY,
            ''
        )
    return wxcpt


@app.route('/', methods=['GET', 'POST'])
def callback():
    """
    企业微信回调接口（根路径）
    GET: 验证 URL 有效性
    POST: 接收消息
    """
    if request.method == 'GET':
        return verify_url()
    else:
        return receive_message()

@app.route('/callback', methods=['GET', 'POST'])
def callback_route():
    """
    企业微信回调接口（/callback 路径）
    GET: 验证 URL 有效性
    POST: 接收消息
    """
    if request.method == 'GET':
        return verify_url()
    else:
        return receive_message()


def _execute_cleanup(user_id: str, cleanup_type: str) -> str:
    """
    执行清理操作

    Args:
        user_id: 用户 ID
        cleanup_type: 清理类型（file/image/all）

    Returns:
        清理结果消息
    """
    try:
        import sqlite3
        conn = sqlite3.connect(db_manager.db_path)
        cursor = conn.cursor()
        
        if cleanup_type == 'file':
            # 查询用户的所有非图片文件映射
            cursor.execute("""
                SELECT hash_filename FROM file_mappings 
                WHERE user_id = ? AND hash_filename NOT LIKE '%.jpg' 
                AND hash_filename NOT LIKE '%.jpeg' AND hash_filename NOT LIKE '%.png'
                AND hash_filename NOT LIKE '%.gif' AND hash_filename NOT LIKE '%.webp'
                AND hash_filename NOT LIKE '%.bmp'
            """, (user_id,))
            files_to_delete = [row[0] for row in cursor.fetchall()]
            
            # 软删除：移动文件到deleted目录
            import os
            import shutil
            user_files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data', user_id, 'files')
            deleted_dir = os.path.join(user_files_dir, 'deleted')
            os.makedirs(deleted_dir, exist_ok=True)
            
            deleted_count = 0
            for hash_filename in files_to_delete:
                # 标记文件为已删除（数据库）
                file_hash = os.path.splitext(hash_filename)[0].split('_')[0]
                if db_manager.mark_file_as_deleted(user_id, file_hash):
                    deleted_count += 1
                    logger.info(f"[清理操作] 已标记文件为已删除: {hash_filename}")
                
                # 移动加密文件到deleted目录
                encrypted_path = os.path.join(user_files_dir, hash_filename)
                if os.path.exists(encrypted_path):
                    try:
                        shutil.move(encrypted_path, os.path.join(deleted_dir, hash_filename))
                        logger.info(f"[清理操作] 已移动文件: {hash_filename}")
                    except Exception as e:
                        logger.error(f"[清理操作] 移动文件失败: {encrypted_path}, 错误: {e}")
                
                # 移动解密文件（如果存在）
                name, ext = os.path.splitext(hash_filename)
                decrypted_path = os.path.join(user_files_dir, f"{name}_decrypted{ext}")
                if os.path.exists(decrypted_path):
                    try:
                        shutil.move(decrypted_path, os.path.join(deleted_dir, f"{name}_decrypted{ext}"))
                        logger.info(f"[清理操作] 已移动文件: {name}_decrypted{ext}")
                    except Exception as e:
                        logger.error(f"[清理操作] 移动文件失败: {decrypted_path}, 错误: {e}")
            
            logger.info(f"[清理操作] 共标记 {deleted_count} 个文件为已删除")
            
            # 清理file_mappings表记录
            cursor.execute("""
                DELETE FROM file_mappings 
                WHERE user_id = ? AND hash_filename NOT LIKE '%.jpg' 
                AND hash_filename NOT LIKE '%.jpeg' AND hash_filename NOT LIKE '%.png'
                AND hash_filename NOT LIKE '%.gif' AND hash_filename NOT LIKE '%.webp'
                AND hash_filename NOT LIKE '%.bmp'
            """, (user_id,))
            conn.commit()
            conn.close()
            logger.info(f"[清理操作] 用户 {user_id} 的文件记录已清理")
            return "您的文件记录已清理完成。"
        
        elif cleanup_type == 'image':
            # 查询用户的所有图片文件映射
            cursor.execute("""
                SELECT hash_filename FROM file_mappings 
                WHERE user_id = ? AND (hash_filename LIKE '%.jpg' 
                OR hash_filename LIKE '%.jpeg' OR hash_filename LIKE '%.png'
                OR hash_filename LIKE '%.gif' OR hash_filename LIKE '%.webp'
                OR hash_filename LIKE '%.bmp')
            """, (user_id,))
            files_to_delete = [row[0] for row in cursor.fetchall()]
            
            # 软删除：移动文件到deleted目录
            import os
            import shutil
            user_files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data', user_id, 'files')
            deleted_dir = os.path.join(user_files_dir, 'deleted')
            os.makedirs(deleted_dir, exist_ok=True)
            
            deleted_count = 0
            for hash_filename in files_to_delete:
                # 标记文件为已删除（数据库）
                file_hash = os.path.splitext(hash_filename)[0].split('_')[0]
                if db_manager.mark_file_as_deleted(user_id, file_hash):
                    deleted_count += 1
                    logger.info(f"[清理操作] 已标记文件为已删除: {hash_filename}")
                
                # 移动加密文件到deleted目录
                encrypted_path = os.path.join(user_files_dir, hash_filename)
                if os.path.exists(encrypted_path):
                    try:
                        shutil.move(encrypted_path, os.path.join(deleted_dir, hash_filename))
                        logger.info(f"[清理操作] 已移动文件: {hash_filename}")
                    except Exception as e:
                        logger.error(f"[清理操作] 移动文件失败: {encrypted_path}, 错误: {e}")
                
                # 移动解密文件（如果存在）
                name, ext = os.path.splitext(hash_filename)
                decrypted_path = os.path.join(user_files_dir, f"{name}_decrypted{ext}")
                if os.path.exists(decrypted_path):
                    try:
                        shutil.move(decrypted_path, os.path.join(deleted_dir, f"{name}_decrypted{ext}"))
                        logger.info(f"[清理操作] 已移动文件: {name}_decrypted{ext}")
                    except Exception as e:
                        logger.error(f"[清理操作] 移动文件失败: {decrypted_path}, 错误: {e}")
            
            logger.info(f"[清理操作] 共标记 {deleted_count} 个文件为已删除")
            
            # 清理file_mappings表记录
            cursor.execute("""
                DELETE FROM file_mappings 
                WHERE user_id = ? AND (hash_filename LIKE '%.jpg' 
                OR hash_filename LIKE '%.jpeg' OR hash_filename LIKE '%.png'
                OR hash_filename LIKE '%.gif' OR hash_filename LIKE '%.webp'
                OR hash_filename LIKE '%.bmp')
            """, (user_id,))
            conn.commit()
            conn.close()
            
            # 清理用户的文件信息
            session_manager.clear_user_file(user_id)
            
            logger.info(f"[清理操作] 用户 {user_id} 的图片记录已清理")
            return "您的图片记录已清理完成。"
        
        elif cleanup_type == 'all':
            # 查询用户的所有文件映射（用于清理磁盘文件）
            cursor.execute('SELECT hash_filename FROM file_mappings WHERE user_id = ?', (user_id,))
            files_to_delete = [row[0] for row in cursor.fetchall()]
            
            # 清理磁盘文件（使用用户独立的文件目录）
            import os
            user_files_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data', user_id, 'files')
            deleted_count = 0
            for hash_filename in files_to_delete:
                # 删除加密文件
                encrypted_path = os.path.join(user_files_dir, hash_filename)
                if os.path.exists(encrypted_path):
                    try:
                        os.remove(encrypted_path)
                        deleted_count += 1
                        logger.info(f"[清理操作] 已删除文件: {encrypted_path}")
                    except Exception as e:
                        logger.error(f"[清理操作] 删除文件失败: {encrypted_path}, 错误: {e}")
                
                # 删除解密文件（如果存在）
                name, ext = os.path.splitext(hash_filename)
                decrypted_path = os.path.join(user_files_dir, f"{name}_decrypted{ext}")
                if os.path.exists(decrypted_path):
                    try:
                        os.remove(decrypted_path)
                        deleted_count += 1
                        logger.info(f"[清理操作] 已删除文件: {decrypted_path}")
                    except Exception as e:
                        logger.error(f"[清理操作] 删除文件失败: {decrypted_path}, 错误: {e}")
            
            logger.info(f"[清理操作] 共删除 {deleted_count} 个磁盘文件")
            
            # 清理数据库记录
            cursor.execute('DELETE FROM user_sessions WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM messages WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM file_mappings WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM file_hashes WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            
            # 清理用户的文件信息
            session_manager.clear_user_file(user_id)
            
            # 重置 iFlow 会话（关闭旧会话、删除会话历史、创建新会话）
            try:
                run_async(session_manager.reset_user_session(user_id))
                logger.info(f"[清理操作] 用户 {user_id} 的 iFlow 会话已重置")
            except Exception as e:
                logger.error(f"[清理操作] 重置 iFlow 会话失败: {e}")
            
            # 删除整个用户目录（包括 workspace 和 files）
            user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_data', user_id)
            if os.path.exists(user_data_dir):
                try:
                    import shutil
                    shutil.rmtree(user_data_dir)
                    logger.info(f"[清理操作] 已删除用户目录: {user_data_dir}")
                except Exception as e:
                    logger.error(f"[清理操作] 删除用户目录失败: {user_data_dir}, 错误: {e}")
            
            logger.info(f"[清理操作] 用户 {user_id} 的对话记录已清理")
            return "您的对话记录已清理完成。"
        
        else:
            return "未知的清理类型。"
    
    except Exception as e:
        logger.error(f"[清理操作] 清理失败: {e}")
        return f"清理失败: {str(e)}"


def verify_url():
    """
    验证 URL 有效性
    """
    msg_signature = request.args.get('msg_signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = request.args.get('echostr', '')

    logger.info(f"[验证URL] msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}, echostr={echostr}")

    try:
        # 解密 echostr 并返回
        ret, sEchoStr = get_wxcpt().VerifyURL(msg_signature, timestamp, nonce, echostr)
        if ret == 0:
            logger.info(f"[验证URL] 成功: {sEchoStr}")
            return sEchoStr
        else:
            logger.warning(f"[验证URL] 失败: ret={ret}")
            return "验证失败", 400
    except Exception as e:
        logger.error(f"[验证URL] 异常: {e}")
        return "验证异常", 500


def receive_message():
    """
    接收消息并返回加密的 stream 回复
    """
    try:
        # 获取加密消息
        data = request.get_data(as_text=True)
        logger.debug(f"[接收消息] 原始数据: {data[:200]}...")

        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')

        # 生成请求唯一标识（用于去重）
        request_key = f"{user_id}:{timestamp}:{nonce}" if 'user_id' in locals() else f"{timestamp}:{nonce}"

        # 检查是否已处理过此请求（去重）
        with _request_cache_lock:
            if request_key in _request_cache:
                logger.info(f"[接收消息] 检测到重复请求，直接返回缓存结果")
                return _request_cache[request_key]

        # 解密消息
        ret, decrypted_msg = get_wxcpt().DecryptMsg(data, msg_signature, timestamp, nonce)
        if ret == 0:
            logger.info(f"[接收消息] 解密成功")

            # 解析 JSON 消息
            message_data = json.loads(decrypted_msg)

            # 打印完整的消息结构（用于调试）
            logger.info(f"[接收消息] 完整消息结构: {json.dumps(message_data, ensure_ascii=False)}")

            # 提取消息信息
            user_id = message_data.get('from', {}).get('userid', '')
            response_url = message_data.get('response_url', '')
            msg_type = message_data.get('msgtype', '')
            msgid = message_data.get('msgid', '')  # 提取消息唯一标识

            # 检查是否有引用信息
            quoted_msg_id = message_data.get('quoted_msg_id', None)
            if quoted_msg_id:
                logger.info(f"[接收消息] 检测到引用消息: {quoted_msg_id}")

            logger.info(f"[接收消息] 用户ID: {user_id}, 消息类型: {msg_type}, msgid: {msgid}")

            # 重新生成请求唯一标识
            request_key = f"{user_id}:{timestamp}:{nonce}"

            # 再次检查是否已处理过此请求（去重）
            with _request_cache_lock:
                if request_key in _request_cache:
                    logger.info(f"[接收消息] 检测到重复请求，直接返回缓存结果")
                    return _request_cache[request_key]

            # 智能机器人的 receiveid 是空串
            receiveid = ''

            # 限流保护（只对用户主动发送的消息进行限流，stream 消息除外）
            if msg_type != 'stream':
                allowed, wait_time = rate_limiter.is_allowed(user_id)
                if not allowed:
                    logger.warning(f"[限流] 用户 {user_id} 超过限制，拒绝处理")
                    # 返回限流提示消息
                    error_message = f"您的请求过于频繁，请 {wait_time} 秒后再试。"
                    stream_id = str(int(time.time()))
                    stream = MakeTextStream(stream_id, error_message, True)
                    encrypted_resp = EncryptMessage('', nonce, timestamp, stream)
                    
                    # 缓存结果
                    with _request_cache_lock:
                        _request_cache[request_key] = encrypted_resp
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

            # 根据消息类型处理
            if msg_type == 'text':
                # 处理文本消息
                text_content = message_data.get('text', {}).get('content', '')
                logger.info(f"[接收消息] 文本内容: {text_content}")

                # 去除 @机器人 的提及（如果有）
                if '@' in text_content:
                    text_content = text_content.split(maxsplit=1)[-1] if len(text_content.split()) > 1 else text_content

                # 检查是否有引用消息中的图片
                quoted_image_url = None
                quoted_file_url = None
                quote_data = message_data.get('quote', {})
                if quote_data:
                    logger.info(f"[接收消息] 检测到引用消息: {quote_data}")
                    if quote_data.get('msgtype') == 'image':
                        quoted_image_url = quote_data.get('image', {}).get('url', '')
                        logger.info(f"[接收消息] 引用中的图片 URL: {quoted_image_url}")
                    elif quote_data.get('msgtype') == 'file':
                        quoted_file_url = quote_data.get('file', {}).get('url', '')
                        logger.info(f"[接收消息] 引用中的文件 URL: {quoted_file_url}")
                    
                    # 注意：企业微信的 quote 对象不包含 msgid，所以我们无法精确验证引用
                    # 对于文件/图片引用，我们通过 URL + user_id 验证
                    # 对于文本引用，我们允许直接引用（因为不涉及文件访问）

                # 如果有引用的图片，直接下载并验证（引用同一张图片时media_id会变化）
                quoted_image_path = None
                if quoted_image_url:
                    # 直接下载引用的图片
                    download_result = file_downloader.download_file(quoted_image_url, user_id=user_id, aes_key_base64=config.WECOM_ENCODING_AES_KEY)
                    
                    if download_result:
                        file_hash = download_result.get('file_hash')
                        if file_hash:
                            # 检查文件是否存在于用户的file_hashes表中且未被删除
                            hash_status = db_manager.get_file_hash_status(user_id, file_hash)
                            if not hash_status or hash_status['is_deleted']:
                                logger.error(f"[接收消息] 引用的图片不存在或已被删除（file_hash: {file_hash}）")
                                stream_id = str(int(time.time()))
                                error_message = "您引用的文件已被清理，请重新发送"
                                stream = MakeTextStream(stream_id, error_message, True)
                                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                                if encrypted_resp:
                                    return encrypted_resp
                                return "success"
                        
                        # 验证通过，处理文件
                        final_path = download_result['hash_path']
                        original_filename = download_result['original_filename']
                        hash_filename = download_result['hash_filename']

                        # 保存文件映射关系
                        db_manager.save_file_mapping(hash_filename, original_filename, user_id)

                        # 保存文件路径到会话
                        session_manager.save_user_file(user_id, 'image', final_path, original_filename)

                        # 记录图片消息
                        quoted_media_id = extract_media_id(quoted_image_url)
                        db_manager.log_message(user_id, "image_message", f"引用图片: {quoted_image_url}", final_path, msgid=msgid, media_id=quoted_media_id)

                        quoted_image_path = final_path
                        logger.info(f"[接收消息] 引用图片已保存: {download_result}")
                    else:
                        logger.error(f"[接收消息] 下载引用图片失败: {quoted_image_url}")
                        stream_id = str(int(time.time()))
                        error_message = "您引用的消息不存在，请重新发送"
                        stream = MakeTextStream(stream_id, error_message, True)
                        encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                        if encrypted_resp:
                            return encrypted_resp
                        return "success"

                # 如果有引用的文件，直接下载并验证（引用同一文件时media_id会变化）
                quoted_file_path = None
                if quoted_file_url:
                    # 直接下载引用的文件
                    download_result = file_downloader.download_file(quoted_file_url, user_id=user_id, aes_key_base64=config.WECOM_ENCODING_AES_KEY)
                    
                    if download_result:
                        file_hash = download_result.get('file_hash')
                        if file_hash:
                            # 检查文件是否存在于用户的file_hashes表中且未被删除
                            hash_status = db_manager.get_file_hash_status(user_id, file_hash)
                            if not hash_status or hash_status['is_deleted']:
                                logger.error(f"[接收消息] 引用的文件不存在或已被删除（file_hash: {file_hash}）")
                                stream_id = str(int(time.time()))
                                error_message = "您引用的文件已被清理，请重新发送"
                                stream = MakeTextStream(stream_id, error_message, True)
                                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                                if encrypted_resp:
                                    return encrypted_resp
                                return "success"
                        
                        # 验证通过，处理文件
                        final_path = download_result['hash_path']
                        original_filename = download_result['original_filename']
                        hash_filename = download_result['hash_filename']

                        # 保存文件映射关系
                        db_manager.save_file_mapping(hash_filename, original_filename, user_id)

                        # 保存文件路径到会话
                        session_manager.save_user_file(user_id, 'file', final_path, original_filename)

                        # 记录文件消息
                        quoted_media_id = extract_media_id(quoted_file_url)
                        db_manager.log_message(user_id, "file_message", f"引用文件: {quoted_file_url}", final_path, msgid=msgid, media_id=quoted_media_id)

                        quoted_file_path = final_path
                        logger.info(f"[接收消息] 引用文件已保存: {download_result}")
                    else:
                        logger.error(f"[接收消息] 下载引用文件失败: {quoted_file_url}")
                        stream_id = str(int(time.time()))
                        error_message = "您引用的消息不存在，请重新发送"
                        stream = MakeTextStream(stream_id, error_message, True)
                        encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                        if encrypted_resp:
                            return encrypted_resp
                        return "success"

                # 检查是否是清理命令（支持模糊匹配）
                stripped_content = text_content.strip().lower()
                current_time = int(time.time())
                
                # 优先检查是否有待确认的清理操作
                with _cleanup_confirm_lock:
                    if user_id in _cleanup_confirm_cache:
                        confirm_data = _cleanup_confirm_cache[user_id]
                        # 检查是否超时
                        if current_time - confirm_data['timestamp'] > _cleanup_confirm_ttl:
                            del _cleanup_confirm_cache[user_id]
                            logger.info(f"[接收消息] 用户 {user_id} 的清理操作已超时")
                        else:
                            # 在待确认状态中
                            if stripped_content in ['确认', 'yes']:
                                # 执行清理操作
                                cleanup_type = confirm_data['type']
                                del _cleanup_confirm_cache[user_id]
                                
                                logger.info(f"[接收消息] 用户 {user_id} 确认执行清理: {cleanup_type}")
                                
                                # 执行清理
                                reply_message = _execute_cleanup(user_id, cleanup_type)
                                
                                stream_id = str(int(time.time()))
                                stream = MakeTextStream(stream_id, reply_message, True)
                                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                                if encrypted_resp:
                                    return encrypted_resp
                                return "success"
                            elif stripped_content in ['取消', 'cancel']:
                                # 取消清理操作
                                del _cleanup_confirm_cache[user_id]
                                logger.info(f"[接收消息] 用户 {user_id} 取消清理操作")
                                
                                reply_message = "已取消清理操作"
                                stream_id = str(int(time.time()))
                                stream = MakeTextStream(stream_id, reply_message, True)
                                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                                if encrypted_resp:
                                    return encrypted_resp
                                return "success"
                            else:
                                # 其他任何回复都自动取消确认状态
                                del _cleanup_confirm_cache[user_id]
                                logger.info(f"[接收消息] 用户 {user_id} 发送其他消息，自动取消清理操作")
                                
                                # 继续当作普通消息处理，不做返回
                
                # 检查是否是清理指令
                if '清理' in stripped_content or '清空' in stripped_content:
                    cleanup_type = None
                    
                    # 判断清理类型
                    if '文件' in stripped_content or '文档' in stripped_content:
                        cleanup_type = 'file'
                        confirm_message = "确认要清理所有文件记录（非图片）吗？\n\n请回复：确认 或 yes（其他任何回复都将自动取消）"
                    elif '图片' in stripped_content or '照片' in stripped_content:
                        cleanup_type = 'image'
                        confirm_message = "确认要清理所有图片记录吗？\n\n请回复：确认 或 yes（其他任何回复都将自动取消）"
                    elif '对话' in stripped_content or '记录' in stripped_content or '历史' in stripped_content or '会话' in stripped_content:
                        cleanup_type = 'all'
                        confirm_message = "确认要清理所有对话记录吗？\n\n请回复：确认 或 yes（其他任何回复都将自动取消）"
                    else:
                        # 只有"清理"或"清空"，默认清理所有
                        cleanup_type = 'all'
                        confirm_message = "确认要清理所有对话记录吗？\n\n请回复：确认 或 yes（其他任何回复都将自动取消）"
                    
                    # 保存确认状态
                    with _cleanup_confirm_lock:
                        _cleanup_confirm_cache[user_id] = {
                            'type': cleanup_type,
                            'timestamp': current_time
                        }
                    
                    logger.info(f"[接收消息] 用户 {user_id} 请求清理: {cleanup_type}，等待确认")
                    
                    stream_id = str(int(time.time()))
                    stream = MakeTextStream(stream_id, confirm_message, True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

                # 记录用户消息
                db_manager.log_message(user_id, "user_message", text_content, msgid=msgid)

                # 附加文件信息到消息（优先使用引用的文件/图片）
                if quoted_image_path:
                    # 使用引用的图片
                    hash_filename = os.path.basename(quoted_image_path)
                    original_filename = db_manager.get_original_filename(hash_filename)

                    if original_filename:
                        display_filename = original_filename
                    else:
                        display_filename = hash_filename

                    # 转换为相对路径（便于迁移）
                    relative_path = to_relative_path(quoted_image_path)
                    
                    # 添加隐藏的文件路径标记，让 AI 能找到文件
                    file_info = f"\n\n[引用图片] {display_filename}\n[FILE_PATH] {relative_path}"
                    text_content_with_file = text_content + file_info
                    logger.info(f"[接收消息] 附加引用图片信息到消息: {relative_path}")
                elif quoted_file_path:
                    # 使用引用的文件
                    hash_filename = os.path.basename(quoted_file_path)
                    original_filename = db_manager.get_original_filename(hash_filename)

                    if original_filename:
                        display_filename = original_filename
                    else:
                        display_filename = hash_filename

                    # 转换为相对路径（便于迁移）
                    relative_path = to_relative_path(quoted_file_path)
                    
                    # 添加隐藏的文件路径标记，让 AI 能找到文件
                    file_info = f"\n\n[引用文件] {display_filename}\n[FILE_PATH] {relative_path}"
                    text_content_with_file = text_content + file_info
                    logger.info(f"[接收消息] 附加引用文件信息到消息: {relative_path}")
                else:
                    # 检测是否是命令式文件操作语言
                    # 只有用户明确要求对文件进行操作时，才自动附加最新文件
                    file_command_keywords = [
                        '分析', '总结', '写写', '描述', '说明', '解释', '翻译',
                        '提取', '识别', '读取', '查看', '检查', '对比',
                        '生成', '创建', '修改', '编辑', '处理', '转换',
                        '计算', '统计', '归纳', '概括', '列举', '找出'
                    ]
                    
                    should_attach_file = False
                    for keyword in file_command_keywords:
                        if keyword in text_content:
                            should_attach_file = True
                            break
                    
                    if should_attach_file:
                        # 查询数据库中最新的文件（用户用命令式语言要求操作文件）
                        recent_file = db_manager.get_recent_file_message(user_id)
                        if recent_file:
                            file_path = recent_file['file_path']
                            hash_filename = os.path.basename(file_path)
                            
                            # 尝试获取原始文件名
                            original_filename = db_manager.get_original_filename(hash_filename)
                            
                            if original_filename:
                                display_filename = original_filename
                            else:
                                display_filename = hash_filename

                            # 转换为相对路径（便于迁移）
                            relative_path = to_relative_path(file_path)
                            
                            # 添加隐藏的文件路径标记，让 AI 能找到文件
                            file_info = f"\n\n[文件] {display_filename}\n[FILE_PATH] {relative_path}"
                            text_content_with_file = text_content + file_info
                            logger.info(f"[接收消息] 检测到文件操作命令，附加文件信息到消息: {relative_path}")
                        else:
                            text_content_with_file = text_content
                    else:
                        # 用户没有用命令式语言，不自动附加文件
                        text_content_with_file = text_content
                        logger.info(f"[接收消息] 用户未使用命令式文件操作语言，不自动附加文件")

                # 消息内容去重（60秒内相同消息不重复处理）
                message_key = f"{user_id}:{text_content}"
                current_time = int(time.time())
                
                with _message_cache_lock:
                    if message_key in _message_cache:
                        last_time = _message_cache[message_key]
                        if current_time - last_time < _message_cache_ttl:
                            logger.info(f"[接收消息] 检测到重复消息（60秒内），忽略处理")
                            # 返回空响应
                            return "success"
                    # 更新消息时间戳
                    _message_cache[message_key] = current_time
                    
                    # 清理过期的消息缓存
                    expired_keys = [k for k, t in _message_cache.items() if current_time - t > _message_cache_ttl]
                    for key in expired_keys:
                        del _message_cache[key]

                # 同步处理消息并返回回复
                # 检查是否已经有后台任务在处理
                # 使用 user_id 作为 key，假设每个用户同时只有一个任务
                task_key = user_id
                
                if task_key in _task_status_cache:
                    # 已有后台任务在处理，返回"正在处理"
                    # 使用任务中存储的 stream_id
                    stream_id = _task_status_cache[task_key]['stream_id']
                    stream = MakeTextStream(stream_id, get_busy_message(), False)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    
                    with _request_cache_lock:
                        _request_cache[request_key] = encrypted_resp
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"
                
                # 没有后台任务，开始处理
                # 生成固定的 stream_id（基于用户和时间）
                stream_id = f"{user_id}_{int(time.time())}"
                
                # 标记任务开始处理
                with _task_status_lock:
                    _task_status_cache[task_key] = {
                        'status': 'processing',
                        'result': None,
                        'user_id': user_id,
                        'text_content': text_content,
                        'stream_id': stream_id,
                        'created_at': int(time.time())
                    }
                
                # 后台异步处理（不阻塞响应）
                def process_in_background():
                    try:
                        reply_content = run_async(process_message_and_get_reply(user_id, text_content_with_file))
                        
                        with _task_status_lock:
                            if task_key in _task_status_cache:
                                _task_status_cache[task_key]['status'] = 'completed'
                                _task_status_cache[task_key]['result'] = reply_content
                    except Exception as e:
                        logger.error(f"[后台处理] 异步处理失败: {e}")
                        import traceback
                        logger.error(f"[后台处理] 错误堆栈:\n{traceback.format_exc()}")
                        with _task_status_lock:
                            if task_key in _task_status_cache:
                                _task_status_cache[task_key]['status'] = 'error'
                                _task_status_cache[task_key]['result'] = f"处理失败: {str(e) if str(e) else '未知错误'}"
                
                # 启动后台处理线程
                threading.Thread(target=process_in_background, daemon=True).start()
                
                # 立即返回"处理中"的消息（不等待）- 使用 processing message
                stream = MakeTextStream(stream_id, get_processing_message(), False)
                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                
                with _request_cache_lock:
                    _request_cache[request_key] = encrypted_resp
                
                if encrypted_resp:
                    return encrypted_resp
                return "success"

            elif msg_type == 'stream':
                # 处理流消息（企业微信询问最新回复）
                stream_id = message_data.get('stream', {}).get('id', '')
                logger.info(f"[接收消息] 收到 stream 消息，stream_id={stream_id}")
                
                # 清理过期任务（超过5分钟未完成的任务）
                current_time = int(time.time())
                expired_tasks = []
                with _task_status_lock:
                    for key, task in list(_task_status_cache.items()):
                        if current_time - task.get('created_at', 0) > 300:  # 5分钟
                            expired_tasks.append(key)
                    for key in expired_tasks:
                        del _task_status_cache[key]
                
                # 使用 user_id 作为 key，假设每个用户同时只有一个任务
                task_key = user_id
                
                with _task_status_lock:
                    if task_key in _task_status_cache:
                        task = _task_status_cache[task_key]
                        # 使用任务中存储的 stream_id
                        stream_id = task['stream_id']
                        
                        if task['status'] == 'completed':
                            # 返回完成的结果
                            logger.info(f"[接收消息] 返回完成的结果")
                            stream = MakeTextStream(stream_id, task['result'], True)
                            encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                            
                            # 清理缓存
                            del _task_status_cache[task_key]
                            
                            if encrypted_resp:
                                return encrypted_resp
                            return "success"
                        elif task['status'] == 'error':
                            # 返回错误信息
                            logger.info(f"[接收消息] 返回错误信息")
                            stream = MakeTextStream(stream_id, task['result'], True)
                            encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                            
                            del _task_status_cache[task_key]
                            
                            if encrypted_resp:
                                return encrypted_resp
                            return "success"
                        else:
                            # 还在处理中，返回当前累积的内容（流式）
                            accumulated_text = task.get('result') or ''
                            
                            # 检查任务运行时间
                            current_time = int(time.time())
                            elapsed_time = current_time - task.get('created_at', current_time)
                            
                            # 根据运行时间选择提示消息
                            if elapsed_time > 120 and not accumulated_text:
                                # 超过2分钟且没有累积内容，使用长等待消息
                                message = get_long_wait_message()
                                logger.info(f"[接收消息] 还在处理中，返回长等待提示（已运行{elapsed_time}秒）")
                                stream = MakeTextStream(stream_id, message, False)
                            elif accumulated_text:
                                # 有累积内容，返回累积内容
                                logger.info(f"[接收消息] 还在处理中，返回累积内容（长度: {len(accumulated_text)}，已运行{elapsed_time}秒）")
                                stream = MakeTextStream(stream_id, accumulated_text, False)
                            else:
                                # 没有累积内容，返回处理中提示
                                logger.info(f"[接收消息] 还在处理中，返回处理中提示（已运行{elapsed_time}秒）")
                                stream = MakeTextStream(stream_id, get_processing_message(), False)
                            
                            encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                            if encrypted_resp:
                                return encrypted_resp
                            return "success"
                
                # 没有找到任务
                return "success"

            elif msg_type == 'image':
                # 处理图片消息
                image_data = message_data.get('image', {})
                image_url = image_data.get('url', '')
                logger.info(f"[接收消息] 图片 URL: {image_url}")

                # 检查是否已经有后台任务在处理
                task_key = user_id
                
                if task_key in _task_status_cache:
                    # 已有后台任务在处理，返回"正在处理"
                    stream_id = _task_status_cache[task_key]['stream_id']
                    stream = MakeTextStream(stream_id, "正在处理您的图片，请稍候...", False)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

                # 下载图片
                download_result = file_downloader.download_file(image_url, user_id=user_id, aes_key_base64=config.WECOM_ENCODING_AES_KEY)
                
                if download_result:
                    hash_path = download_result['hash_path']
                    original_filename = download_result['original_filename']
                    hash_filename = download_result['hash_filename']
                    
                    # 保存文件映射关系
                    db_manager.save_file_mapping(hash_filename, original_filename, user_id)
                    
                    # 保存文件路径到会话
                    session_manager.save_user_file(user_id, 'image', hash_path, original_filename)
                    
                    # 记录图片消息
                    image_media_id = extract_media_id(image_url)
                    db_manager.log_message(user_id, "image_message", f"图片: {image_url}", hash_path, msgid=msgid, media_id=image_media_id)
                    
                    # 构造询问消息
                    stream_id = str(int(time.time()))
                    reply_message = f"已收到图片：{original_filename}\n\n请告诉我您希望如何处理这张图片？\n例如：\n- 分析图片内容\n- 提取图片中的文字\n- 描述图片细节\n- 其他需求"
                    
                    stream = MakeTextStream(stream_id, reply_message, True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"
                else:
                    # 下载失败
                    # 记录图片消息（失败情况）
                    image_media_id = extract_media_id(image_url)
                    db_manager.log_message(user_id, "image_message", f"图片: {image_url}", None, msgid=msgid, media_id=image_media_id)
                    
                    stream_id = str(int(time.time()))
                    stream = MakeTextStream(stream_id, "下载图片失败，请稍后重试。", True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

            elif msg_type == 'file':
                # 处理文件消息
                file_data = message_data.get('file', {})
                file_url = file_data.get('url', '')
                logger.info(f"[接收消息] 文件 URL: {file_url}")

                # 下载文件
                download_result = file_downloader.download_file(file_url, user_id=user_id, aes_key_base64=config.WECOM_ENCODING_AES_KEY)

                # 记录文件消息
                if download_result:
                    hash_path = download_result['hash_path']
                    original_filename = download_result['original_filename']
                    hash_filename = download_result['hash_filename']
                    
                    # 保存文件映射关系
                    db_manager.save_file_mapping(hash_filename, original_filename, user_id)
                    
                    # 保存文件路径到会话
                    session_manager.save_user_file(user_id, 'file', hash_path, original_filename)
                    
                    # 记录文件消息
                    file_media_id = extract_media_id(file_url)
                    db_manager.log_message(user_id, "file_message", f"文件: {file_url}", hash_path, msgid=msgid, media_id=file_media_id)
                    
                    # 构造询问消息
                    stream_id = str(int(time.time()))
                    reply_message = f"已收到文件：{original_filename}\n\n请告诉我您希望如何处理这个文件？\n例如：\n- 读取文件内容\n- 提取文件信息\n- 分析文件数据\n- 其他需求"
                    
                    stream = MakeTextStream(stream_id, reply_message, True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"
                else:
                    # 下载失败
                    file_media_id = extract_media_id(file_url)
                    db_manager.log_message(user_id, "file_message", f"文件: {file_url}", None, msgid=msgid, media_id=file_media_id)
                    
                    stream_id = str(int(time.time()))
                    stream = MakeTextStream(stream_id, "下载文件失败，请稍后重试。", True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

            elif msg_type == 'voice':
                # 处理语音消息
                voice_data = message_data.get('voice', {})
                voice_content = voice_data.get('content', '')
                logger.info(f"[接收消息] 语音内容: {voice_content}")

                # 将语音内容作为文本处理
                db_manager.log_message(user_id, "user_message", voice_content, msgid=msgid)
                
                stream_id = str(int(time.time()))
                reply_content = run_async(process_message_and_get_reply(user_id, voice_content))

                # 生成 stream 消息
                stream = MakeTextStream(stream_id, reply_content, True)
                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)

                # 缓存结果
                with _request_cache_lock:
                    _request_cache[request_key] = encrypted_resp

                if encrypted_resp:
                    return encrypted_resp
                return "success"

            elif msg_type == 'mixed':
                # 处理图文混排消息
                mixed_data = message_data.get('mixed', {})
                msg_items = mixed_data.get('msg_item', [])
                logger.info(f"[接收消息] 图文混排，包含 {len(msg_items)} 个元素")

                # 提取文本内容
                text_content = ""
                for item in msg_items:
                    if item.get('msgtype') == 'text':
                        text_content += item.get('text', {}).get('content', '')

                if text_content:
                    # 去除 @机器人 的提及
                    if '@' in text_content:
                        text_content = text_content.split(maxsplit=1)[-1] if len(text_content.split()) > 1 else text_content

                    # 记录图文消息
                    db_manager.log_message(user_id, "mixed_message", f"图文混排: {text_content[:100]}", msgid=msgid)

                    stream_id = str(int(time.time()))
                    reply_content = run_async(process_message_and_get_reply(user_id, text_content_with_file))

                    # 生成 stream 消息
                    stream = MakeTextStream(stream_id, reply_content, True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)

                    # 缓存结果
                    with _request_cache_lock:
                        _request_cache[request_key] = encrypted_resp

                    if encrypted_resp:
                        return encrypted_resp
                    return "success"
                else:
                    # 没有文本内容，发送提示
                    stream_id = str(int(time.time()))
                    error_message = "收到图文混排消息！请提供文本内容以便我回复。"
                    stream = MakeTextStream(stream_id, error_message, True)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)

                    # 缓存结果
                    with _request_cache_lock:
                        _request_cache[request_key] = encrypted_resp

                    if encrypted_resp:
                        return encrypted_resp
                    return "success"

            else:
                logger.warning(f"[接收消息] 暂不支持的消息类型: {msg_type}")
                db_manager.log_message(user_id, f"unknown_message_{msg_type}", json.dumps(message_data), msgid=msgid)

                # 发送不支持提示
                stream_id = str(int(time.time()))
                error_message = f"抱歉，我暂时不支持 {msg_type} 类型的消息。"
                stream = MakeTextStream(stream_id, error_message, True)
                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)

                # 缓存结果
                with _request_cache_lock:
                    _request_cache[request_key] = encrypted_resp

                if encrypted_resp:
                    return encrypted_resp
                return "success"
        else:
            logger.warning(f"[接收消息] 解密失败: ret={ret}")
            return "解密失败", 400
    except Exception as e:
        logger.error(f"[接收消息] 异常: {e}")
        import traceback
        traceback.print_exc()
        return "接收异常", 500


async def process_message_and_get_reply(user_id: str, message: str):
    """
    异步处理消息：转发给 iFlow CLI 并返回回复内容（支持流式收集）

    Args:
        user_id: 用户 ID
        message: 用户消息

    Returns:
        回复内容
    """
    try:
        logger.info(f"[消息处理] 开始处理用户 {user_id} 的消息: {message[:100]}...")

        # 获取或创建用户会话
        client = await session_manager.get_or_create_session(user_id)

        # 发送消息到 iFlow CLI
        await client.send_message(message)

        # 接收 iFlow CLI 的回复（流式收集）
        response_text = ""
        assistant_finished = False

        async for msg in client.receive_messages():
            # 处理不同类型的消息
            if hasattr(msg, 'chunk') and hasattr(msg.chunk, 'text'):
                # AssistantMessage: AI 助手回复
                response_text += msg.chunk.text
                logger.debug(f"[消息处理] 接收到 iFlow 回复片段: {msg.chunk.text[:50]}...")
                
                # 实时更新任务状态缓存（用于流式刷新）
                task_key = user_id
                with _task_status_lock:
                    if task_key in _task_status_cache:
                        _task_status_cache[task_key]['result'] = response_text
                        logger.debug(f"[消息处理] 实时更新任务状态，当前长度: {len(response_text)}")
                        
            elif hasattr(msg, 'stop_reason'):
                # TaskFinishMessage: 任务完成
                logger.info(f"[消息处理] iFlow 任务完成，原因: {msg.stop_reason}")
                assistant_finished = True
                break

        # 如果没有收到完整的回复，使用已收集的文本
        if not assistant_finished and not response_text:
            logger.warning(f"[消息处理] 警告: 未收到 iFlow 完整回复")
            response_text = "抱歉，我遇到了一些问题，请稍后重试。"

        logger.info(f"[消息处理] iFlow 完整回复: {response_text[:100]}...")

        # 保存机器人回复消息到数据库（只记录非空消息）
        if response_text and response_text.strip():
            db_manager.log_message(user_id, "bot_message", response_text)

        return response_text

    except Exception as e:
        logger.error(f"[消息处理] 处理消息异常: {e}")
        import traceback
        traceback.print_exc()

        # 返回错误信息
        error_message = f"抱歉，处理您的消息时出错了: {str(e)}"
        db_manager.log_message(user_id, "error_message", error_message)
        return error_message


async def process_image_and_get_reply(user_id: str, image_url: str):
    """
    异步处理图片并返回回复内容

    Args:
        user_id: 用户 ID
        image_url: 图片 URL

    Returns:
        回复内容
    """
    try:
        logger.info(f"[图片处理] 开始处理用户 {user_id} 的图片: {image_url}")

        # 下载图片
        download_result = file_downloader.download_file(image_url, aes_key_base64=config.WECOM_ENCODING_AES_KEY)
        if download_result:
            # 获取解密后的文件路径
            downloaded_path = download_result['hash_path']
            # 处理图片
            result = await file_processor.process_file(downloaded_path, "image")

            # 不清理文件，让 AI 可以读取图片内容

            if result['success']:
                # 发送图片内容给 iFlow CLI 处理
                return await process_message_and_get_reply(user_id, result['content'])
            else:
                return f"处理图片失败: {result['content']}"
        else:
            return "下载图片失败，请稍后重试。"

    except Exception as e:
        logger.error(f"[图片处理] 异常: {e}")
        return f"处理图片时出错: {str(e)}"


async def process_file_and_get_reply(user_id: str, file_url: str):
    """
    异步处理文件并返回回复内容

    Args:
        user_id: 用户 ID
        file_url: 文件 URL

    Returns:
        回复内容
    """
    try:
        logger.info(f"[文件处理] 开始处理用户 {user_id} 的文件: {file_url}")

        # 下载文件
        download_result = file_downloader.download_file(file_url, aes_key_base64=config.WECOM_ENCODING_AES_KEY)
        if download_result:
            hash_path = download_result['hash_path']
            original_filename = download_result['original_filename']
            hash_filename = download_result['hash_filename']
            
            # 保存文件映射关系
            db_manager.save_file_mapping(hash_filename, original_filename, user_id)
            
            # 处理文件
            result = await file_processor.process_file(hash_path, "file")

            # 不清理文件，让 AI 可以读取文件内容

            if result['success']:
                # 发送文件内容给 iFlow CLI 处理
                return await process_message_and_get_reply(user_id, result['content'])
            else:
                return f"处理文件失败: {result['content']}"
        else:
            return "下载文件失败，请稍后重试。"

    except Exception as e:
        logger.error(f"[文件处理] 异常: {e}")
        return f"处理文件时出错: {str(e)}"


if __name__ == '__main__':
        try:
            logger.info(f"[启动] 企业微信机器人服务启动在 {config.FLASK_HOST}:{config.FLASK_PORT}")
            logger.info(f"[启动] 已启用功能: 会话持久化、文件处理、限流保护")
            app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
        except Exception as e:
            logger.error(f"[启动] 服务启动失败: {e}")
            raise