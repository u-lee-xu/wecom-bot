"""
测试企业微信机器人接口
"""

import requests
import json
import base64


def test_callback_url():
    """测试回调 URL 验证接口"""
    print("=" * 50)
    print("测试 1: 回调 URL 验证接口 (GET)")
    print("=" * 50)

    url = "http://localhost:5000/"
    params = {
        "msg_signature": "test_signature",
        "timestamp": "1234567890",
        "nonce": "test_nonce",
        "echostr": "test_echo"
    }

    response = requests.get(url, params=params)
    print(f"请求: GET {url}")
    print(f"参数: {params}")
    print(f"响应状态码: {response.status_code}")
    print(f"响应内容: {response.text}")
    print()


def test_message_receive():
    """测试消息接收接口"""
    print("=" * 50)
    print("测试 2: 消息接收接口 (POST)")
    print("=" * 50)

    url = "http://localhost:5000/"
    params = {
        "msg_signature": "test_signature",
        "timestamp": "1234567890",
        "nonce": "test_nonce"
    }

    # 模拟加密消息（简化版，真实环境需要使用 WXBizMsgCrypt 加密）
    message_data = {
        "msgid": "test_msg_001",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_001"},
        "response_url": "http://mock-response-url",
        "msgtype": "text",
        "text": {"content": "你好，请介绍一下你自己"}
    }

    # 模拟加密格式
    encrypted_data = json.dumps({"encrypt": json.dumps(message_data)})

    headers = {"Content-Type": "application/json"}

    print(f"请求: POST {url}")
    print(f"消息内容: {json.dumps(message_data, ensure_ascii=False)}")

    try:
        response = requests.post(url, params=params, data=encrypted_data, headers=headers)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
    except Exception as e:
        print(f"请求异常: {e}")

    print()


def test_health():
    """测试服务健康状态"""
    print("=" * 50)
    print("测试 3: 服务健康检查")
    print("=" * 50)

    try:
        response = requests.get("http://localhost:5000/")
        print(f"响应状态码: {response.status_code}")
        if response.status_code == 200:
            print("✅ 服务正常运行")
        else:
            print("⚠️ 服务可能存在问题")
    except Exception as e:
        print(f"❌ 服务无法访问: {e}")

    print()


if __name__ == "__main__":
    print("企业微信机器人接口测试")
    print("=" * 50)
    print()

    # 运行测试
    test_health()
    test_callback_url()
    test_message_receive()

    print("=" * 50)
    print("测试完成")
    print("=" * 50)