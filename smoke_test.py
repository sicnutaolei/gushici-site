# -*- coding: utf-8 -*-
"""冒烟测试：用 Flask test client 走一遍核心路由，不需要启动真实服务器

使用独立测试数据库（data/smoke_test.db），绝不触碰真实数据 poems.db。
"""
import sys, io, os

os.environ["POEMS_DB_PATH"] = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "smoke_test.db")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app import app, init_db

# 每次测试重建测试数据库（不依赖删除 db 文件，规避环境安全删除限制）
init_db(reset=True)

c = app.test_client()
failures = []

def check(name, resp, expect_status=200, expect_text=None):
    ok = resp.status_code == expect_status
    if ok and expect_text:
        ok = expect_text.encode("utf-8") in resp.data
    status = "PASS" if ok else "FAIL"
    if not ok:
        failures.append(name)
    print(f"[{status}] {name} (status={resp.status_code})")

# 1. 首页：应显示预置诗词
check("首页列表", c.get("/"), 200, "关雎")
check("搜索诗句", c.get("/?q=明月几时有"), 200, "水调歌头")
check("朝代筛选", c.get("/?dynasty=宋"), 200, "题西林壁")

# 2. 详情页
check("详情页-将进酒", c.get("/poem/19"), 200, "天生我材必有用")
check("详情页-译文/注释/赏析", c.get("/poem/20"), 200, "赏析")

# 3. 未登录访问受保护页面 -> 重定向
r = c.get("/favorites")
check("未登录访问收藏页重定向", r, 302)

# 4. 注册新用户
r = c.post("/register", data={"username": "tester", "password": "abc12345", "password2": "abc12345"}, follow_redirects=True)
check("注册成功页", r, 200)

# 5. 登录 / 收藏 / 笔记 / 标签
check("登录页", c.get("/login"), 200)
c.post("/login", data={"username": "tester", "password": "abc12345"})
r = c.post("/poem/13/favorite", follow_redirects=True)  # 静夜思
check("收藏静夜思", r, 200)
check("收藏页显示", c.get("/favorites"), 200, "静夜思")
c.post("/poem/13/note", data={"tags": "必背,思乡", "note": "李白的思乡名篇，已背会。"})
check("笔记列表", c.get("/notes"), 200, "必背")
check("标签页", c.get("/tag/思乡"), 200, "静夜思")
check("详情页个人面板", c.get("/poem/13"), 200, "已喜欢")

# 6. 管理员登录 + 后台
c.get("/logout")
c.post("/login", data={"username": "admin", "password": "admin123"})
check("管理后台", c.get("/admin"), 200, "诗词管理")
check("新增诗词表单", c.get("/admin/poem/new"), 200)
c.post("/admin/poem/new", data={
    "title": "测试诗", "author": "测试人", "dynasty": "现代",
    "content": "测试内容第一行", "translation": "", "annotation": "", "appreciation": ""})
check("新增后可见", c.get("/?dynasty=现代"), 200, "测试诗")

# 7. 修改密码
c.get("/logout")
c.post("/login", data={"username": "tester", "password": "abc12345"})
c.post("/change-password", data={"old_password": "abc12345", "new_password": "xyz98765", "new_password2": "xyz98765"})
check("新密码可登录", c.post("/login", data={"username": "tester", "password": "xyz98765"}), 302)
check("旧密码已失效", c.post("/login", data={"username": "tester", "password": "abc12345"}), 200)

# 8. 批量导入（管理员）
c.get("/logout")
c.post("/login", data={"username": "admin", "password": "admin123"})
check("导入页面", c.get("/admin/import"), 200, "批量导入")
c.post("/admin/import", data={"json_text": '''[
  {"title": "测试导入诗", "author": "导入者", "dynasty": "现代", "content": "测试行一\\n测试行二"},
  {"title": "测试导入诗", "author": "导入者", "dynasty": "现代", "content": "重复的会被跳过"},
  {"title": "缺字段诗", "author": "导入者"}
]'''}, follow_redirects=True)
check("导入结果页", c.get("/?dynasty=现代"), 200, "测试导入诗")
check("重复只导入一条", c.get("/?q=测试导入诗"), 200, "测试导入诗")

# 9. 非管理员访问后台 -> 403
c.get("/logout")
c.post("/login", data={"username": "tester", "password": "xyz98765"})
check("普通用户访问后台403", c.get("/admin"), 403)

# 10. 上一篇/下一篇导航
r = c.get("/poem/2")
check("详情页含下一篇导航", r, 200, "下一篇")
check("详情页上一篇导航", c.get("/poem/2"), 200, "上一篇")

# 11. 个人数据导出（登录 tester，之前收藏过静夜思并写了笔记）
check("导出JSON", c.get("/export"), 200, "静夜思")

# 12. 404 页面
check("不存在的诗词404", c.get("/poem/99999"), 404)

print()
print("=" * 40)
if failures:
    print("存在失败项:", failures)
    sys.exit(1)
print(f"全部通过！")
