"""
测试可选功能
"""

import requests
import json
import time


def test_rate_limiter():
    """测试限流保护"""
    print("=" * 50)
    print("测试 1: 限流保护（连续发送 11 个请求）")
    print("=" * 50)

    url = "http://localhost:5000/"
    params = {
        "msg_signature": "test_signature",
        "timestamp": "1234567890",
        "nonce": "test_nonce"
    }

    message_data = {
        "msgid": "test_msg_001",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_001"},
        "response_url": "http://mock-response-url",
        "msgtype": "text",
        "text": {"content": "测试限流"}
    }

    encrypted_data = json.dumps({"encrypt": json.dumps(message_data)})
    headers = {"Content-Type": "application/json"}

    success_count = 0
    rate_limited_count = 0

    for i in range(11):
        print(f"\n发送第 {i+1} 个请求...")
        try:
            response = requests.post(url, params=params, data=encrypted_data, headers=headers, timeout=5)
            if response.status_code == 200:
                success_count += 1
                print(f"  ✅ 请求成功")
            elif response.status_code == 500:
                rate_limited_count += 1
                print(f"  ⚠️  请求被限流（预期行为）")
            else:
                print(f"  ❌ 请求失败: {response.status_code}")
        except Exception as e:
            print(f"  ❌ 请求异常: {e}")

        if i < 10:  # 前 10 个请求快速发送
            time.sleep(0.1)

    print(f"\n限流保护测试结果:")
    print(f"  成功请求数: {success_count} (预期: 10)")
    print(f"  限流请求数: {rate_limited_count} (预期: 1)")
    print()


def test_file_processing():
    """测试文件处理"""
    print("=" * 50)
    print("测试 2: 文件处理（图片、文件、语音、图文混排）")
    print("=" * 50)

    url = "http://localhost:5000/"
    params = {
        "msg_signature": "test_signature",
        "timestamp": "1234567890",
        "nonce": "test_nonce"
    }

    headers = {"Content-Type": "application/json"}

    # 测试图片消息
    print("\n测试图片消息:")
    image_data = {
        "msgid": "test_msg_002",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_002"},
        "response_url": "http://mock-response-url",
        "msgtype": "image",
        "image": {"url": "https://example.com/test.jpg"}
    }
    encrypted_data = json.dumps({"encrypt": json.dumps(image_data)})
    response = requests.post(url, params=params, data=encrypted_data, headers=headers, timeout=5)
    print(f"  响应状态码: {response.status_code}")

    # 测试文件消息
    print("\n测试文件消息:")
    file_data = {
        "msgid": "test_msg_003",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_003"},
        "response_url": "http://mock-response-url",
        "msgtype": "file",
        "file": {"url": "https://example.com/test.pdf"}
    }
    encrypted_data = json.dumps({"encrypt": json.dumps(file_data)})
    response = requests.post(url, params=params, data=encrypted_data, headers=headers, timeout=5)
    print(f"  响应状态码: {response.status_code}")

    # 测试语音消息
    print("\n测试语音消息:")
    voice_data = {
        "msgid": "test_msg_004",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_004"},
        "response_url": "http://mock-response-url",
        "msgtype": "voice",
        "voice": {"content": "这是语音转成的文本内容"}
    }
    encrypted_data = json.dumps({"encrypt": json.dumps(voice_data)})
    response = requests.post(url, params=params, data=encrypted_data, headers=headers, timeout=5)
    print(f"  响应状态码: {response.status_code}")

    # 测试图文混排消息
    print("\n测试图文混排消息:")
    mixed_data = {
        "msgid": "test_msg_005",
        "aibotid": "test_bot_001",
        "chattype": "single",
        "from": {"userid": "test_user_005"},
        "response_url": "http://mock-response-url",
        "msgtype": "mixed",
        "mixed": {
            "msg_item": [
                {
                    "msgtype": "text",
                    "text": {"content": "@机器人 这是一个测试消息"}
                },
                {
                    "msgtype": "image",
                    "image": {"url": "https://example.com/test.jpg"}
                }
            ]
        }
    }
    encrypted_data = json.dumps({"encrypt": json.dumps(mixed_data)})
    response = requests.post(url, params=params, data=encrypted_data, headers=headers, timeout=5)
    print(f"  响应状态码: {response.status_code}")

    print()


def test_database():
    """测试数据库功能"""
    print("=" * 50)
    print("测试 3: 数据库功能（会话持久化、消息记录）")
    print("=" * 50)

    try:
        from database import db_manager

        # 测试获取用户统计
        user_id = "test_user_001"
        stats = db_manager.get_user_stats(user_id)
        print(f"\n用户 {user_id} 统计信息:")
        print(f"  会话 ID: {stats.get('session_id')}")
        print(f"  消息总数: {stats.get('total_messages')}")

        print("\n数据库功能测试通过")
    except Exception as e:
        print(f"\n数据库功能测试失败: {e}")
        import traceback
        traceback.print_exc()

    print()


if __name__ == "__main__":
    print("企业微信机器人可选功能测试")
    print("=" * 50)
    print()

    # 运行测试
    test_database()
    test_rate_limiter()
    test_file_processing()

    print("=" * 50)
    print("测试完成")
    print("=" * 50)
