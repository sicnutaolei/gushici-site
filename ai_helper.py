"""DeepSeek（OpenAI 兼容）AI 助手：生成作者生平 / 诗词创作背景。

配置全部走环境变量（不进代码库）：
- AI_API_KEY   必填，DeepSeek 平台申请
- AI_BASE_URL  选填，默认 https://api.deepseek.com
- AI_MODEL     选填，默认 deepseek-chat

只用 Python 标准库（urllib），不给项目增加任何依赖。
未配置 key 时 ai_available() 返回 False，调用方给用户友好提示即可。
"""
import json
import os
import urllib.error
import urllib.request

TIMEOUT = 90  # 生成较多文字时 DeepSeek 可能要十几秒，留足余量


def ai_available() -> bool:
    return bool(os.environ.get("AI_API_KEY"))


def _config():
    return {
        "base_url": (os.environ.get("AI_BASE_URL") or "https://api.deepseek.com").rstrip("/"),
        "api_key": os.environ["AI_API_KEY"],
        "model": os.environ.get("AI_MODEL") or "deepseek-chat",
    }


def ai_chat_json(system: str, user: str):
    """调用 Chat Completions，返回解析后的 JSON dict；失败抛 RuntimeError（中文报错）"""
    cfg = _config()
    payload = json.dumps({
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.6,
        "max_tokens": 1000,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        cfg["base_url"] + "/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:
            pass
        raise RuntimeError(f"AI 接口返回 {e.code}：{detail or '请检查 AI_API_KEY 是否有效'}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 AI 接口：{e.reason}") from None

    try:
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise RuntimeError(f"AI 返回内容无法解析为 JSON：{e}") from None


# ---------- 面向业务的两个封装 ----------

BIO_SYSTEM = ("你是严谨的古典文学学者。只输出 JSON，不要输出任何其他文字。"
              "生卒年用通行说法，拿不准就加「约」前缀；不得编造史实。")


def generate_author_bio(name: str, dynasty: str = "") -> dict:
    """生成作者档案：{zihao, birth_year, death_year, bio}"""
    user = (f"请为诗人「{name}」" + (f"（{dynasty}）" if dynasty else "") +
            "写一份档案，输出 JSON，字段：\n"
            '- "zihao"：字号，如「字太白，号青莲居士」，无则空字符串\n'
            '- "birth_year"：生年，如「701」或「约701」\n'
            '- "death_year"：卒年\n'
            '- "bio"：生平简介，120-180 字，涵盖身份、经历要点、诗风、代表作、文学史地位\n'
            "只输出 JSON 对象本身。")
    data = ai_chat_json(BIO_SYSTEM, user)
    return {k: str(data.get(k, "") or "").strip() for k in
            ("zihao", "birth_year", "death_year", "bio")}


BG_SYSTEM = ("你是严谨的古典文学学者。只输出 JSON，不要输出任何其他文字。"
             "以学界通行说法为准，不得编造具体史实与轶事。")


def generate_poem_background(title: str, author: str, dynasty: str, content: str) -> dict:
    """生成创作背景：{background}，聚焦作者当时人生阶段与经历"""
    user = (f"诗题《{title}》，作者{author}" + (f"（{dynasty}）" if dynasty else "") +
            "。原文：\n" + content +
            "\n\n请写这段诗的创作背景，输出 JSON，字段：\n"
            '- "background"：80-150 字。重点写作者创作此诗时所处的人生阶段（如贬谪、'
            "漫游、隐居、战乱流离、任职何处）与当时经历、心境，不要复述诗意、不要赏析。"
            "若创作年份学界有争议，用通行说法并可加「一般认为」。\n"
            "只输出 JSON 对象本身。")
    data = ai_chat_json(BG_SYSTEM, user)
    return {"background": str(data.get("background", "") or "").strip()}
