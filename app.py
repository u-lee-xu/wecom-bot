"""
企业微信智能机器人主应用
"""

from flask import Flask, request
from wework.WXBizMsgCrypt import WXBizMsgCrypt
import config
import json
import asyncio
from session_manager import session_manager

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

    print(f"[验证URL] msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}, echostr={echostr}")

    try:
        # 解密 echostr 并返回
        ret, sEchoStr = get_wxcpt().VerifyURL(msg_signature, timestamp, nonce, echostr)
        if ret == 0:
            print(f"[验证URL] 成功: {sEchoStr}")
            return sEchoStr
        else:
            print(f"[验证URL] 失败: ret={ret}")
            return "验证失败", 400
    except Exception as e:
        print(f"[验证URL] 异常: {e}")
        return "验证异常", 500


def receive_message():
    """
    接收消息
    """
    try:
        # 获取加密消息
        data = request.get_data(as_text=True)
        print(f"[接收消息] 原始数据: {data}")

        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')

        # 解密消息
        ret, decrypted_msg = get_wxcpt().DecryptMsg(data, msg_signature, timestamp, nonce)
        if ret == 0:
            print(f"[接收消息] 解密成功: {decrypted_msg}")

            # 解析 JSON 消息
            message_data = json.loads(decrypted_msg)

            # 提取消息信息
            user_id = message_data.get('from', {}).get('userid', '')
            response_url = message_data.get('response_url', '')
            msg_type = message_data.get('msgtype', '')

            print(f"[接收消息] 用户ID: {user_id}, 消息类型: {msg_type}")

            # 处理文本消息
            if msg_type == 'text':
                text_content = message_data.get('text', {}).get('content', '')
                print(f"[接收消息] 文本内容: {text_content}")

                # 去除 @机器人 的提及（如果有）
                if '@' in text_content:
                    # 移除 @机器人 部分，保留实际内容
                    text_content = text_content.split(maxsplit=1)[-1] if len(text_content.split()) > 1 else text_content

                # 异步处理消息转发和回复
                asyncio.run(process_message_async(user_id, text_content, response_url))
            else:
                print(f"[接收消息] 暂不支持的消息类型: {msg_type}")

            # 返回空包（后续会通过 response_url 回复）
            return "success"
        else:
            print(f"[接收消息] 解密失败: ret={ret}")
            return "解密失败", 400
    except Exception as e:
        print(f"[接收消息] 异常: {e}")
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
        print(f"[消息处理] 开始处理用户 {user_id} 的消息: {message}")

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
                print(f"[消息处理] 接收到 iFlow 回复片段: {msg.chunk.text[:50]}...")
            elif hasattr(msg, 'stop_reason'):
                # TaskFinishMessage: 任务完成
                print(f"[消息处理] iFlow 任务完成，原因: {msg.stop_reason}")
                assistant_finished = True
                break

        # 如果没有收到完整的回复，使用已收集的文本
        if not assistant_finished and not response_text:
            print(f"[消息处理] 警告: 未收到 iFlow 完整回复")
            response_text = "抱歉，我遇到了一些问题，请稍后重试。"

        print(f"[消息处理] iFlow 完整回复: {response_text}")

        # 发送回复给企业微信
        await send_reply_to_wecom(response_url, response_text)

    except Exception as e:
        print(f"[消息处理] 处理消息异常: {e}")
        import traceback
        traceback.print_exc()

        # 发送错误回复
        error_message = f"抱歉，处理您的消息时出错了: {str(e)}"
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

        print(f"[回复消息] 发送回复到企业微信: {message[:50]}...")

        async with aiohttp.ClientSession() as session:
            async with session.post(response_url, json=reply_data) as resp:
                if resp.status == 200:
                    print(f"[回复消息] 发送成功")
                else:
                    text = await resp.text()
                    print(f"[回复消息] 发送失败: {resp.status} - {text}")

    except Exception as e:
        print(f"[回复消息] 发送异常: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    print(f"[启动] 企业微信机器人服务启动在 {config.FLASK_HOST}:{config.FLASK_PORT}")
    app.run(host=config.FLASK_HOST, port=config.FLASK_PORT, debug=config.FLASK_DEBUG)