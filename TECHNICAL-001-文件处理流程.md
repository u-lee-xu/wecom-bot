# TECHNICAL-001 - 企业微信文件处理流程

## 索引信息
- 索引号：T001
- 日期：2026-02-11
- 类型：技术文档

---

## 一、整体流程图

```
用户发送文件
    ↓
企业微信回调
    ↓
接收并解密消息 (WXBizJsonMsgCrypt)
    ↓
提取文件 URL
    ↓
下载文件 (file_downloader.download_file)
    ├─ 下载原始加密文件
    ├─ 计算 SHA256 哈希
    ├─ 保存为哈希文件名
    └─ 检测是否加密（自动解密）
    ↓
解密文件 (file_downloader.decrypt_file)
    └─ AES-CBC 解密
    ↓
保存文件映射关系 (database.save_file_mapping)
    ├─ hash_filename: 哈希文件名
    ├─ original_filename: 原始文件名
    └─ user_id: 用户ID
    ↓
记录到数据库 (database.log_message)
    ├─ user_id: 用户ID
    ├─ message_type: image_message/file_message
    ├─ content: 文件信息和路径
    └─ file_path: 文件路径
    ↓
保存到会话 (session_manager.save_user_file)
    ├─ file_type: image/file
    ├─ file_path: 文件路径
    └─ original_filename: 原始文件名
    ↓
用户发送文本（或引用文件）
    ↓
附加文件信息到消息
    ├─ 优先使用引用的文件
    ├─ 否则查询最近文件
    └─ 获取原始文件名
    ↓
发送给 AI 处理
    └─ AI 读取文件并返回结果
```

---

## 二、详细流程分析

### 2.1 消息接收和解密

**文件：** `app.py`, `WXBizJsonMsgCrypt.py`

**流程：**
1. 企业微信向 `/callback` 发送 POST 请求
2. 获取加密消息数据
3. 获取 msg_signature, timestamp, nonce 参数
4. 使用 `WXBizJsonMsgCrypt` 解密消息：
   ```python
   wxcpt = WXBizJsonMsgCrypt(TOKEN, EncodingAES_KEY, '')
   ret, decrypted_msg = wxcpt.DecryptMsg(data, msg_signature, timestamp, nonce)
   ```
5. 解析 JSON 消息，提取 msgtype（text/image/file/stream）
6. 检测是否有引用信息（quote字段）

---

### 2.2 文件下载和解密

**文件：** `file_downloader.py`

#### 2.2.1 下载文件 (`download_file`)

**输入参数：**
- `file_url`: 文件 URL
- `filename`: 可选的原始文件名
- `aes_key_base64`: AES 密钥（Base64 编码）

**处理步骤：**
1. 使用 `requests.get()` 下载文件
2. 计算文件内容的 SHA256 哈希（取前 16 位）
3. 提取原始文件名（从 URL 或 Content-Disposition）
4. 生成哈希文件名：`{hash}{extension}`
5. 检查文件是否已存在：
   - 如果存在，直接返回现有文件路径
   - 如果存在解密版本，返回解密版本
6. 保存原始加密文件
7. **检测文件头判断是否需要解密：**
   ```python
   first_4_bytes = file_content[:4]
   if first_4_bytes == b'\xf6\x4d\x2a\x28':  # 企业微信图片
       需要解密
   elif first_4_bytes == b'\x7b\x1a\x7a\x03':  # 企业微信文件
       需要解密
   ```
8. 如果检测到加密文件，调用 `decrypt_file` 自动解密
9. 返回解密后的文件路径

**返回值：**
```python
{
    'hash_path': '/home/pi/wecom/downloads/xxx_decrypted.pdf',
    'original_filename': 'paper.pdf',
    'hash_filename': 'xxx_decrypted.pdf'
}
```

#### 2.2.2 解密文件 (`decrypt_file`)

**处理步骤：**
1. 读取加密数据
2. Base64 解码 AES 密钥
3. 提取 IV（密钥前 16 字节）
4. AES-CBC 解密
5. 去除 PKCS#7 填充
6. 保存为 `*_decrypted.{ext}`
7. 返回解密文件路径

---

### 2.3 数据库和文件映射

#### 2.3.1 文件映射表 (`file_mappings`)

**表结构：**
```sql
CREATE TABLE file_mappings (
    hash_filename TEXT PRIMARY KEY,  -- 哈希文件名
    original_filename TEXT NOT NULL,  -- 原始文件名
    user_id TEXT NOT NULL,            -- 用户 ID
    first_seen TIMESTAMP,            -- 首次上传时间
    last_seen TIMESTAMP              -- 最后访问时间
)
```

#### 2.2.2 文件消息表 (`messages`)

**表结构：**
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL,
    message_type TEXT NOT NULL,        -- user_message/bot_message/image_message/file_message
    content TEXT,                     -- 消息内容或文件信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**文件消息内容格式：**
```
图片: https://example.com/image.jpg | [文件路径: downloads/xxx_decrypted.jpg | 文件名: paper.jpg]
```

#### 2.3.3 文件映射关联

**场景 1：直接发送图片**
```
用户发送图片 "photo.jpg"
    ↓
下载为：a1b2c3d4e5f6g7h8.jpg（加密）
    ↓
解密为：a1b2c3d4e5f6g7h8_decrypted.jpg
    ↓
保存映射：
  hash_filename: a1b2c3d4e5f6g7h8_decrypted.jpg
  original_filename: photo.jpg
  user_id: XuLi
    ↓
保存消息：
  message_type: image_message
  content: "图片: ... | [文件路径: downloads/xxx_decrypted.jpg | 文件名: photo.jpg]"
```

**场景 2：引用图片**
```
用户发送文本并引用图片
    ↓
下载引用图片：b2c3d4e5f6g7h8i9.jpg（加密）
    ↓
解密为：b2c3d4e5f6g7h8i9_decrypted.jpg
    ↓
保存映射：
  hash_filename: b2c3d4e5f6g7h8i9_decrypted.jpg
  original_filename: avatar.jpg
  user_id: XuLi
    ↓
保存消息：
  message_type: image_message
  content: "引用图片: ... | [文件路径: downloads/xxx_decrypted.jpg | 文件名: avatar.jpg]"
```

**场景 3：文件去重**
```
用户发送同一文件两次 "paper.pdf"
    ↓
第一次：
  下载：3d4e5f6g7h8i9j0k.pdf（加密）
  解密：3d4e5f6g7h8i9j0k_decrypted.pdf
  保存映射
    ↓
第二次：
  计算哈希相同：3d4e5f6g7h8i9j0k
  文件已存在，复用：3d4e5f6g7h8i9j0k_decrypted.pdf
  更新映射的 last_seen 时间
```

---

### 2.4 消息处理和 AI 交互

#### 2.4.1 文本消息处理（带引用）

**代码位置：** `app.py` 第 230-340 行

**流程：**
1. 接收文本消息
2. 检测是否有引用消息（quote 字段）
3. 如果有引用图片：
   - 下载引用图片（传入 AES 密钥）
   - 自动解密
   - 保存文件映射
   - 记录到数据库
   - 保存到会话
4. 附加文件信息到消息：
   ```python
   file_info = f"\n\n[用户引用的图片]\n类型: image\n路径: {file_path}\n文件名: {display_filename}"
   ```
5. 发送给 AI 处理

#### 2.4.2 文件消息处理

**代码位置：** `app.py` 第 550-610 行

**流程：**
1. 接收文件消息
2. 下载文件（传入 AES 密钥）
3. 自动解密（如果是加密文件）
4. 保存文件映射
5. 保存到数据库
6. 保存到会话
7. 发送自动回复："收到图片了！"
8. 用户后续发送"分析图片"指令时，附加文件信息

#### 2.4.3 AI 处理流程

**文件：** `file_processor.py`

**流程：**
1. AI 收到带文件信息的消息
2. 提取文件路径
3. 使用工具读取文件内容
4. 分析并返回结果

**消息格式：**
```
我来读取并分析这个PDF文档。

- 文件名: sensors-26-00436.pdf
- 文件大小: 1.2 MB
- 文件格式: .pdf
- 文件路径: downloads/xxx_decrypted.pdf

请使用适当的工具读取这个文档文件的内容，并进行分析。
```

---

## 三、关键数据流

### 3.1 文件哈希去重

**目的：** 避免重复下载相同内容的文件

**机制：**
- 使用 SHA256 哈希（前 16 位）作为文件名
- 相同内容的文件会得到相同的哈希值
- 下载前检查文件是否已存在

**示例：**
```
用户发送 "paper.pdf"（8.7MB）
  ↓
计算哈希：a1b2c3d4e5f6g7h8
  ↓
保存为：a1b2c3d4e5f6g7h8.pdf
  ↓
用户再次发送 "paper.pdf"
  ↓
计算哈希：a1b2c3d4e5f6g7h8（相同）
  ↓
文件已存在，复用：a1b2c3d4e5f6g7h8.pdf
```

### 3.2 文件名映射查询

**场景：** AI 查询用户上传的文件

**查询流程：**
```python
# 1. 查询最近的文件消息
recent_file = db_manager.get_recent_file_message(user_id)
# 返回：{file_type: 'file', file_path: 'downloads/xxx.pdf', filename: 'xxx.pdf'}

# 2. 提取哈希文件名
hash_filename = os.path.basename(file_path)  # xxx.pdf

# 3. 查询原始文件名
original_filename = db_manager.get_original_filename(hash_filename)
# 返回：'sensors-26-00436.pdf'

# 4. 附加到消息
file_info = f"[用户最近发送的文件]\n类型: {file_type}\n路径: {file_path}\n文件名: {original_filename}"
```

### 3.3 引用图片优先级

**规则：** 引用的图片优先于数据库中的最近文件

**实现：**
```python
if quoted_image_path:
    # 优先使用引用的图片
    file_info = f"[用户引用的图片]\n类型: image\n路径: {quoted_image_path}\n文件名: {display_filename}"
else:
    # 查询数据库中最新的文件
    recent_file = db_manager.get_recent_file_message(user_id)
    if recent_file:
        file_info = f"[用户最近发送的文件]\n类型: {recent_file['file_type']}\n路径: {file_path}\n文件名: {display_filename}"
```

---

## 四、代码文件职责

| 文件 | 职责 |
|------|------|
| `app.py` | 主应用，处理企业微信回调、消息路由、文件处理流程控制 |
| `WXBizJsonMsgCrypt.py` | 企业微信官方加密库，消息加解密 |
| `file_downloader.py` | 文件下载、哈希去重、自动解密 |
| `database.py` | 数据库管理、文件映射存储、消息记录 |
| `session_manager.py` | 会话管理、用户文件存储 |
| `file_processor.py` | 文件内容提取、格式化描述 |

---

## 五、关键常量和配置

| 配置项 | 值 | 说明 |
|--------|---|------|
| `WECOM_TOKEN` | `1V7LcV` | 企业微信验证 Token |
| `WECOM_ENCODING_AES_KEY` | `FiUqLuCmTJtjEQuchGqmGm5gx82d9vj98yl59rjMKsR` | 企业微信 AES 密钥 |
| `download_dir` | `downloads` | 文件下载目录 |
| `hash_length` | 16 | SHA256 哈希取前 16 位 |
| `message_cache_ttl` | 60 秒 | 消息去重时间窗口 |

---

## 六、加密文件头识别

| 文件类型 | 文件头 | 解密后文件头 |
|---------|--------|--------------|
| 企业微信图片 | `f6 4d 2a 28` | `ff d8 ff e1` (JPEG) |
| 企业微信文件 | `7b 1a 7a 03` | `25 50 44 46` (PDF) |
| 标准 PDF | `25 50 44 46` | - |
| 标准 JPEG | `ff d8 ff e1` | - |

---

## 七、数据库表结构

### 7.1 file_mappings 表

| 字段 | 类型 | 说明 |
|------|------|------|
| hash_filename | TEXT (PK) | 哈希文件名（主键） |
| original_filename | TEXT | 原始文件名 |
| user_id | TEXT | 用户 ID |
| first_seen | TIMESTAMP | 首次上传时间 |
| last_seen | TIMESTAMP | 最后访问时间 |

### 7.2 messages 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER (PK) | 消息 ID |
| user_id | TEXT | 用户 ID |
| message_type | TEXT | 消息类型 |
| content | TEXT | 消息内容 |
| created_at | TIMESTAMP | 创建时间 |

### 7.3 user_sessions 表

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT (PK) | 用户 ID |
| session_id | TEXT | 会话 ID |
| created_at | TIMESTAMP | 创建时间 |
| last_active | TIMESTAMP | 最后活跃时间 |
| message_count | INTEGER | 消息计数 |

---

## 八、常见场景流程

### 8.1 场景：发送图片并分析

```
用户发送图片 "photo.jpg"
    ↓
接收 image 消息
    ↓
下载：a1b2c3d4e5f6g7h8.jpg（加密）
    ↓
解密：a1b2c3d4e5f6g7h8_decrypted.jpg
    ↓
保存映射：a1b2c3d4e5f6g7h8_decrypted.jpg → photo.jpg
    ↓
记录消息：image_message
    ↓
自动回复："收到图片了！"
    ↓
用户发送："分析图片"
    ↓
附加文件信息到消息
    ↓
AI 读取图片并分析
    ↓
返回分析结果
```

### 8.2 场景：引用之前的图片

```
用户发送文本并引用图片 "分析这张图片"
    ↓
检测到引用图片
    ↓
下载引用图片：b2c3d4e5f6g7h8i9.jpg（加密）
    ↓
解密：b2c3d4e5f6g7h8i9_decrypted.jpg
    ↓
保存映射：b2c3d4e5f6g7h8i9_decrypted.jpg → avatar.jpg
    ↓
记录消息：image_message
    ↓
附加引用图片信息到消息
    ↓
AI 读取引用图片并分析
    ↓
返回分析结果
```

### 8.3 场景：发送 PDF 并分析

```
用户发送 PDF "paper.pdf"
    ↓
接收 file 消息
    ↓
下载：c3d4e5f6g7h8i9j0k.pdf（加密）
    ↓
解密：c3d4e5f6g7h8i9j0k_decrypted.pdf
    ↓
保存映射：c3d4e5f6g7h8i9j0k_decrypted.pdf → paper.pdf
    ↓
记录消息：file_message
    ↓
自动回复："收到图片了！"（待优化）
    ↓
用户发送："分析这篇论文"
    ↓
附加文件信息到消息
    ↓
AI 读取 PDF 并分析
    ↓
返回分析结果
```

---

## 九、待优化项

- [ ] 文件接收回复消息（PDF 文件应该显示"收到文件了！"而不是"收到图片了！"）
- [ ] 文件处理失败时的错误提示优化
- [ ] 支持更多文件格式（DOCX, XLSX 等）
- [ ] 文件大小限制和分批处理
- [ ] 旧文件自动清理策略
- [ ] 文件访问权限控制