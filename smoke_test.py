# -*- coding: utf-8 -*-
"""冒烟测试：用 Flask test client 走一遍核心路由，不需要启动真实服务器"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app import app

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

# 7. 非管理员访问后台 -> 403
c.get("/logout")
c.post("/login", data={"username": "tester", "password": "abc12345"})
check("普通用户访问后台403", c.get("/admin"), 403)

# 8. 404 页面
check("不存在的诗词404", c.get("/poem/99999"), 404)

print()
print("=" * 40)
if failures:
    print("存在失败项:", failures)
    sys.exit(1)
print(f"全部通过！")
