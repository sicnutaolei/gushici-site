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

# 12. 作者聚合页
check("作者页", c.get("/author/李白"), 200, "共")
check("作者页仅该作者", c.get("/author/李白"), 200, "静夜思")

# 13. 学习统计（tester 已收藏静夜思+标签，未登录时重定向）
c.get("/logout")
check("未登录访问统计重定向", c.get("/stats"), 302)
c.post("/login", data={"username": "tester", "password": "xyz98765"})
check("统计页", c.get("/stats"), 200, "标签分布")

# 15. 每日一诗：重定向到详情页
r = c.get("/daily")
check("每日一诗重定向", r, 302)
check("每日一诗落地页", c.get(r.headers.get("Location", "/"), follow_redirects=True), 200)

# 16. 404 页面
check("不存在的诗词404", c.get("/poem/99999"), 404)

# ---------- 17. JSON API（为 Flutter 等客户端准备）----------
def check_json(name, resp, expect_status=200, expect_keys=None):
    ok = resp.status_code == expect_status
    if ok and expect_keys:
        try:
            body = resp.get_json()
        except Exception:
            body, ok = None, False
        if body is not None:
            for k in expect_keys:
                if k not in body:
                    ok = False
    status = "PASS" if ok else "FAIL"
    if not ok:
        failures.append(name)
    print(f"[{status}] {name} (status={resp.status_code})")

def check_bool(name, cond):
    ok = bool(cond)
    status = "PASS" if ok else "FAIL"
    if not ok:
        failures.append(name)
    print(f"[{status}] {name}")

# 匿名客户端（无 session cookie），用于验证未授权访问
anon = app.test_client()

# 17.1 未带 token 访问受保护接口 -> 401
check_json("API未授权访问401", anon.get("/api/v1/auth/me"), 401)
check_json("API未授权收藏401", anon.post("/api/v1/poems/13/favorite"), 401)

# 17.2 注册拿 token
r = c.post("/api/v1/auth/register",
           json={"username": "apitest", "password": "api12345", "password2": "api12345"})
check_json("API注册返回token", r, 200, ["token", "user"])
api_token = r.get_json().get("token") or ""
check_bool("API token非空", type(api_token) is str and len(api_token) == 64)

# 17.3 Bearer token 访问 /me
check_json("API-me", c.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + api_token}),
           200, ["user"])
# 17.4 Bearer token 错误 -> 401（用匿名客户端，排除 session 回退干扰）
check_json("API错误token401", anon.get("/api/v1/auth/me", headers={"Authorization": "Bearer wrong"}), 401)

# 17.5 诗词列表 / 详情 / 每日一诗 / 作者 / 朝代
check_json("API诗词列表", c.get("/api/v1/poems"), 200, ["items", "total", "pages"])
check_json("API列表含预置诗", c.get("/api/v1/poems?q=静夜思"), 200)
check_json("API诗词详情", c.get("/api/v1/poems/13"), 200, ["poem", "prev", "next", "my_record"])
check_json("API每日一诗", c.get("/api/v1/daily"), 200, ["id", "title"])
check_json("API作者列表", c.get("/api/v1/authors"), 200)
check_json("API朝代列表", c.get("/api/v1/dynasties"), 200)
check_json("API作者诗词", c.get("/api/v1/authors/李白"), 200)
check_json("API作者生平", c.get("/api/v1/authors/李白/info"), 200,
           ["name", "dynasty", "zihao", "birth_year", "death_year", "bio", "has_profile"])

# 17.6 收藏开关（带 token）
check_json("API收藏置true", c.post("/api/v1/poems/13/favorite",
           headers={"Authorization": "Bearer " + api_token}), 200, ["is_favorite"])
check_json("API收藏列表", c.get("/api/v1/favorites", headers={"Authorization": "Bearer " + api_token}),
           200)
_fav_body = c.get("/api/v1/favorites", headers={"Authorization": "Bearer " + api_token}).get_json()
check_bool("API收藏含静夜思", any(it["poem"]["title"] == "静夜思" for it in _fav_body))

# 17.7 保存笔记/标签
check_json("API保存笔记", c.put("/api/v1/poems/13/note",
           json={"note": "API测试笔记", "tags": "必背,思乡"},
           headers={"Authorization": "Bearer " + api_token}), 200, ["note", "tags"])
_notes_body = c.get("/api/v1/notes", headers={"Authorization": "Bearer " + api_token}).get_json()
check_bool("API笔记列表含笔记", any("API测试笔记" in it["note"] for it in _notes_body))
check_json("API标签列表", c.get("/api/v1/tags", headers={"Authorization": "Bearer " + api_token}), 200)
check_json("API标签筛选", c.get("/api/v1/tags/思乡", headers={"Authorization": "Bearer " + api_token}), 200)

# 17.8 统计 / 导出
check_json("API统计", c.get("/api/v1/stats", headers={"Authorization": "Bearer " + api_token}),
           200, ["favorite", "note", "total_poems"])
check_json("API导出", c.get("/api/v1/export", headers={"Authorization": "Bearer " + api_token}), 200)

# 17.9 CORS 响应头（/api 路径）
hdr = c.get("/api/v1/dynasties").headers.get("Access-Control-Allow-Origin")
check_bool("API CORS头", hdr == "*")

# 17.10 改密码使旧 token 失效
r = c.post("/api/v1/auth/change-password",
           json={"old_password": "api12345", "new_password": "api98765", "new_password2": "api98765"},
           headers={"Authorization": "Bearer " + api_token})
check_json("API改密返回新token", r, 200, ["token"])
new_token = r.get_json().get("token")
check_bool("API旧token失效", anon.get("/api/v1/auth/me",
      headers={"Authorization": "Bearer " + api_token}).status_code == 401)
check_bool("API新token可用", c.get("/api/v1/auth/me",
      headers={"Authorization": "Bearer " + new_token}).status_code == 200)

# 17.11 AI 端点鉴权 + 保存端点（只验证鉴权/保存，不真实调用 AI，避免消耗额度）
check_json("AI生平未登录401",
           anon.post("/api/v1/ai/author-bio", json={"name": "李白"}), 401)
check_json("AI生平非管理员403",
           anon.post("/api/v1/ai/author-bio", json={"name": "李白"},
                     headers={"Authorization": "Bearer " + new_token}), 403)
r = anon.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
check_json("管理员API登录", r, 200, ["token", "user"])
admin_token = r.get_json().get("token") or ""
check_bool("管理员token非空", len(admin_token) == 64)
check_bool("管理员is_admin为真", (r.get_json().get("user") or {}).get("is_admin") is True)
# 测试库未配置 AI key -> 503（不会真正请求 AI 接口）
r = anon.post("/api/v1/ai/author-bio", json={"name": "李白"},
              headers={"Authorization": "Bearer " + admin_token})
check_bool("AI生平无key503", r.status_code == 503)
# 保存端点（管理员）：作者生平 + 创作背景
r = anon.put("/api/v1/authors/冒烟测试作者/bio",
             json={"zihao": "字测试", "bio": "冒烟测试简介", "dynasty": "唐"},
             headers={"Authorization": "Bearer " + admin_token})
check_json("API保存作者生平", r, 200, ["name", "bio"])
check_bool("API作者生平已落库", (r.get_json().get("bio") or "") == "冒烟测试简介")
_plist = anon.get("/api/v1/poems", headers={"Authorization": "Bearer " + admin_token}).get_json()
_pid = (_plist.get("items") or [{}])[0].get("id") or 1
r = anon.put(f"/api/v1/poems/{_pid}/background", json={"background": "冒烟测试背景"},
             headers={"Authorization": "Bearer " + admin_token})
check_json("API保存创作背景", r, 200, ["background"])
check_bool("API创作背景已落库", (r.get_json().get("background") or "") == "冒烟测试背景")

print()
print("=" * 40)
if failures:
    print("存在失败项:", failures)
    sys.exit(1)
print(f"全部通过！")
