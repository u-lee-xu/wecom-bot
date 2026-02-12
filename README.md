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

### 1. 企业微信机器人配置

复制 `config.example.py` 为 `config.py`，并填写企业微信机器人配置：

```python
# 企业微信配置
WECOM_TOKEN = "your_token_here"  # 从企业微信后台获取
WECOM_ENCODING_AES_KEY = "your_encoding_aes_key_here"  # 从企业微信后台获取
WECOM_CORP_ID = "your_corp_id_here"  # 企业 ID
WECOM_AGENT_ID = "1000003"  # 应用 ID
WECOM_SECRET = "your_secret_here"  # 应用密钥

# Flask 配置
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 26036  # 对应企业微信回调 URL 的端口
FLASK_DEBUG = False  # 生产环境关闭调试模式

# iFlow 配置
IFLOW_TIMEOUT = 120  # iFlow 超时时间（秒）
```

**获取方式**：
1. 登录企业微信管理后台
2. 进入「应用管理」→「应用」→「自建」→「创建应用」
3. 选择「智能机器人」类型
4. 创建后获取：Agent ID、Secret、Corp ID
5. 在「接收消息」设置中获取：Token、EncodingAESKey

### 2. iFlow CLI 配置

安装并配置 iFlow CLI：

```bash
# 安装 iFlow CLI
bash -c "$(curl -fsSL https://gitee.com/iflow-ai/iflow-cli/raw/main/install.sh)"

# 配置 API key
iflow config set apiKey "your_api_key_here"
```

**配置文件位置**：`~/.iflow/settings.json`

**配置内容**：
```json
{
  "apiKey": "sk-your-api-key-here",
  "searchApiKey": "sk-your-api-key-here",
  "baseUrl": "https://apis.iflow.cn/v1",
  "modelName": "glm-4.7"
}
```

**获取 API key**：
1. 访问 https://cli.iflow.cn
2. 注册/登录账号
3. 获取 API key
4. 注意 API key 有效期，到期后需要更新

**更新 API key**：
```bash
# 编辑配置文件
nano ~/.iflow/settings.json

# 重启服务
sudo systemctl restart wecom-bot.service
```

### 3. 系统服务配置（可选）

创建 systemd 服务文件 `/etc/systemd/system/wecom-bot.service`：

```ini
[Unit]
Description=Enterprise WeChat Bot Service
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/wecom
Environment="PATH=/home/pi/wecom/venv/bin"
ExecStart=/home/pi/wecom/venv/bin/python app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用和启动服务：
```bash
sudo systemctl enable wecom-bot.service
sudo systemctl start wecom-bot.service
sudo systemctl status wecom-bot.service
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
2. 设置回调 URL：`http://your-server-ip:26036/`
3. 填写 Token 和 EncodingAESKey（与 config.py 中一致）

## 打包和部署

### 打包部署包

在当前设备上运行打包脚本：

```bash
bash package.sh
```

这将创建一个名为 `wecom-bot-vYYYYMMDD.tar.gz` 的部署包，包含所有必要的文件。

### 部署到新设备

#### 方式 1：自动部署

```bash
# 1. 上传部署包
scp wecom-bot-vYYYYMMDD.tar.gz user@target:/tmp/

# 2. SSH 登录目标设备
ssh user@target

# 3. 运行部署脚本
cd /tmp
tar -xzf wecom-bot-vYYYYMMDD.tar.gz
bash deploy_remote.sh -p wecom-bot-vYYYYMMDD.tar.gz
```

#### 方式 2：手动部署

```bash
# 1. 上传部署包
scp wecom-bot-vYYYYMMDD.tar.gz user@target:/tmp/

# 2. SSH 登录目标设备
ssh user@target

# 3. 解压到安装目录
sudo mkdir -p /opt/wecom-bot
cd /opt/wecom-bot
sudo tar -xzf /tmp/wecom-bot-vYYYYMMDD.tar.gz
sudo chown $USER:$USER /opt/wecom-bot

# 4. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 5. 安装依赖
pip install -r requirements.txt

# 6. 配置文件
nano config.py  # 填写企业微信配置

# 7. 安装 iFlow CLI
bash -c "$(curl -fsSL https://gitee.com/iflow-ai/iflow-cli/raw/main/install.sh)"
iflow config set apiKey "your_api_key_here"

# 8. 创建必要目录
mkdir -p user_data shared_files downloads

# 9. 安装 systemd 服务
sudo cp wecom-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wecom-bot.service
sudo systemctl start wecom-bot.service

# 10. 查看服务状态
sudo systemctl status wecom-bot.service
```

### 部署脚本参数

`deploy_remote.sh` 支持以下参数：

```bash
bash deploy_remote.sh [选项]

选项:
  -p, --package FILE   部署包路径 (默认: /tmp/wecom-bot-deploy.tar.gz)
  -d, --dir DIR        安装目录 (默认: /opt/wecom-bot)
  -h, --help           显示帮助信息
```

### 系统要求

- Python 3.8 或更高版本
- Linux 系统（推荐 Ubuntu、Debian、CentOS）
- 系统权限（sudo）用于安装 systemd 服务
- 网络连接（用于安装依赖和 iFlow CLI）

### 常用命令

```bash
# 查看服务状态
sudo systemctl status wecom-bot.service

# 启动服务
sudo systemctl start wecom-bot.service

# 停止服务
sudo systemctl stop wecom-bot.service

# 重启服务
sudo systemctl restart wecom-bot.service

# 查看日志
sudo journalctl -u wecom-bot.service -f

# 查看应用日志
tail -f /opt/wecom-bot/app.log
```

## 开发状态

- [x] 开发环境搭建
- [x] 回调验证接口（GET）
- [x] 消息接收接口（POST）
- [x] 会话管理器
- [x] iFlow CLI SDK 集成
- [x] 消息转发逻辑
- [x] 回复消息功能
- [x] 流式消息支持
- [x] 文件处理（图片、文档）
- [x] 文件解密（企业微信加密格式）
- [x] 会话隔离（多用户）
- [x] 数据库持久化
- [x] 限流保护
- [x] 企业共享资料库
- [x] 软删除系统