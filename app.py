"""古诗词学习记录网站 - Flask 主应用

功能：浏览/搜索诗词、注册登录、收藏、自定义标签、学习笔记、管理后台。
默认管理员：admin / admin123（首次启动自动创建，登录后请尽快修改）。
"""
import json
import os
from functools import wraps

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)

from models import Poem, User, UserPoem, db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "please-change-this-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DATA_DIR, "poems.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

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
    record = None
    user = current_user()
    if user:
        record = UserPoem.query.filter_by(user_id=user.id, poem_id=poem.id).first()
    return render_template("detail.html", poem=poem, record=record)


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
                            "translation", "annotation", "appreciation")}
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
                                                "translation", "annotation", "appreciation")}
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


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
