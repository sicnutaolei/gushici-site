# 部署教程（飞牛 NAS / 任意 Docker 主机）

本教程面向**完全没有 Docker 经验**的情况，一步步把「拾遗集」跑起来。
全程需要用到的只有：SSH 工具 + 几条复制粘贴的命令。

> 如果你之前部署过工资系统（`salary-docker`），本教程的目录和做法完全一致，
> 可以直接照搬，只需把路径换成 `gushici-docker`。

---

## 一、部署前准备

| 项目 | 要求 | 如何确认 |
|------|------|----------|
| Docker | NAS 已安装「Docker」套件并启动 | SSH 里执行 `docker version` 能看到版本号 |
| 端口 | 本方案用 **8080**，需未被占用 | `sudo ss -tlnp \| grep 8080` 无输出即空闲 |
| 内存 | ≥ 512MB 空闲 | 镜像约 150MB，运行占 80-120MB |
| SSH 工具 | 任意（Windows Terminal / PuTTY / Xshell） | 能登录 NAS 即可 |

> **飞牛提示**：飞牛上 `docker` 命令一般需要 `sudo` 提权，所以下文命令都带 `sudo`。
> 如果你的环境 `docker ps` 不加 sudo 也能用，就去掉 sudo 即可。

选定部署目录（和工资系统同级）：

```bash
DEPLOY_DIR=/vol1/1000/docker/gushici-docker
```

---

## 二、方式一：git clone 部署（推荐，后续升级最省事）

### 1. 克隆代码

```bash
sudo mkdir -p /vol1/1000/docker
cd /vol1/1000/docker
sudo git clone git@github.com:sicnutaolei/gushici-site.git gushici-docker
cd gushici-docker
```

> 仓库是**私有**的。若 NAS 没配 GitHub SSH key 会报权限错误，有两种解法：
> - 把 NAS 的公钥（`cat ~/.ssh/id_rsa.pub`）加到 GitHub → Settings → SSH keys；
> - 或者改用方式二（上传文件），完全绕开 git。

### 2. 修改密钥（重要）

```bash
sudo sed -i "s|please-change-this-secret-key|$(openssl rand -hex 32)|" docker-compose.yml
```

确认改成功了：

```bash
grep SECRET_KEY docker-compose.yml   # 应显示一长串随机字符，而不是 please-change
```

### 3. 后台构建并启动（防 SSH 断线）

```bash
sudo nohup docker compose up -d --build > build.log 2>&1 &
```

> **为什么用 nohup**：首次构建要装 Python 依赖，可能几分钟。
> 直接前台跑的话 SSH 一断构建就中断。后台跑可以放心关掉窗口。

查看构建进度：

```bash
tail -f build.log        # Ctrl+C 退出查看（不会中断构建）
```

看到类似 `Container gushici-site Started` 即完成。

### 4. 确认运行状态

```bash
sudo docker ps --filter name=gushici-site
sudo docker logs gushici-site --tail 20
```

正常日志里应有：

```
[init] 已创建默认管理员：admin / admin123（请登录后修改密码）
[init] 已导入预置诗词 70 首
```

浏览器打开 **http://NAS的IP:8080** 即可访问。

---

## 三、方式二：上传文件部署（NAS 没配 git 时用）

在本机（Windows）打包：

```powershell
cd C:\Users\Administrator\WorkBuddy\WB\gushici-site
# 排除虚拟环境和本地数据库
Compress-Archive -Path app.py, models.py, seed_data.py, seed_data1.py, seed_data2.py, `
  requirements.txt, Dockerfile, docker-compose.yml, .dockerignore, templates, static `
  -DestinationPath gushici.zip -Force
```

然后：

1. 飞牛「文件管理」→ 进入 `/vol1/1000/docker/` → 新建文件夹 `gushici-docker`
2. 上传 `gushici.zip` 到该目录 → 右键「解压到当前文件夹」
3. SSH 登录 NAS，执行：

```bash
cd /vol1/1000/docker/gushici-docker
ls    # 应能看到 app.py、Dockerfile、templates 等
sudo sed -i "s|please-change-this-secret-key|$(openssl rand -hex 32)|" docker-compose.yml
sudo nohup docker compose up -d --build > build.log 2>&1 &
```

---

## 四、首次使用

1. 打开 `http://NAS的IP:8080`
2. 用默认管理员登录：

| 用户名 | 密码 |
|--------|------|
| admin | admin123 |

3. **立刻改密码**：右上角「改密码」
4. 日常使用建议注册一个自己的普通账号，管理员账号只用于管理后台（增删诗词、管理用户）

---

## 五、数据备份与恢复

所有个人数据（账号、收藏、标签、笔记）都在一个 SQLite 文件里：

```
/vol1/1000/docker/gushici-docker/data/poems.db
```

**备份**（建议加进你的定期备份任务）：

```bash
cd /vol1/1000/docker/gushici-docker
sudo cp data/poems.db data/poems.db.bak.$(date +%Y%m%d)
```

**恢复**：停容器 → 用备份文件覆盖 `data/poems.db` → 启动容器

```bash
sudo docker compose down
sudo cp data/poems.db.bak.20260909 data/poems.db
sudo docker compose up -d
```

**另外一重保险**：网站内置「导出」功能（统计页 → 导出我的数据 JSON），
可以把个人的收藏/标签/笔记单独导出成 JSON 文件，即使数据库损坏也能保住你的笔记。

---

## 六、升级到新版本

方式一（git 部署）只需三条命令，数据不会丢：

```bash
cd /vol1/1000/docker/gushici-docker
sudo git pull
sudo nohup docker compose up -d --build > build.log 2>&1 &
```

方式二（上传部署）：重新打包上传覆盖源文件，再执行同样的 `up -d --build`。

---

## 七、常见问题排查

| 症状 | 原因 | 解决办法 |
|------|------|----------|
| `docker: command not found` / 权限被拒 | 没装 Docker 套件或没提权 | 装套件；命令前加 `sudo` |
| `Permission denied (publickey)` | NAS 没配 GitHub SSH key | 改用方式二，或给 NAS 配 SSH key |
| 构建卡在 `pip install` 很久 | 网络慢 | 等，或看 `tail -f build.log`；已用清华源，通常 1-3 分钟 |
| `Error response from daemon: pull ... denied` | 镜像源 401（飞牛内置源常见问题） | 换镜像源：编辑 `/etc/docker/daemon.json` 配置加速器，重启 Docker |
| 端口打不开 | 8080 被占用或防火墙 | 改端口：`docker-compose.yml` 里把 `8080:5000` 改成 `9090:5000` |
| 构建中途断线 | SSH 会话被切断 | 已用 `nohup ... &` 可避免；断线后重连看 `tail build.log` 是否仍在跑 |
| 打开是空白/502 | 容器还没起来 | `sudo docker logs gushici-site --tail 50` 看报错 |
| 登录后总是被登出 | SECRET_KEY 每次重建都变 | 已用 sed 固定写入 compose，确认没改回默认值 |
| 每日一诗到早上 8 点才换 | 时区问题 | 确认 compose 里有 `- TZ=Asia/Shanghai` |
| 数据目录是空的 | volume 没挂载 | `sudo docker inspect gushici-site \| grep -A3 Mounts` 检查 |

---

## 八、可选：改端口 / 反代访问

**改端口**：编辑 `docker-compose.yml`

```yaml
ports:
  - "9090:5000"     # 左边改成你想要的端口
```

然后 `sudo docker compose up -d` 生效。

**用飞牛的反代做子路径访问**（如 `thirsty.fnos.net/gushi/`）：
当前版本按根路径设计，子路径需要额外改造（Flask 需要挂载 URL 前缀）。
如果只是内网用，直接 `IP:端口` 最简单；确实需要子路径的话告诉我，我加一个前缀中间件支持。

---

## 九、一键速查（复制粘贴用）

```bash
# 全新部署
DEPLOY_DIR=/vol1/1000/docker/gushici-docker
sudo mkdir -p /vol1/1000/docker && cd /vol1/1000/docker
sudo git clone git@github.com:sicnutaolei/gushici-site.git gushici-docker && cd gushici-docker
sudo sed -i "s|please-change-this-secret-key|$(openssl rand -hex 32)|" docker-compose.yml
sudo nohup docker compose up -d --build > build.log 2>&1 &
tail -f build.log

# 日常运维
sudo docker ps --filter name=gushici-site      # 看状态
sudo docker logs gushici-site --tail 20        # 看日志
sudo docker compose restart                    # 重启
sudo docker compose down                       # 停止（数据保留）
```
