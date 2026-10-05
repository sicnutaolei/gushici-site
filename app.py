"""古诗词学习记录网站 - Flask 主应用

功能：浏览/搜索诗词、注册登录、收藏、自定义标签、学习笔记、管理后台。
默认管理员：admin / admin123（首次启动自动创建，登录后请尽快修改）。
"""
import json
import os
from datetime import datetime
from functools import wraps

import click
from flask import (Flask, Response, abort, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from sqlalchemy import inspect, text

from models import Author, Poem, ReciteLog, SiteSetting, User, UserPoem, db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "please-change-this-secret-key")
# 可通过环境变量 POEMS_DB_PATH 指定数据库文件（测试时指向独立文件，避免影响真实数据）
db_path = os.environ.get("POEMS_DB_PATH", os.path.join(DATA_DIR, "poems.db"))
os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# API 返回中文原文时输出可读 UTF-8（不转义为 \uXXXX），同时减小 payload
app.json.ensure_ascii = False

db.init_app(app)

# 注册 JSON API（/api/v1）——为 Flutter 等客户端提供后端接口，不破坏网页端
from api import api_bp
app.register_blueprint(api_bp)


# ---------- CORS（仅对 /api 放开，供 Flutter web / 跨域调用）----------
@app.after_request
def _add_cors(resp):
    if request.path.startswith("/api"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return resp


@app.route("/api/v1", defaults={"_": ""}, methods=["OPTIONS"])
@app.route("/api/v1/<path:_>", methods=["OPTIONS"])
def _api_preflight(_):
    return ("", 204)


PER_PAGE = 10


# ---------- 登录态工具 ----------

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            flash("请先登录", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        u = current_user()
        if not u:
            return redirect(url_for("login", next=request.path))
        if not u.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return dict(cur_user=current_user())


# ---------- 诗词浏览 ----------

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    dynasty = request.args.get("dynasty", "").strip()
    page = request.args.get("page", 1, type=int)

    query = Poem.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Poem.title.like(like),
                                    Poem.author.like(like),
                                    Poem.content.like(like)))
    if dynasty:
        query = query.filter(Poem.dynasty == dynasty)

    pagination = query.order_by(Poem.id).paginate(page=page, per_page=PER_PAGE,
                                                  error_out=False)

    user = current_user()
    fav_ids = set()
    if user:
        rows = UserPoem.query.filter_by(user_id=user.id, is_favorite=True).all()
        fav_ids = {r.poem_id for r in rows}

    dynasties = [d[0] for d in db.session.query(Poem.dynasty).distinct().order_by(Poem.dynasty)]
    total = Poem.query.count()

    return render_template("index.html", poems=pagination.items, pagination=pagination,
                           q=q, dynasty=dynasty, dynasties=dynasties,
                           fav_ids=fav_ids, total=total)


@app.route("/poem/<int:poem_id>")
def poem_detail(poem_id):
    poem = db.get_or_404(Poem, poem_id)
    prev_poem = Poem.query.filter(Poem.id < poem.id).order_by(Poem.id.desc()).first()
    next_poem = Poem.query.filter(Poem.id > poem.id).order_by(Poem.id.asc()).first()
    record = None
    user = current_user()
    if user:
        record = UserPoem.query.filter_by(user_id=user.id, poem_id=poem.id).first()
    return render_template("detail.html", poem=poem, record=record,
                           prev_poem=prev_poem, next_poem=next_poem)


# ---------- 个人记录：收藏 / 标签 / 笔记 ----------

def _get_record(user_id, poem_id):
    record = UserPoem.query.filter_by(user_id=user_id, poem_id=poem_id).first()
    if not record:
        record = UserPoem(user_id=user_id, poem_id=poem_id)
        db.session.add(record)
    return record


@app.post("/poem/<int:poem_id>/favorite")
@login_required
def toggle_favorite(poem_id):
    db.get_or_404(Poem, poem_id)
    record = _get_record(current_user().id, poem_id)
    record.is_favorite = not record.is_favorite
    db.session.commit()
    flash("已加入喜欢" if record.is_favorite else "已取消喜欢", "success")
    return redirect(request.referrer or url_for("poem_detail", poem_id=poem_id))


@app.post("/poem/<int:poem_id>/note")
@login_required
def save_note(poem_id):
    db.get_or_404(Poem, poem_id)
    note = request.form.get("note", "").strip()
    tags_raw = request.form.get("tags", "").strip()
    tags = ",".join(t for t in (x.strip() for x in tags_raw.replace("，", ",").split(",")) if t)[:200]
    record = _get_record(current_user().id, poem_id)
    record.note = note
    record.tags = tags
    db.session.commit()
    flash("笔记与标签已保存", "success")
    return redirect(url_for("poem_detail", poem_id=poem_id))


@app.route("/favorites")
@login_required
def favorites():
    records = (UserPoem.query.filter_by(user_id=current_user().id, is_favorite=True)
               .order_by(UserPoem.updated_at.desc()).all())
    return render_template("favorites.html", records=records)


@app.route("/notes")
@login_required
def notes():
    records = (UserPoem.query.filter_by(user_id=current_user().id)
               .order_by(UserPoem.updated_at.desc()).all())
    records = [r for r in records if r.note or r.tags]
    return render_template("notes.html", records=records)


@app.route("/tag/<name>")
@login_required
def tag_view(name):
    records = (UserPoem.query.filter_by(user_id=current_user().id)
               .order_by(UserPoem.updated_at.desc()).all())
    records = [r for r in records if name in r.tag_list()]
    return render_template("tag.html", tag=name, records=records)


@app.route("/daily")
def daily():
    """每日一诗：同一天所有人看到同一首（按日期序数取模）"""
    total = Poem.query.count()
    if total == 0:
        flash("诗词库为空", "warning")
        return redirect(url_for("index"))
    offset = datetime.now().toordinal() % total
    poem = Poem.query.order_by(Poem.id).offset(offset).first()
    return redirect(url_for("poem_detail", poem_id=poem.id))


@app.route("/author/<name>")
def author_view(name):
    author_obj = Author.query.filter_by(name=name).first()
    poems = Poem.query.filter(Poem.author == name).order_by(Poem.id).all()
    user = current_user()
    fav_ids = set()
    if user:
        rows = UserPoem.query.filter_by(user_id=user.id, is_favorite=True).all()
        fav_ids = {r.poem_id for r in rows}
    dynasties = sorted({p.dynasty for p in poems})
    return render_template("author.html", name=name, author_obj=author_obj,
                           poems=poems, fav_ids=fav_ids, dynasties=dynasties)


@app.route("/stats")
@login_required
def stats():
    """个人学习统计：收藏数、笔记数、标签分布、朝代分布"""
    uid = current_user().id
    records = UserPoem.query.filter_by(user_id=uid).all()
    fav_count = sum(1 for r in records if r.is_favorite)
    note_count = sum(1 for r in records if r.note)
    tagged_count = sum(1 for r in records if r.tags)

    tag_stat = {}
    for r in records:
        for t in r.tag_list():
            tag_stat[t] = tag_stat.get(t, 0) + 1
    tags_sorted = sorted(tag_stat.items(), key=lambda x: -x[1])

    dynasty_stat = {}
    for r in records:
        if r.is_favorite or r.note or r.tags:
            d = r.poem.dynasty
            dynasty_stat[d] = dynasty_stat.get(d, 0) + 1
    dynasty_sorted = sorted(dynasty_stat.items(), key=lambda x: -x[1])

    max_tag = tags_sorted[0][1] if tags_sorted else 0
    max_dyn = dynasty_sorted[0][1] if dynasty_sorted else 0
    total = Poem.query.count()
    touched = len({r.poem_id for r in records if r.is_favorite or r.note or r.tags})

    return render_template("stats.html", fav_count=fav_count, note_count=note_count,
                           tagged_count=tagged_count, tags_sorted=tags_sorted,
                           dynasty_sorted=dynasty_sorted, max_tag=max_tag,
                           max_dyn=max_dyn, total=total, touched=touched,
                           **_recite_summary(uid))


# ---------- 背诵打卡 ----------

def _recite_summary(uid):
    """背诵打卡汇总：今日是否打卡、连续天数、累计次数、覆盖首数、最近记录"""
    logs = (ReciteLog.query.filter_by(user_id=uid)
            .order_by(ReciteLog.created_at.desc()).all())
    today = datetime.now().date()
    days = sorted({r.created_at.date() for r in logs}, reverse=True)
    streak = 0
    # 从今天（或昨天）起往回数连续天数
    if days and (days[0] == today or (today - days[0]).days == 1):
        streak = 1
        for prev, cur in zip(days, days[1:]):
            if (prev - cur).days == 1:
                streak += 1
            else:
                break
    recent = logs[:8]
    return {
        "recite_today": today in set(days),
        "recite_streak": streak,
        "recite_total": len(logs),
        "recite_poems": len({r.poem_id for r in logs}),
        "recite_recent": recent,
    }


@app.route("/recite/<int:poem_id>")
@login_required
def recite(poem_id):
    """背诵模式：只给标题/作者/朝代与标点，正文逐字填写，全对自动记打卡"""
    poem = db.get_or_404(Poem, poem_id)
    return render_template("recite.html", poem=poem)


@app.post("/recite/<int:poem_id>/checkin")
@login_required
def recite_checkin(poem_id):
    """背诵全对后的打卡接口（由 recite 页前端自动调用）"""
    poem = db.get_or_404(Poem, poem_id)
    db.session.add(ReciteLog(user_id=current_user().id, poem_id=poem.id))
    db.session.commit()
    s = _recite_summary(current_user().id)
    return jsonify(ok=True, today=s["recite_today"], streak=s["recite_streak"],
                   total=s["recite_total"], poems=s["recite_poems"])


@app.route("/export")
@login_required
def export_data():
    """导出当前用户的个人数据（收藏 / 标签 / 笔记）为 JSON 文件，用于备份或迁移"""
    records = (UserPoem.query.filter_by(user_id=current_user().id)
               .order_by(UserPoem.poem_id).all())
    data = {
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "username": current_user().username,
        "records": [
            {
                "poem_id": r.poem_id,
                "title": r.poem.title,
                "author": r.poem.author,
                "dynasty": r.poem.dynasty,
                "is_favorite": r.is_favorite,
                "tags": r.tag_list(),
                "note": r.note,
            }
            for r in records if r.is_favorite or r.note or r.tags
        ],
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"gushici_export_{datetime.now().strftime('%Y%m%d')}.json"
    return Response(body, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


# ---------- 认证 ----------

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old = request.form.get("old_password", "")
        new = request.form.get("new_password", "")
        new2 = request.form.get("new_password2", "")
        user = current_user()
        if not user.check_password(old):
            flash("原密码不正确", "warning")
        elif len(new) < 6:
            flash("新密码至少 6 位", "warning")
        elif new != new2:
            flash("两次输入的新密码不一致", "warning")
        else:
            user.set_password(new)
            db.session.commit()
            flash("密码修改成功", "success")
            return redirect(url_for("index"))
    return render_template("change_password.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        if not (2 <= len(username) <= 20):
            flash("用户名需 2-20 个字符", "warning")
        elif len(password) < 6:
            flash("密码至少 6 位", "warning")
        elif password != password2:
            flash("两次输入的密码不一致", "warning")
        elif User.query.filter_by(username=username).first():
            flash("用户名已被占用", "warning")
        else:
            u = User(username=username)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash("注册成功，请登录", "success")
            return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session["user_id"] = user.id
            flash(f"欢迎回来，{user.username}", "success")
            nxt = request.args.get("next") or request.form.get("next")
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("index"))
        flash("用户名或密码错误", "warning")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("已退出登录", "success")
    return redirect(url_for("index"))


# ---------- 管理后台 ----------

@app.route("/admin")
@admin_required
def admin():
    poems = Poem.query.order_by(Poem.id).all()
    users = User.query.order_by(User.id).all()
    return render_template("admin.html", poems=poems, users=users)


@app.route("/admin/poem/new", methods=["GET", "POST"])
@admin_required
def poem_new():
    form = {k: "" for k in ("title", "author", "dynasty", "content",
                            "translation", "annotation", "appreciation", "background")}
    if request.method == "POST":
        for k in form:
            form[k] = request.form.get(k, "").strip()
        if not (form["title"] and form["author"] and form["dynasty"] and form["content"]):
            flash("标题、作者、朝代、原文为必填项", "warning")
        else:
            poem = Poem(**form)
            db.session.add(poem)
            db.session.commit()
            flash("诗词已添加", "success")
            return redirect(url_for("admin"))
    return render_template("poem_form.html", form=form, is_new=True)


@app.route("/admin/poem/<int:poem_id>/edit", methods=["GET", "POST"])
@admin_required
def poem_edit(poem_id):
    poem = db.get_or_404(Poem, poem_id)
    form = {k: getattr(poem, k) or "" for k in ("title", "author", "dynasty", "content",
                                                "translation", "annotation", "appreciation",
                                                "background")}
    if request.method == "POST":
        for k in form:
            setattr(poem, k, request.form.get(k, "").strip())
        db.session.commit()
        flash("诗词已更新", "success")
        return redirect(url_for("admin"))
    return render_template("poem_form.html", form=form, is_new=False, poem_id=poem.id)


@app.post("/admin/poem/<int:poem_id>/delete")
@admin_required
def poem_delete(poem_id):
    poem = db.get_or_404(Poem, poem_id)
    UserPoem.query.filter_by(poem_id=poem.id).delete()
    db.session.delete(poem)
    db.session.commit()
    flash("诗词已删除", "success")
    return redirect(url_for("admin"))


@app.route("/admin/author/<name>/edit", methods=["GET", "POST"])
@admin_required
def author_edit(name):
    """补充 / 编辑某作者的生平简介（作者档案可选，缺省显示「暂无简介」）。"""
    author_obj = Author.query.filter_by(name=name).first()
    fields = ("dynasty", "zihao", "birth_year", "death_year", "bio")
    if request.method == "POST":
        if not author_obj:
            author_obj = Author(name=name)
            db.session.add(author_obj)
        for k in fields:
            setattr(author_obj, k, (request.form.get(k, "") or "").strip())
        db.session.commit()
        flash("作者信息已保存", "success")
        return redirect(url_for("author_view", name=name))
    form = {k: getattr(author_obj, k) or "" for k in fields} if author_obj else {k: "" for k in fields}
    return render_template("author_form.html", name=name, form=form)


# ---------- AI 生成（DeepSeek，OpenAI 兼容接口）----------

def _ai_config():
    """从站点设置（网页填写）读取 AI 配置，环境变量优先级更高。返回 (key, base, model)。"""
    import ai_helper
    key = os.environ.get("AI_API_KEY") or SiteSetting.get("AI_API_KEY", "")
    base = os.environ.get("AI_BASE_URL") or SiteSetting.get("AI_BASE_URL", "")
    model = os.environ.get("AI_MODEL") or SiteSetting.get("AI_MODEL", "")
    return ai_helper.resolve_config(api_key=key, base_url=base, model=model)


@app.route("/admin/settings", methods=["GET", "POST"])
@admin_required
def admin_settings():
    """AI 配置（密钥/接口地址/模型），管理员在网页填写，存数据库。
    环境变量若已设置则覆盖此处。"""
    if request.method == "POST":
        for k in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL"):
            v = (request.form.get(k, "") or "").strip()
            if v:  # 留空表示不修改已保存的值
                SiteSetting.set(k, v)
        flash("AI 设置已保存", "success")
        return redirect(url_for("admin_settings"))
    vals = {k: SiteSetting.get(k, "") for k in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL")}
    env_src = {k: bool(os.environ.get(k)) for k in ("AI_API_KEY", "AI_BASE_URL", "AI_MODEL")}
    return render_template("settings.html", vals=vals, env_src=env_src)


@app.post("/admin/author/<name>/ai-bio")
@admin_required
def author_ai_bio(name):
    """AI 生成作者生平，返回 JSON 供表单预填（管理员确认后才保存）"""
    import ai_helper
    key, base, model = _ai_config()
    if not key:
        return jsonify(ok=False, error="未配置 AI_API_KEY（可在网站管理页「AI 设置」填写，或设置 AI_API_KEY 环境变量）"), 503
    j = request.get_json(silent=True) or {}
    dynasty = j.get("dynasty", "")
    try:
        data = ai_helper.generate_author_bio(name, dynasty, api_key=key, base_url=base, model=model)
        return jsonify(ok=True, **data)
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 502


@app.post("/admin/poem/<int:poem_id>/ai-background")
@admin_required
def poem_ai_background(poem_id):
    """AI 生成某首诗的创作背景，返回 JSON 供表单预填（管理员确认后才保存）"""
    import ai_helper
    key, base, model = _ai_config()
    if not key:
        return jsonify(ok=False, error="未配置 AI_API_KEY（可在网站管理页「AI 设置」填写，或设置 AI_API_KEY 环境变量）"), 503
    poem = db.get_or_404(Poem, poem_id)
    try:
        data = ai_helper.generate_poem_background(
            poem.title, poem.author, poem.dynasty, poem.content,
            api_key=key, base_url=base, model=model)
        return jsonify(ok=True, **data)
    except RuntimeError as e:
        return jsonify(ok=False, error=str(e)), 502


@app.cli.command("ai-fill-bios")
@click.option("--only-empty", is_flag=True, default=True, help="只给没有简介的作者生成")
def ai_fill_bios(only_empty):
    """批量 AI 生成作者生平（环境变量或网页「AI 设置」均可）"""
    import ai_helper
    key, base, model = _ai_config()
    if not key:
        raise SystemExit("请先配置 AI_API_KEY（网页「AI 设置」或环境变量）")
    names = [r[0] for r in db.session.query(Poem.author).distinct().order_by(Poem.author)]
    done = skip = fail = 0
    for name in names:
        author_obj = Author.query.filter_by(name=name).first()
        if only_empty and author_obj and (author_obj.bio or "").strip():
            skip += 1
            continue
        try:
            data = ai_helper.generate_author_bio(name, api_key=key, base_url=base, model=model)
        except RuntimeError as e:
            print(f"[失败] {name}: {e}")
            fail += 1
            continue
        if not author_obj:
            author_obj = Author(name=name)
            db.session.add(author_obj)
        for k in ("zihao", "birth_year", "death_year", "bio"):
            if data.get(k):
                setattr(author_obj, k, data[k])
        db.session.commit()
        done += 1
        print(f"[完成] {name}")
    print(f"汇总：生成 {done}，跳过 {skip}，失败 {fail}")


@app.cli.command("ai-fill-backgrounds")
@click.option("--only-empty", is_flag=True, default=True, help="只给没有创作背景的诗生成")
def ai_fill_backgrounds(only_empty):
    """批量 AI 生成诗词创作背景（环境变量或网页「AI 设置」均可）"""
    import ai_helper
    key, base, model = _ai_config()
    if not key:
        raise SystemExit("请先配置 AI_API_KEY（网页「AI 设置」或环境变量）")
    poems = Poem.query.order_by(Poem.id).all()
    done = skip = fail = 0
    for p in poems:
        if only_empty and (p.background or "").strip():
            skip += 1
            continue
        try:
            data = ai_helper.generate_poem_background(
                p.title, p.author, p.dynasty, p.content,
                api_key=key, base_url=base, model=model)
        except RuntimeError as e:
            print(f"[失败] 《{p.title}》: {e}")
            fail += 1
            continue
        if data.get("background"):
            p.background = data["background"]
            db.session.commit()
            done += 1
            print(f"[完成] 《{p.title}》")
    print(f"汇总：生成 {done}，跳过 {skip}，失败 {fail}")


REQUIRED_FIELDS = ("title", "author", "dynasty", "content")


@app.route("/admin/import", methods=["GET", "POST"])
@admin_required
def import_poems():
    """批量导入诗词：粘贴 JSON 或上传 .json 文件。

    JSON 格式（数组，可选字段 translation / annotation / appreciation）：
    [
      {"title": "...", "author": "...", "dynasty": "唐", "content": "...", ...}
    ]
    同标题+作者已存在的会跳过（防重复导入）。
    """
    result = None
    if request.method == "POST":
        raw = ""
        upload = request.files.get("file")
        if upload and upload.filename:
            raw = upload.read().decode("utf-8", errors="replace")
        else:
            raw = request.form.get("json_text", "")
        result = {"ok": 0, "skip": 0, "errors": []}
        try:
            items = json.loads(raw)
        except ValueError as e:
            result["errors"].append(f"JSON 解析失败：{e}")
            items = None
        if items is not None:
            if not isinstance(items, list):
                result["errors"].append("JSON 顶层必须是数组 [ ... ]")
            else:
                for i, item in enumerate(items, 1):
                    if not isinstance(item, dict):
                        result["errors"].append(f"第 {i} 条：不是对象")
                        continue
                    missing = [f for f in REQUIRED_FIELDS if not str(item.get(f, "")).strip()]
                    if missing:
                        result["errors"].append(f"第 {i} 条：缺少必填字段 {('、'.join(missing))}")
                        continue
                    exists = Poem.query.filter_by(title=item["title"].strip(),
                                                  author=item["author"].strip()).first()
                    if exists:
                        result["skip"] += 1
                        continue
                    poem = Poem(
                        title=item["title"].strip(), author=item["author"].strip(),
                        dynasty=item["dynasty"].strip(), content=item["content"].strip(),
                        translation=str(item.get("translation", "") or "").strip(),
                        annotation=str(item.get("annotation", "") or "").strip(),
                        appreciation=str(item.get("appreciation", "") or "").strip(),
                    )
                    db.session.add(poem)
                    result["ok"] += 1
                db.session.commit()
        if result["ok"]:
            flash(f"成功导入 {result['ok']} 首，跳过重复 {result['skip']} 首", "success")
        elif not result["errors"]:
            flash("没有导入任何诗词", "warning")
    return render_template("import.html", result=result)


@app.post("/admin/user/<int:user_id>/toggle_admin")
@admin_required
def user_toggle_admin(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user().id:
        flash("不能修改自己的管理员身份", "warning")
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash("已更新用户权限", "success")
    return redirect(url_for("admin"))


@app.post("/admin/user/<int:user_id>/delete")
@admin_required
def user_delete(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user().id:
        flash("不能删除自己", "warning")
    else:
        UserPoem.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        flash("用户已删除", "success")
    return redirect(url_for("admin"))


# ---------- 初始化 ----------

def init_db(reset=False):
    """建表 + 预置数据 + 默认管理员（幂等，重复启动不会重复导入）。

    reset=True 时先删除所有表再重建（仅测试用，会清空全部数据）。
    """
    with app.app_context():
        if reset:
            db.drop_all()
        db.create_all()
        # 老库向后兼容：create_all 只建新表不给旧表加列，这里统一自动补列（自愈迁移）
        wanted_columns = {
            "users": {"api_token": "VARCHAR(64)"},
            "poems": {"background": "TEXT"},
        }
        for table, cols_to_add in wanted_columns.items():
            try:
                cols = [c["name"] for c in inspect(db.engine).get_columns(table)]
            except Exception:
                continue
            for col, coltype in cols_to_add.items():
                if col not in cols:
                    with db.engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                    print(f"[init] 已为 {table} 表追加 {col} 列")
        if not User.query.filter_by(username="admin").first():
            admin = User(username="admin", is_admin=True)
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()
            print("[init] 已创建默认管理员：admin / admin123（请登录后修改密码）")
        if Poem.query.count() == 0:
            from seed_data import ALL_POEMS
            db.session.bulk_insert_mappings(Poem, ALL_POEMS)
            db.session.commit()
            print(f"[init] 已导入预置诗词 {len(ALL_POEMS)} 首")
        if Author.query.count() == 0:
            from seed_authors import ALL_AUTHORS
            db.session.bulk_insert_mappings(Author, ALL_AUTHORS)
            db.session.commit()
            print(f"[init] 已导入作者简介 {len(ALL_AUTHORS)} 位")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
