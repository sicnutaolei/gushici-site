# API 接口文档（v1）

为 Flutter / 移动端 app 提供 JSON 后端。**网页端功能不受影响**，接口与网页共用同一套数据。

- **Base URL**：`http://<NAS的IP>:8080/api/v1`（本地开发：`http://127.0.0.1:5000/api/v1`）
- **内容类型**：`application/json`（UTF-8，中文不转义）
- **鉴权**：`Authorization: Bearer <token>` 请求头（移动端标准）
- **CORS**：`/api` 路径已放开 `Access-Control-Allow-Origin: *`，Flutter web / 跨域可直接调用

---

## 鉴权流程

1. `POST /auth/register` 或 `POST /auth/login` → 响应体里的 `token` 即为 API 令牌
2. 之后每个需要登录的接口，请求头带 `Authorization: Bearer <token>`
3. 改密码后旧 token 立即失效，需重新 login 拿新 token
4. 退出登录 `POST /auth/logout` 会清空该 token

> 注：同一浏览器站点内，API 也兼容 session cookie 登录（方便调试），但 app 请用 Bearer Token。

---

## 接口列表

### 认证

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/auth/register` | 否 | 注册，返回 `token` + `user` |
| POST | `/auth/login` | 否 | 登录，返回 `token` + `user` |
| POST | `/auth/logout` | 是 | 退出，清空 token |
| GET  | `/auth/me` | 是 | 当前用户信息 |
| POST | `/auth/change-password` | 是 | 改密码，返回新 `token` |

**register / login 请求体**
```json
{ "username": "陶", "password": "abc123", "password2": "abc123" }
```
**响应示例**
```json
{ "token": "27fff3201ece17f446ffcbc8636450482abb782030fce124530c7d494ec8ebb1",
  "user": { "id": 3, "username": "陶", "is_admin": false } }
```

### 诗词浏览（无需登录）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/poems?q=&dynasty=&author=&page=&per_page=` | 列表（搜索/筛选/分页，最大 per_page=100） |
| GET | `/poems/<id>` | 详情（含上一篇/下一篇 `prev`/`next`，登录后含 `my_record`） |
| GET | `/daily` | 每日一诗（按日期固定） |
| GET | `/authors` | 作者列表 `[{name, dynasty, count}]` |
| GET | `/authors/<name>` | 某作者全部诗词 |
| GET | `/dynasties` | 朝代列表 |

**poems 列表响应**
```json
{ "items": [ { "id": 1, "title": "关雎", "author": "佚名", "dynasty": "先秦",
               "content": "关关雎鸠，在河之洲……", "translation": "", "annotation": "",
               "appreciation": "", "is_favorite": false } ],
  "page": 1, "per_page": 10, "total": 73, "pages": 8 }
```

**poems/<id> 响应**
```json
{ "poem": { "id": 13, "title": "静夜思", "author": "李白", "dynasty": "唐", "content": "……", "is_favorite": false },
  "prev": { "id": 12, "title": "……", "author": "……" },
  "next": { "id": 14, "title": "……", "author": "……" },
  "my_record": null }
```

### 个人记录（需登录，带 Bearer Token）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/favorites` | 收藏列表 |
| POST | `/poems/<id>/favorite` | 切换收藏（返回 `{"is_favorite": true/false}`） |
| GET  | `/notes` | 笔记列表（含标签、笔记） |
| PUT/POST | `/poems/<id>/note` | 保存笔记/标签，请求体 `{"note":"", "tags":"必背,思乡"}` |
| GET  | `/tags` | 标签分布 `[{name, count}]` |
| GET  | `/tags/<name>` | 某标签下的诗词 |
| GET  | `/stats` | 学习统计 |
| GET  | `/export` | 导出个人数据 JSON |

**note 保存请求体**
```json
{ "note": "已背会，注意‘疑’是‘怀疑/好像’之意", "tags": "必背,思乡" }
```

### 错误响应

未登录或 token 无效：`401`
```json
{ "error": "未登录或 token 无效", "code": "unauthorized" }
```
参数错误：`400` → `{"error": "具体原因"}`

---

## Flutter 调用示例

依赖 `http` 包：

```dart
import 'dart:convert';
import 'package:http/http.dart' as http;

const base = 'http://192.168.195.107:8080/api/v1';
String? token;

Future<void> login(String user, String pwd) async {
  final r = await http.post(
    Uri.parse('$base/auth/login'),
    headers: {'Content-Type': 'application/json'},
    body: jsonEncode({'username': user, 'password': pwd}),
  );
  token = jsonDecode(r.body)['token'];
}

Future<List<dynamic>> fetchPoems({String? q, int page = 1}) async {
  final r = await http.get(
    Uri.parse('$base/poems').replace(queryParameters: {
      if (q != null) 'q': q, 'page': '$page', 'per_page': '20',
    }),
    headers: { if (token != null) 'Authorization': 'Bearer $token' },
  );
  return jsonDecode(r.body)['items'];
}

Future<void> toggleFavorite(int id) async {
  await http.post(
    Uri.parse('$base/poems/$id/favorite'),
    headers: {'Authorization': 'Bearer $token!'},
  );
}
```

> 提示：NAS 上部署时，Flutter 手机/桌面端访问的 Base URL 用 NAS 的内网 IP（如 `192.168.195.107:8080`）；若走 ZeroTier 则用它分配的虚拟网段地址。
