# 赴日工作信息监测系统

一个定时运行的赴日工作相关信息监测工具，自动检测政策变化、新职位和中介名录变动，并通过 Hermes 推送到您的邮箱和 Discord。

## 📋 功能概述

本系统监测三类信息：

| 类型 | 内容 | 监测方式 | 推送条件 |
|------|------|----------|----------|
| **A 类** | 日本官方政策/签证 | 页面变化监测 | 命中关键词才推送 |
| **B 类** | 招聘职位信息 | 邮箱解析 | 新职位即推送 |
| **C 类** | 中介资质/名录 | 页面变化监测 | 有变化就推送 |

## 🚀 快速开始

### 1. 安装依赖

```bash
# 进入项目目录
cd japan-job-monitor

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入您的配置
nano .env
```

需要填写的内容：

```ini
# 邮箱 IMAP 配置（用于接收求职提醒邮件）
IMAP_SERVER=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=your-email@gmail.com
IMAP_PASSWORD=your-app-password

# Hermes 通知配置（暂时留空，使用占位实现）
# 等您提供 Hermes 接口方式后再填写
HERMES_API_URL=
HERMES_API_TOKEN=

# 日志级别
LOG_LEVEL=INFO
```

### 3. 检查配置文件

配置文件位于 `config/` 目录：

- `sources.yaml` - 信息源配置（可增删改查）
- `keywords.txt` - 关键词列表（每行一个）

您可以根据需要修改这些文件。

### 4. 手动测试运行

```bash
python main.py
```

首次运行时：
- 会自动创建 `monitor.db` 数据库
- 会抓取所有配置的源
- 通知会以"占位"形式打印到日志（因为 Hermes 尚未配置）

查看输出：
```bash
# 实时查看日志
tail -f monitor.log
```

### 5. 配置定时任务（crontab）

```bash
# 编辑 crontab
crontab -e

# 添加以下两行（每天 9:00 和 21:00 各运行一次）
0 9 * * * cd /path/to/japan-job-monitor && /usr/bin/python3 main.py >> monitor.log 2>&1
0 21 * * * cd /path/to/japan-job-monitor && /usr/bin/python3 main.py >> monitor.log 2>&1
```

**注意**：请将 `/path/to/japan-job-monitor` 替换为实际的项目路径。

验证 crontab：
```bash
crontab -l
```

## 📁 项目结构

```
japan-job-monitor/
├── main.py              # 主程序入口
├── storage.py           # 数据库操作
├── notifier.py          # 通知模块（对接 Hermes）
├── fetchers/            # 抓取模块
│   ├── __init__.py
│   ├── rss.py           # RSS 抓取
│   ├── page_change.py   # 页面变化监测
│   └── email_inbox.py   # 邮箱解析
├── config/
│   ├── sources.yaml     # 信息源配置
│   └── keywords.txt     # 关键词列表
├── .env                 # 环境变量（密钥，不进 git）
├── .env.example         # 环境变量示例
├── .gitignore
├── requirements.txt     # Python 依赖
├── monitor.db           # SQLite 数据库（运行后生成）
├── monitor.log          # 日志文件
└── README.md            # 本文件
```

## ⚙️ 配置说明

### sources.yaml

每个信息源包含以下字段：

```yaml
- name: "来源名称"        # 自定义名称
  type: page_change      # 类型：page_change / rss / email
  url: "https://..."     # 网址
  channel: both          # 推送渠道：email / discord / both
  note: "备注说明"       # 可选备注
```

### keywords.txt

一行一个关键词，A 类政策内容命中任一关键词才会推送。

初始关键词：
```
特定技能
育成就労
育成就労制度
技能実習
在留資格
外国人雇用
介護
外食
建設
N4
N5
JFT-Basic
```

## 🔧 故障排查

### 问题 1：某个源抓取失败

查看日志中的错误信息：
```bash
grep "ERROR" monitor.log
```

可能原因：
- 网站临时不可达 → 程序会自动跳过，继续处理其他源
- URL 已变更 → 更新 `sources.yaml` 中的 URL
- robots.txt 禁止 → 请更换为允许的源

### 问题 2：邮箱连接失败

检查 `.env` 中的 IMAP 配置：
- 确认 IMAP 服务器地址和端口正确
- 某些邮箱需要使用"应用专用密码"而非登录密码
- 确认防火墙允许出站连接到 IMAP 端口

### 问题 3：重复收到同一条通知

这可能是去重逻辑有问题。检查数据库：
```bash
sqlite3 monitor.db "SELECT * FROM seen_items ORDER BY first_seen DESC LIMIT 10;"
```

### 问题 4：程序崩溃

查看完整错误堆栈：
```bash
tail -100 monitor.log
```

常见问题：
- 缺少依赖 → `pip install -r requirements.txt`
- 配置文件格式错误 → 检查 YAML 语法
- 权限问题 → 确保对目录有读写权限

## 📊 数据库查询

查看已记录的条目：
```bash
sqlite3 monitor.db "SELECT source_name, item_type, title, first_seen FROM seen_items ORDER BY first_seen DESC LIMIT 20;"
```

按来源统计：
```bash
sqlite3 monitor.db "SELECT source_name, COUNT(*) as count FROM seen_items GROUP BY source_name;"
```

清空数据库（谨慎使用）：
```bash
sqlite3 monitor.db "DELETE FROM seen_items;"
```

## 🔐 安全提示

1. **永远不要将 `.env` 文件提交到 git** - 已配置在 `.gitignore` 中
2. **定期备份 `monitor.db`** - 避免数据丢失
3. **使用应用专用密码** - 不要在 `.env` 中使用邮箱主密码

## ❓ 待确认事项

### Hermes 接口方式

目前通知模块使用**占位实现**（仅打印到日志）。要启用真实通知，请提供：

1. **Hermes 的调用方式**：
   - HTTP API？请提供 endpoint 和请求格式
   - CLI 命令？请提供命令格式
   - 或其他方式？

2. **专用邮箱的 IMAP 信息**：
   - IMAP 服务器地址
   - 端口
   - 账号和密码（或应用专用密码）

3. **是否需要日文翻译功能**：
   - 如需开启，请提供翻译 API 的配置

## 📝 更新日志

- v1.0.0 - 初始版本
  - 支持页面变化监测
  - 支持邮箱解析
  - 支持 RSS 抓取
  - 关键词过滤
  - SQLite 去重存储
  - 占位通知实现

## 📄 许可证

本项目供个人使用。
