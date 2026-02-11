# MEMORY-004 - 失败尝试

## 索引信息
- 索引号：M004
- 日期：2026-02-10
- 类型：失败尝试

---

## 一、Git 推送失败

### 1.1 任务
将本地代码推送到 GitHub 仓库

### 1.2 尝试方法
1. 使用 `git push` 命令推送
2. 尝试 HTTPS 方式推送
3. 尝试设置超时参数

### 1.3 失败原因
- 树莓派网络连接 GitHub 的 git 协议超时
- 网络不稳定导致推送失败

### 1.4 解决方案
- 使用 GitHub API 直接创建初始提交
- 后续可以考虑：
  - 使用 SSH 方式（已配置密钥）
  - 使用代理加速
  - 等待网络条件改善后推送

### 1.5 经验教训
- 在网络条件不稳定时，优先使用 API 而非 git 命令
- 预先配置好 SSH 密钥备用

---

## 二、Ripgrep (rg) 未安装

### 2.1 问题
尝试使用 `rg` 命令搜索代码，发现未安装

### 2.2 影响
- 无法使用 ripgrep 进行高效代码搜索
- 需要使用其他工具替代（如 grep）

### 2.3 解决方案
- 安装 ripgrep：
  ```bash
  sudo apt install ripgrep
  ```

### 2.4 经验教训
- 开发前确认所有必需工具是否已安装
- 树莓派可能缺少一些常用工具

---

## 三、GitHub CLI (gh) 未安装

### 3.1 问题
尝试使用 `gh` 命令操作 GitHub，发现未安装

### 3.2 影响
- 无法使用 GitHub CLI 简化操作
- 需要使用 API 或 git 命令

### 3.3 解决方案
- 安装 GitHub CLI：
  ```bash
  sudo apt install gh
  # 或使用 curl 安装最新版本
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
  sudo apt update
  sudo apt install gh
  ```

### 3.4 经验教训
- GitHub CLI 可以简化很多操作，建议安装
- 树莓派可能需要手动安装最新版本

---

## 四、Docker 镜像下载时间长

### 4.1 问题
GitHub MCP Server Docker 镜像下载耗时超过 30 分钟

### 4.2 原因
- 镜像较大（约 500MB）
- 树莓派网络速度有限
- ARM64 架构可能需要特殊处理

### 4.3 解决方案
- 使用后台下载：`docker pull ... &`
- 考虑使用国内镜像源
- 考虑直接下载二进制文件

### 4.4 经验教训
- 大文件下载使用后台模式
- 预估下载时间，避免阻塞其他任务

---

## 五、网络连接 GitHub 不稳定

### 5.1 问题描述
树莓派连接 GitHub 经常超时，影响开发效率

### 5.2 受影响的操作
- git push/pull
- Docker 镜像下载
- npm 包安装
- GitHub API 调用（偶尔）

### 5.3 尝试的解决方案
- [ ] 使用 GitHub API（部分成功）
- [ ] 配置 SSH 密钥（已完成，待测试）
- [ ] 使用代理（未配置）
- [ ] 使用国内镜像源（未配置）

### 5.4 待解决的问题
1. 配置国内镜像源加速
2. 配置代理服务器
3. 优化网络配置

### 5.5 经验教训
- 树莓派开发需要考虑网络限制
- 准备多种备用方案
- 优先使用本地资源，减少网络依赖

---

## 六、避免的坑

### 6.1 企业微信相关
- ❌ 不要忽略消息加解密，必须使用官方库
- ❌ 不要假设 response_url 永久有效（1小时）
- ❌ 不要忘记处理事件排重（使用 msgid）
- ❌ 不要直接访问企业微信的图片/文件 URL（已加密）

### 6.2 iFlow CLI 相关
- ❌ 不要手动管理 iFlow 进程（SDK 自动管理）
- ❌ 不要使用固定的端口号（SDK 自动检测）
- ❌ 不要为每个消息创建新的 IFlowClient（复用实例）
- ❌ 不要忘记配置会话持久化

### 6.3 系统相关
- ❌ 不要忽略 ARM64 架构的兼容性问题
- ❌ 不要假设所有工具都已安装
- ❌ 不要在受限网络环境下执行大文件操作
- ❌ 不要忽略资源限制（内存、CPU）

---

## 七、待解决的问题

| 问题 | 优先级 | 状态 |
|------|--------|------|
| GitHub 网络连接不稳定 | 高 | 待解决 |
| ripgrep 未安装 | 中 | 待解决 |
| GitHub CLI 未安装 | 中 | 待解决 |
| 配置国内镜像源 | 中 | 待解决 |
| 配置代理服务器 | 低 | 待解决 |

---

## 八、图片/文档处理相关问题

### 8.1 事件循环冲突
- **问题：** `RuntimeError: There is no current event loop in thread`
- **原因：** Flask 同步线程中调用 `asyncio.get_event_loop().time()`
- **影响：** 图片处理失败，返回 500 错误
- **解决方案：** 使用 `time.time()` 代替 `asyncio.get_event_loop().time()`
- **经验教训：** Flask 是同步框架，不能直接使用 asyncio 的函数

### 8.2 文件作用域错误
- **问题：** `UnboundLocalError: cannot access local variable 'downloaded_path'`
- **原因：** 变量在使用前未定义
- **影响：** 文件处理失败
- **解决方案：** 先下载文件，再使用变量
- **经验教训：** 注意变量的定义顺序

### 8.3 AI 无法读取文件
- **问题：** AI 报告文件无法读取
- **原因：** 文件在发送给 AI 之前被清理（`cleanup_file`）
- **影响：** 无法分析 PDF 文档
- **解决方案：** 不自动清理文件，让 AI 可以读取
- **经验教训：** 文件处理流程中，要确保 AI 能访问文件

### 8.4 重复回复空白内容
- **问题：** AI 返回空白内容
- **原因：** 任务被取消（`StopReason.CANCELLED`）
- **影响：** 用户体验差
- **解决方案：** 增加任务超时处理
- **经验教训：** 需要处理异步任务的各种终止状态

### 8.5 数据库存储加密文件路径
- **问题：** 数据库保存的是加密文件路径，AI 无法读取
- **原因：** 没有正确保存解密后的文件路径
- **影响：** AI 分析失败
- **解决方案：** 保存解密后的文件路径
- **经验教训：** 要区分加密文件和解密文件

---

## 九、后续改进建议

1. **网络优化**
   - 配置国内镜像源（npm、docker、pip）
   - 配置代理服务器
   - 优化 DNS 解析

2. **工具完善**
   - 安装常用开发工具（ripgrep、gh 等）
   - 配置开发环境
   - 准备离线资源

3. **开发流程**
   - 优先使用本地资源
   - 批量处理网络请求
   - 使用异步/后台操作