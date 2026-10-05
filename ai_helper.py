"""AI 助手：生成作者生平 / 诗词创作背景。

兼容任意 OpenAI Chat Completions 接口的模型（DeepSeek、自建/第三方网关等）。

配置全部走环境变量或网页「AI 设置」（不进代码库）：
- AI_API_KEY    必填，接口密钥
- AI_BASE_URL   选填，默认 https://api.deepseek.com
- AI_MODEL      选填，默认 deepseek-flash
- AI_MAX_TOKENS 选填，默认 8192（推理类模型思考会消耗额度，给足余量；被截断会自动重试加大）

只用 Python 标准库（urllib），不给项目增加任何依赖。
未配置 key 时 ai_available() 返回 False，调用方给用户友好提示即可。
"""
import json
import os
import urllib.error
import urllib.request

TIMEOUT = 180  # 推理类模型思考可能要几十秒，留足余量

# 推理模型（如 deepseek-flash、dots3-note-*）会把额度花在思考上导致回答被截断；
# 一旦触发截断（finish_reason=length）就按此阶梯提高 max_tokens 重试，至多 3 次。
_BUDGET_LADDER = (8192, 16384)


def resolve_config(api_key: str = None, base_url: str = None, model: str = None, max_tokens=None):
    """优先级：传入参数 > 环境变量 > 内置默认值。
    返回 (api_key, base_url, model, max_tokens)。"""
    key = (api_key or os.environ.get("AI_API_KEY") or "").strip()
    base = (base_url or os.environ.get("AI_BASE_URL") or "https://api.deepseek.com").strip().rstrip("/") \
        or "https://api.deepseek.com"
    mdl = (model or os.environ.get("AI_MODEL") or "deepseek-flash").strip() or "deepseek-flash"
    try:
        mt = int((str(max_tokens) if max_tokens is not None else os.environ.get("AI_MAX_TOKENS") or "8192").strip()
                 or "8192")
    except (ValueError, TypeError):
        mt = 8192
    if mt < 1024:
        mt = 1024
    return key, base, mdl, mt


def ai_available(api_key: str = None) -> bool:
    return bool(resolve_config(api_key)[0])


def ai_chat_json(system: str, user: str, api_key: str = None, base_url: str = None,
                model: str = None, max_tokens: int = None):
    """调用 Chat Completions，返回解析后的 JSON dict；失败抛 RuntimeError（中文报错）。

    对推理类模型（思考会消耗 token）做了容错：一旦因额度耗尽被截断，自动按
    _BUDGET_LADDER 提高 max_tokens 重试，最多 3 次；仍失败才给出明确中文报错。
    """
    key, base, mdl, mt = resolve_config(api_key, base_url, model, max_tokens)
    if not key:
        raise RuntimeError("未配置 AI_API_KEY（可在网站管理页「AI 设置」填写，或设置 AI_API_KEY 环境变量）")

    # 截断时按阶梯放大额度重试（从用户设定/默认值起步，逐级到 16384）
    budgets = [b for b in _BUDGET_LADDER if b >= mt]
    if not budgets:
        budgets = [mt]
    last_reason = None
    for attempt, budget in enumerate(budgets, 1):
        data = _raw_call(key, base, mdl, system, user, budget)
        try:
            choice = data["choices"][0]
            msg = choice.get("message", {}) or {}
            fr = choice.get("finish_reason")
            content = msg.get("content")
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"AI 返回结构异常：{e}（响应片段：{str(data)[:300]}）") from None

        # 有正文：解析；若恰好在 JSON 中途被截断（length）则放大额度重试
        if content and (content or "").strip():
            try:
                return _extract_json(content)
            except (ValueError, json.JSONDecodeError) as e:
                if fr == "length":
                    last_reason = (f"回答在 JSON 中途被截断（max_tokens={budget} 额度耗尽），"
                                   f"已自动放大额度第 {attempt} 次重试")
                    continue
                snippet = (content or "").strip()[:200]
                raise RuntimeError(f"AI 返回内容无法解析为 JSON：{e}（原始内容：{snippet!r}）") from None

        # 无正文：推理模型把额度烧在 reasoning_content 上、还没来得及回答
        if fr == "length":
            last_reason = (f"思考过程耗尽了 max_tokens={budget} 额度，回答为空，"
                           f"已自动放大额度第 {attempt} 次重试")
            continue
        # 既无正文、又不是截断——模型不支持或接口异常
        raise RuntimeError(f"AI 返回为空（finish_reason={fr!r}），请检查该模型是否支持当前请求格式") from None

    raise RuntimeError(f"AI 多次重试仍因 token 额度不足而截断：{last_reason or '未知原因'}。"
                       f"可到「AI 设置」调大 AI_MAX_TOKENS，或换思考更短的模型。") from None


def _raw_call(key: str, base: str, mdl: str, system: str, user: str, budget: int) -> dict:
    """发起一次 Chat Completions 请求，返回解析后的响应 dict；HTTP/连接错误直接抛 RuntimeError。"""
    payload = json.dumps({
        "model": mdl,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.6,
        "max_tokens": budget,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        base + "/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(
            f"AI 接口返回 {e.code}：{detail or '请检查 AI_API_KEY 是否有效、AI_BASE_URL/AI_MODEL 是否正确'}"
        ) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 AI 接口：{e.reason}") from None


def _extract_json(content: str) -> dict:
    """从模型回复里取出 JSON 对象。兼容模型把 JSON 用 ```json ... ``` 代码块包裹的情况。"""
    s = (content or "").strip()
    if not s:
        raise ValueError("响应内容为空")
    # 去掉可能的 markdown 代码块包裹（```json ... ``` 或 ``` ... ```）
    if s.startswith("```"):
        # 去掉首行（可能含语言标识如 json）与结尾的 ```
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
        if not s:
            raise ValueError("响应内容为空（仅含代码块标记）")
    return json.loads(s)


# ---------- 面向业务的两个封装 ----------

BIO_SYSTEM = ("你是严谨的古典文学学者。只输出 JSON 对象本身，不要输出任何其他文字，"
              "也不要用 ``` 代码块或反引号包裹。生卒年用通行说法，拿不准就加「约」前缀；"
              "不得编造史实。")


def generate_author_bio(name: str, dynasty: str = "", api_key: str = None,
                        base_url: str = None, model: str = None, max_tokens: int = None) -> dict:
    """生成作者档案：{zihao, birth_year, death_year, bio}"""
    user = (f"请为诗人「{name}」" + (f"（{dynasty}）" if dynasty else "") +
            "写一份档案，输出 JSON，字段：\n"
            '- "zihao"：字号，如「字太白，号青莲居士」，无则空字符串\n'
            '- "birth_year"：生年，如「701」或「约701」\n'
            '- "death_year"：卒年\n'
            '- "bio"：生平简介，120-180 字，涵盖身份、经历要点、诗风、代表作、文学史地位\n'
            "只输出 JSON 对象本身。")
    data = ai_chat_json(BIO_SYSTEM, user, api_key=api_key, base_url=base_url, model=model, max_tokens=max_tokens)
    return {k: str(data.get(k, "") or "").strip() for k in
            ("zihao", "birth_year", "death_year", "bio")}


BG_SYSTEM = ("你是严谨的古典文学学者。只输出 JSON 对象本身，不要输出任何其他文字，"
             "也不要用 ``` 代码块或反引号包裹。以学界通行说法为准，不得编造具体史实与轶事。")


def generate_poem_background(title: str, author: str, dynasty: str, content: str,
                            api_key: str = None, base_url: str = None, model: str = None,
                            max_tokens: int = None) -> dict:
    """生成创作背景：{background}，聚焦作者当时人生阶段与经历"""
    user = (f"诗题《{title}》，作者{author}" + (f"（{dynasty}）" if dynasty else "") +
            "。原文：\n" + content +
            "\n\n请写这段诗的创作背景，输出 JSON，字段：\n"
            '- "background"：80-150 字。重点写作者创作此诗时所处的人生阶段（如贬谪、'
            "漫游、隐居、战乱流离、任职何处）与当时经历、心境，不要复述诗意、不要赏析。"
            "若创作年份学界有争议，用通行说法并可加「一般认为」。\n"
            "只输出 JSON 对象本身。")
    data = ai_chat_json(BG_SYSTEM, user, api_key=api_key, base_url=base_url, model=model, max_tokens=max_tokens)
    return {"background": str(data.get("background", "") or "").strip()}
