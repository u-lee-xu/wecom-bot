# MEMORY-002 - 技术资料

## 索引信息
- 索引号：M002
- 日期：2026-02-10
- 类型：技术资料

---

## 一、企业微信智能机器人 API

### 1.1 创建参数

| 参数 | 说明 |
|------|------|
| URL | 回调接口路径（HTTPS，需设置白名单） |
| Token | 随机生成，用于签名验证 |
| EncodingAESKey | 消息加解密密钥 |

### 1.2 验证 URL（GET）

**请求：**
```
GET ?msg_signature=xxx&timestamp=xxx&nonce=xxx&echostr=xxx
```

**响应：** 返回解密后的 `echostr` 明文

### 1.3 接收消息（POST，加密）

**加密格式：**
```json
{
  "encrypt": "加密的JSON字符串"
}
```

**文本消息解密后格式：**
```json
{
  "msgid": "唯一ID",
  "aibotid": "机器人ID",
  "chattype": "single/group",
  "from": {"userid": "用户ID"},
  "response_url": "回复URL（1小时有效，用一次）",
  "msgtype": "text",
  "text": {"content": "消息内容"}
}
```

**支持的消息类型：**
- text - 文本消息
- image - 图片消息（单聊）
- mixed - 图文混排消息
- voice - 语音消息（已转文本）
- file - 文件消息（<100M）

### 1.4 回复消息（POST 到 response_url）

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "Markdown内容"
  }
}
```

**支持的消息类型：**
- markdown - Markdown 格式文本
- template_card - 模板卡片（仅单聊）

### 1.5 官方资源
- 官方文档：https://developer.work.weixin.qq.com/document/path/101033
- 加解密库下载：https://developer.work.weixin.qq.com/document/path/90307
- 接收消息：https://developer.work.weixin.qq.com/document/path/100719
- 主动回复：https://developer.work.weixin.qq.com/document/path/101138
- 接收事件：https://developer.work.weixin.qq.com/document/path/101027

---

## 二、iFlow CLI ACP 协议

### 2.1 启动 ACP 模式

```bash
iflow --experimental-acp --port 8090
```

**通信方式：** WebSocket (`ws://localhost:8090/acp`)

### 2.2 Python SDK 使用

**安装：**
```bash
pip install iflow-cli-sdk
```

**基础用法：**
```python
import asyncio
from iflow_sdk import IFlowClient

async def main():
    async with IFlowClient() as client:
        # 发送消息
        await client.send_message("你好")

        # 接收消息
        async for message in client.receive_messages():
            print(message)

asyncio.run(main())
```

**简单查询：**
```python
from iflow_sdk import query

response = await query("帮助我写个Python函数")
print(response)
```

### 2.3 消息类型

| 类型 | 说明 |
|------|------|
| AssistantMessage | AI 助手回复 |
| ToolCallMessage | 工具调用 |
| PlanMessage | 任务计划 |
| TaskFinishMessage | 任务完成 |

### 2.4 会话模式

| 模式 | 说明 |
|------|------|
| DEFAULT | 默认模式（需确认） |
| YOLO | 自动执行所有操作 |
| AUTO_EDIT | 自动编辑模式 |
| PLAN | 仅规划不执行 |

### 2.5 会话管理命令

| 命令 | 说明 |
|------|------|
| `/chat save <label>` | 保存当前会话并打标签 |
| `/chat resume <label>` | 恢复指定标签的会话 |
| `/chat list` | 查看所有保存的会话 |
| `iflow --resume` | 显示历史会话列表并选择恢复 |
| `iflow -r <session_id>` | 直接恢复指定会话 |

### 2.6 官方资源
- Python SDK：https://pypi.org/project/iflow-cli-sdk/
- ACP 协议：https://agentcommunicationprotocol.dev/
- iFlow 官网：https://cli.iflow.cn/

---

## 三、会话管理

### 3.1 会话存储
- **位置：** `~/.iflow/history/`
- **格式：** 每个会话是一个独立的目录（使用哈希命名）
- **管理方式：** 使用 Git 管理会话历史

### 3.2 检查点功能
配置文件 (`~/.iflow/settings.json`)：
```json
{
  "checkpointing": {
    "enabled": true
  }
}
```

### 3.3 记忆功能

| 功能 | 支持情况 |
|------|----------|
| 会话历史保存 | ✅ 使用 Git 存储 |
| 会话恢复 | ✅ 通过标签或 ID 恢复 |
| 会话压缩 | ✅ `/chat compress` 命令 |
| 检查点 | ✅ 自动保存关键状态 |
| 版本回滚 | ✅ Git 支持 |
| 多会话管理 | ✅ 支持同时管理多个会话 |

### 3.4 多用户会话隔离

**推荐实现（方案 1）：**
```python
user_sessions = {}  # userid -> IFlowClient

async def handle_message(userid, message):
    # 获取或创建用户专属会话
    if userid not in user_sessions:
        user_sessions[userid] = IFlowClient()

    client = user_sessions[userid]
    await client.send_message(message)

    async for msg in client.receive_messages():
        # 处理响应...
        pass
```

---

## 四、开发环境

### 4.1 系统信息
- **操作系统：** Linux 6.12.62+rpt-rpi-2712 (树莓派)
- **Python：** 3.11.2
- **iFlow CLI：** 0.5.8
- **Node.js：** v22.22.0
- **Git：** 2.39.5

### 4.2 已安装工具
| 工具 | 状态 |
|------|------|
| iFlow CLI | ✅ 已安装 |
| Python 3.11.2 | ✅ 已安装 |
| Docker | ✅ 已安装 |
| npm | ✅ 已安装 |
| ffmpeg | ✅ 已安装 |
| curl | ✅ 已安装 |
| wget | ✅ 已安装 |

### 4.3 依赖包（待安装）
- `iflow-cli-sdk` - Python SDK
- `Flask` 或 `FastAPI` - Web 框架
- 企业微信加解密库 - Python 版本

---

## 五、关键注意事项

### 5.1 企业微信相关
1. URL 需要设置白名单
2. 消息和回复都是加密的
3. response_url 有效期 1 小时，仅能用一次
4. 图片和文件 URL 5 分钟内有效，且已加密
5. 需要处理事件排重（使用 msgid）
6. 群聊中主动回复会自动引用触发消息

### 5.2 iFlow CLI 相关
1. 消息需要通过 ACP 协议传输
2. SDK 自动管理 iFlow 进程
3. 端口冲突由 SDK 自动检测
4. 使用同一个 IFlowClient 实例保持会话
5. 会话历史存储在 `~/.iflow/history/`

### 5.3 系统相关
1. 树莓派 ARM64 架构，需要注意依赖兼容性
2. 网络连接 GitHub 可能超时，考虑使用镜像
3. 资源有限，注意内存使用