"""
企业微信智能机器人主应用
"""

from flask import Flask, request
from wework.WXBizMsgCrypt import WXBizMsgCrypt
import config
import json
import asyncio
from session_manager import session_manager
from database import db_manager
from rate_limiter import rate_limiter
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 初始化加解密工具（延迟初始化，避免配置无效时无法启动）
wxcpt = None


def get_wxcpt():
    """获取加解密工具实例"""
    global wxcpt
    if wxcpt is None:
        wxcpt = WXBizMsgCrypt(
            config.WECOM_TOKEN,
            config.WECOM_ENCODING_AES_KEY,
            config.WECOM_CORP_ID
        )
    return wxcpt


@app.route('/', methods=['GET', 'POST'])
def callback():
    """
    企业微信回调接口
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
    接收消息
    """
    try:
        # 获取加密消息
        data = request.get_data(as_text=True)
        logger.debug(f"[接收消息] 原始数据: {data[:200]}...")

        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')

        # 解密消息
        ret, decrypted_msg = get_wxcpt().DecryptMsg(data, msg_signature, timestamp, nonce)
        if ret == 0:
            logger.info(f"[接收消息] 解密成功")

            # 解析 JSON 消息
            message_data = json.loads(decrypted_msg)

            # 提取消息信息
            user_id = message_data.get('from', {}).get('userid', '')
            response_url = message_data.get('response_url', '')
            msg_type = message_data.get('msgtype', '')

            logger.info(f"[接收消息] 用户ID: {user_id}, 消息类型: {msg_type}")

            # 限流保护
            allowed, wait_time = rate_limiter.is_allowed(user_id)
            if not allowed:
                logger.warning(f"[限流] 用户 {user_id} 超过限制，拒绝处理")
                # 发送限流提示消息
                error_message = f"您的请求过于频繁，请 {wait_time} 秒后再试。"
                asyncio.run(send_reply_to_wecom(response_url, error_message))
                return "success"

            # 根据消息类型处理
            if msg_type == 'text':
                # 处理文本消息
                text_content = message_data.get('text', {}).get('content', '')
                logger.info(f"[接收消息] 文本内容: {text_content}")

                # 去除 @机器人 的提及（如果有）
                if '@' in text_content:
                    text_content = text_content.split(maxsplit=1)[-1] if len(text_content.split()) > 1 else text_content

                # 记录用户消息
                db_manager.log_message(user_id, "user_message", text_content)

                # 异步处理消息转发和回复
                asyncio.run(process_message_async(user_id, text_content, response_url))

            elif msg_type == 'image':
                # 处理图片消息
                image_data = message_data.get('image', {})
                image_url = image_data.get('url', '')
                logger.info(f"[接收消息] 图片 URL: {image_url}")

                # 记录图片消息
                db_manager.log_message(user_id, "image_message", f"图片: {image_url}")

                # 发送图片处理提示
                async def process_image():
                    error_message = "收到图片！我暂时无法直接查看图片内容，但我可以帮你分析图片中的信息。"
                    await send_reply_to_wecom(response_url, error_message)

                asyncio.run(process_image())

            elif msg_type == 'file':
                # 处理文件消息
                file_data = message_data.get('file', {})
                file_url = file_data.get('url', '')
                logger.info(f"[接收消息] 文件 URL: {file_url}")

                # 记录文件消息
                db_manager.log_message(user_id, "file_message", f"文件: {file_url}")

                # 发送文件处理提示
                async def process_file():
                    error_message = "收到文件！我暂时无法直接查看文件内容，但我可以帮你处理文件。"
                    await send_reply_to_wecom(response_url, error_message)

                asyncio.run(process_file())

            elif msg_type == 'voice':
                # 处理语音消息
                voice_data = message_data.get('voice', {})
                voice_content = voice_data.get('content', '')
                logger.info(f"[接收消息] 语音内容: {voice_content}")

                # 记录语音消息
                db_manager.log_message(user_id, "voice_message", f"语音: {voice_content}")

                # 将语音内容作为文本处理
                db_manager.log_message(user_id, "user_message", voice_content)
                asyncio.run(process_message_async(user_id, voice_content, response_url))

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

                    # 异步处理消息转发和回复
                    asyncio.run(process_message_async(user_id, text_content, response_url))
                else:
                    # 没有文本内容，发送提示
                    async def process_mixed():
                        error_message = "收到图文混排消息！请提供文本内容以便我回复。"
                        await send_reply_to_wecom(response_url, error_message)

                    asyncio.run(process_mixed())

            else:
                logger.warning(f"[接收消息] 暂不支持的消息类型: {msg_type}")
                db_manager.log_message(user_id, f"unknown_message_{msg_type}", json.dumps(message_data))

                # 发送不支持提示
                async def process_unsupported():
                    error_message = f"抱歉，我暂时不支持 {msg_type} 类型的消息。"
                    await send_reply_to_wecom(response_url, error_message)

                asyncio.run(process_unsupported())

            # 返回空包（后续会通过 response_url 回复）
            return "success"
        else:
            logger.warning(f"[接收消息] 解密失败: ret={ret}")
            return "解密失败", 400
    except Exception as e:
        logger.error(f"[接收消息] 异常: {e}")
        import traceback
        traceback.print_exc()
        return "接收异常", 500


async def process_message_async(user_id: str, message: str, response_url: str):
    """
    异步处理消息：转发给 iFlow CLI 并回复

    Args:
        user_id: 用户 ID
        message: 用户消息
        response_url: 回复 URL
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

        # 发送回复给企业微信
        await send_reply_to_wecom(response_url, response_text)

    except Exception as e:
        logger.error(f"[消息处理] 处理消息异常: {e}")
        import traceback
        traceback.print_exc()

        # 发送错误回复
        error_message = f"抱歉，处理您的消息时出错了: {str(e)}"
        db_manager.log_message(user_id, "error_message", error_message)
        await send_reply_to_wecom(response_url, error_message)


async def send_reply_to_wecom(response_url: str, message: str):
    """
    发送回复给企业微信

    Args:
        response_url: 企业微信回复 URL
        message: 回复消息内容
    """
    try:
        import aiohttp

        # 构造回复消息（Markdown 格式）
        reply_data = {
            "msgtype": "markdown",
            "markdown": {
                "content": message
            }
        }

        logger.info(f"[回复消息] 发送回复到企业微信: {message[:100]}...")

        async with aiohttp.ClientSession() as session:
            async with session.post(response_url, json=reply_data) as resp:
                if resp.status == 200:
                    logger.info(f"[回复消息] 发送成功")
                else:
                    text = await resp.text()
                    logger.error(f"[回复消息] 发送失败: {resp.status} - {text}")

    except Exception as e:
            logger.error(f"[回复消息] 发送异常: {e}")
            import traceback
            traceback.print_exc()
    
    
    if __name__ == '__main__':
        try:
            logger.info(f"[启动] 企业微信机器人服务启动在 {config.FLASK_HOST}:{config.FLASK_PORT}")
            logger.info(f"[启动] 已启用功能: 会话持久化、文件处理、限流保护")
            app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)
        except Exception as e:
            logger.error(f"[启动] 服务启动失败: {e}")
            raise