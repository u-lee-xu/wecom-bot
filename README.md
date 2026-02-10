# 企业微信智能机器人

企业微信智能机器人 - 与 iFlow CLI 双向消息转发

## 功能

- 接收企业微信消息并转发给 iFlow CLI
- 将 iFlow CLI 的回复发送回企业微信
- 支持多用户会话隔离

## 安装

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 配置

复制 `config.example.py` 为 `config.py`，并填写企业微信机器人配置：

```python
WECOM_TOKEN = "your_token_here"  # 从企业微信后台获取
WECOM_ENCODING_AES_KEY = "your_encoding_aes_key_here"  # 从企业微信后台获取
WECOM_CORP_ID = "your_corp_id_here"  # 从企业微信后台获取

FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
FLASK_DEBUG = True
```

## 运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 启动服务
python app.py
```

## 企业微信配置

在企业微信智能机器人设置中：

1. 创建机器人（选择 API 模式）
2. 设置回调 URL：`http://your-server-ip:5000/`
3. 填写 Token 和 EncodingAESKey（与 config.py 中一致）

## 开发状态

- [x] 开发环境搭建
- [x] 回调验证接口（GET）
- [x] 消息接收接口（POST）
- [ ] 会话管理器
- [ ] iFlow CLI SDK 集成
- [ ] 消息转发逻辑
- [ ] 回复消息功能