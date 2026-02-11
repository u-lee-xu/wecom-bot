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
from session_manager import session_manager
from database import db_manager
from rate_limiter import rate_limiter
from file_downloader import file_downloader
from file_processor import file_processor
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局事件循环（用于所有异步操作）
_global_loop = None
_loop_lock = threading.Lock()

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
    return future.result(timeout=120)


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

            # 检查是否有引用信息
            quoted_msg_id = message_data.get('quoted_msg_id', None)
            if quoted_msg_id:
                logger.info(f"[接收消息] 检测到引用消息: {quoted_msg_id}")

            logger.info(f"[接收消息] 用户ID: {user_id}, 消息类型: {msg_type}")

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
                quote_data = message_data.get('quote', {})
                if quote_data:
                    logger.info(f"[接收消息] 检测到引用消息: {quote_data}")
                    if quote_data.get('msgtype') == 'image':
                        quoted_image_url = quote_data.get('image', {}).get('url', '')
                        logger.info(f"[接收消息] 引用中的图片 URL: {quoted_image_url}")

                # 如果有引用的图片，下载并保存
                if quoted_image_url:
                    downloaded_path = file_downloader.download_file(quoted_image_url)
                    if downloaded_path:
                        decrypted_path = file_downloader.decrypt_file(downloaded_path, config.WECOM_ENCODING_AES_KEY)
                        final_path = decrypted_path if decrypted_path else downloaded_path
                        session_manager.save_user_file(user_id, 'image', final_path)
                        db_manager.log_message(user_id, "image_message", f"引用图片: {quoted_image_url}", final_path)
                        logger.info(f"[接收消息] 引用图片已保存: {final_path}")

                # 记录用户消息
                db_manager.log_message(user_id, "user_message", text_content)

                # 从数据库查询用户最近的文件/图片消息（优先获取引用的图片）
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
                    
                    file_info = f"\n\n[用户最近发送的文件]\n类型: {recent_file['file_type']}\n路径: {file_path}\n文件名: {display_filename}"
                    text_content_with_file = text_content + file_info
                    logger.info(f"[接收消息] 附加文件信息到消息: {file_path}")
                else:
                    text_content_with_file = text_content

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
                    stream = MakeTextStream(stream_id, "正在处理您的请求，请稍候...", False)
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
                        with _task_status_lock:
                            if task_key in _task_status_cache:
                                _task_status_cache[task_key]['status'] = 'error'
                                _task_status_cache[task_key]['result'] = f"处理失败: {str(e)}"
                
                # 启动后台处理线程
                threading.Thread(target=process_in_background, daemon=True).start()
                
                # 立即返回"正在处理"的消息（不等待）
                stream = MakeTextStream(stream_id, "正在处理您的请求，请稍候...", False)
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
                            # 还在处理中
                            logger.info(f"[接收消息] 还在处理中")
                            stream = MakeTextStream(stream_id, "正在处理您的请求，请稍候...", False)
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
                download_result = file_downloader.download_file(image_url)
                final_path = None
                
                if download_result:
                    hash_path = download_result['hash_path']
                    original_filename = download_result['original_filename']
                    hash_filename = download_result['hash_filename']
                    
                    # 解密图片（企业微信的图片是加密的）
                    decrypted_path = file_downloader.decrypt_file(hash_path, config.WECOM_ENCODING_AES_KEY)
                    
                    # 保存解密后的文件路径到数据库（或者保留原始路径，看AI是否需要）
                    # 这里保存解密后的路径，因为这才是AI可以正常读取的格式
                    final_path = decrypted_path if decrypted_path else hash_path
                    
                    # 保存文件映射关系（使用解密后的文件名）
                    decrypted_filename = os.path.basename(final_path)
                    db_manager.save_file_mapping(decrypted_filename, original_filename, user_id)
                    
                    # 保存文件路径到会话
                    session_manager.save_user_file(user_id, 'image', final_path, original_filename)
                    
                    # 记录图片消息
                    db_manager.log_message(user_id, "image_message", f"图片: {image_url}", final_path)
                    
                    # 生成固定的 stream_id
                    stream_id = f"{user_id}_{int(time.time())}"
                    
                    # 标记任务开始处理
                    with _task_status_lock:
                        _task_status_cache[task_key] = {
                            'status': 'processing',
                            'result': None,
                            'user_id': user_id,
                            'stream_id': stream_id,
                            'created_at': int(time.time())
                        }
                    
                    # 后台异步处理（不阻塞响应）
                    def process_image_background():
                        try:
                            reply_content = "收到图片了！"
                            
                            with _task_status_lock:
                                if task_key in _task_status_cache:
                                    _task_status_cache[task_key]['status'] = 'completed'
                                    _task_status_cache[task_key]['result'] = reply_content
                        except Exception as e:
                            logger.error(f"[后台处理] 图片处理失败: {e}")
                            with _task_status_lock:
                                if task_key in _task_status_cache:
                                    _task_status_cache[task_key]['status'] = 'error'
                                    _task_status_cache[task_key]['result'] = f"处理图片失败: {str(e)}"
                    
                    # 启动后台处理线程
                    threading.Thread(target=process_image_background, daemon=True).start()
                    
                    # 立即返回"正在处理"的消息
                    stream = MakeTextStream(stream_id, "正在处理您的图片，请稍候...", False)
                    encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)
                    
                    if encrypted_resp:
                        return encrypted_resp
                    return "success"
                else:
                    # 下载失败
                    # 记录图片消息（失败情况）
                    db_manager.log_message(user_id, "image_message", f"图片: {image_url}", None)
                    
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
                download_result = file_downloader.download_file(file_url)

                # 记录文件消息
                if download_result:
                    hash_path = download_result['hash_path']
                    original_filename = download_result['original_filename']
                    hash_filename = download_result['hash_filename']
                    
                    # 保存文件映射关系
                    db_manager.save_file_mapping(hash_filename, original_filename, user_id)
                    
                    db_manager.log_message(user_id, "file_message", f"文件: {file_url}", hash_path)
                    # 保存文件路径到会话
                    session_manager.save_user_file(user_id, 'file', hash_path, original_filename)
                else:
                    db_manager.log_message(user_id, "file_message", f"文件: {file_url}", None)

                # 下载并处理文件
                stream_id = str(int(time.time()))
                reply_content = run_async(process_file_and_get_reply(user_id, file_url))

                # 生成 stream 消息
                stream = MakeTextStream(stream_id, reply_content, True)
                encrypted_resp = EncryptMessage(receiveid, nonce, timestamp, stream)

                # 缓存结果
                with _request_cache_lock:
                    _request_cache[request_key] = encrypted_resp

                if encrypted_resp:
                    return encrypted_resp
                return "success"

            elif msg_type == 'voice':
                # 处理语音消息
                voice_data = message_data.get('voice', {})
                voice_content = voice_data.get('content', '')
                logger.info(f"[接收消息] 语音内容: {voice_content}")

                # 记录语音消息
                db_manager.log_message(user_id, "voice_message", f"语音: {voice_content}")

                # 将语音内容作为文本处理
                db_manager.log_message(user_id, "user_message", voice_content)

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
                    db_manager.log_message(user_id, "mixed_message", f"图文混排: {text_content[:100]}")

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
                db_manager.log_message(user_id, f"unknown_message_{msg_type}", json.dumps(message_data))

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
    异步处理消息：转发给 iFlow CLI 并返回回复内容

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

        # 接收 iFlow CLI 的回复
        response_text = ""
        assistant_finished = False

        async for msg in client.receive_messages():
            # 处理不同类型的消息
            if hasattr(msg, 'chunk') and hasattr(msg.chunk, 'text'):
                # AssistantMessage: AI 助手回复
                response_text += msg.chunk.text
                logger.debug(f"[消息处理] 接收到 iFlow 回复片段: {msg.chunk.text[:50]}...")
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

        # 保存机器人回复消息到数据库
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
        downloaded_path = file_downloader.download_file(image_url)
        if downloaded_path:
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
        download_result = file_downloader.download_file(file_url)
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