# 拾遗集 —— 我的古诗词学习记录网站

仿古诗文网（gushiwen.cn）风格的个人古诗词网站：记录自己**学习过的**和**喜欢的**古诗词。
宣纸底色 + 楷体标题 + 朱砂红点缀的古典中国风界面。

## 功能

- **诗词库**：内置 70 首经典诗词（原文 / 译文 / 注释 / 赏析），预置先秦至清代名篇
- **注册登录**：支持多用户，每人有独立的收藏和笔记
- **我的喜欢**：一键收藏，单独页面查看
- **标签 + 学习笔记**：给诗词打自定义标签（如"必背""已背会""思乡"），写个人学习心得
- **搜索**：按标题 / 作者 / 诗句全文检索，支持按朝代筛选
- **修改密码**：登录后右上角「改密码」
- **数据导出**：一键把收藏 / 标签 / 笔记导出为 JSON 备份
- **学习统计**：收藏数 / 笔记数 / 标签分布 / 朝代分布可视化
- **管理后台**：默认管理员可增删改诗词、批量导入 JSON、管理用户

## 默认管理员

| 用户名 | 密码 |
|--------|------|
| admin | admin123 |

首次登录后请通过右上角「改密码」尽快修改。

## 批量导入诗词

管理后台 →「批量导入」，支持粘贴 JSON 或上传 .json 文件：

```json
[
  {
    "title": "枫桥夜泊",
    "author": "张继",
    "dynasty": "唐",
    "content": "月落乌啼霜满天，江枫渔火对愁眠。\n姑苏城外寒山寺，夜半钟声到客船。",
    "translation": "……",
    "annotation": "……",
    "appreciation": "……"
  }
]
```

必填：`title` / `author` / `dynasty` / `content`；可选：`translation` / `annotation` / `appreciation`。
标题+作者已存在的自动跳过，不会重复导入。

## Docker 部署（推荐）

```bash
# 构建并启动（首次启动自动建库、导入预置诗词、创建管理员）
docker compose up -d --build

# 查看日志确认启动成功
docker compose logs -f
```

访问 `http://<主机IP>:8080` 即可。端口在 `docker-compose.yml` 中修改。

### 数据持久化

SQLite 数据库保存在宿主机 `./data/poems.db`（volume 挂载），删除容器不丢数据。
备份只需复制 `data/` 目录。

### 常用命令

```bash
docker compose down          # 停止（数据保留）
docker compose up -d --build # 重新构建并启动
```

## 本地开发运行（不用 Docker）

```bash
pip install -r requirements.txt
python app.py    # 访问 http://127.0.0.1:5000
```

## 环境变量

| 变量 | 说明 |
|------|------|
| SECRET_KEY | Flask 会话密钥，生产环境务必设置随机长字符串 |
| 端口 | 由 docker-compose.yml 的 ports 映射决定 |

## 技术栈

- 后端：Python Flask + Flask-SQLAlchemy
- 数据库：SQLite（单文件，零运维）
- 部署：Docker + gunicorn
- 前端：原生 HTML/CSS，无 JS 框架依赖

## 目录结构

```
gushici-site/
├── app.py              # Flask 主应用（路由、认证、管理）
├── models.py           # 数据模型：User / Poem / UserPoem
├── seed_data.py        # 预置诗词汇总（seed_data1/2.py）
├── templates/          # 页面模板
├── static/style.css    # 古风样式
├── data/               # SQLite 数据库（自动生成）
├── Dockerfile
└── docker-compose.yml
```
