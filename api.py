"""JSON API (v1) —— 为 Flutter 等客户端提供后端接口。

设计要点：
- 所有响应为 JSON（UTF-8）。
- 鉴权支持 Bearer Token（移动端标准），并回退兼容浏览器 Session Cookie（同站调试方便）。
- 与网页端共享同一套数据模型，网页功能不受影响。
- 不引入 flask-cors，CORS 由 app.py 的 after_request 手写响应头处理。
"""
import secrets
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request, session

from models import Poem, ReciteLog, User, UserPoem, db

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


# ---------- 鉴权 ----------

def get_token_user():
    """优先 Bearer Token；其次回退浏览器 session（同一站点内网页/接口可复用）"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token:
            u = User.query.filter_by(api_token=token).first()
            if u:
                return u
    uid = session.get("user_id")
    if uid:
        return db.session.get(User, uid)
    return None


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not get_token_user():
            return jsonify(error="未登录或 token 无效", code="unauthorized"), 401
        return view(*args, **kwargs)
    return wrapped


def _user_json(u):
    return {"id": u.id, "username": u.username, "is_admin": u.is_admin}


# ---------- 序列化 ----------

def _poem_json(p, fav=False):
    return {
        "id": p.id, "title": p.title, "author": p.author, "dynasty": p.dynasty,
        "content": p.content,
        "translation": p.translation or "", "annotation": p.annotation or "",
        "appreciation": p.appreciation or "", "background": p.background or "",
        "is_favorite": fav,
    }


def _brief(p):
    return {"id": p.id, "title": p.title, "author": p.author} if p else None


# ---------- 认证接口 ----------

@api_bp.route("/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    password2 = data.get("password2") or ""
    if not (2 <= len(username) <= 20):
        return jsonify(error="用户名需 2-20 个字符"), 400
    if len(password) < 6:
        return jsonify(error="密码至少 6 位"), 400
    if password != password2:
        return jsonify(error="两次输入的密码不一致"), 400
    if User.query.filter_by(username=username).first():
        return jsonify(error="用户名已被占用"), 400
    u = User(username=username)
    u.set_password(password)
    u.refresh_token()
    db.session.add(u)
    db.session.commit()
    return jsonify(token=u.api_token, user=_user_json(u)), 200


@api_bp.route("/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    u = User.query.filter_by(username=username).first()
    if not u or not u.check_password(password):
        return jsonify(error="用户名或密码错误"), 401
    if not u.api_token:
        u.refresh_token()
    db.session.commit()
    return jsonify(token=u.api_token, user=_user_json(u)), 200


@api_bp.route("/auth/logout", methods=["POST"])
@api_login_required
def api_logout():
    u = get_token_user()
    u.api_token = None
    db.session.commit()
    return jsonify(ok=True), 200


@api_bp.route("/auth/me")
@api_login_required
def api_me():
    return jsonify(user=_user_json(get_token_user()))


@api_bp.route("/auth/change-password", methods=["POST"])
@api_login_required
def api_change_password():
    u = get_token_user()
    data = request.get_json(silent=True) or {}
    old = data.get("old_password", "")
    new = data.get("new_password", "")
    new2 = data.get("new_password2", "")
    if not u.check_password(old):
        return jsonify(error="原密码不正确"), 400
    if len(new) < 6:
        return jsonify(error="新密码至少 6 位"), 400
    if new != new2:
        return jsonify(error="两次输入的新密码不一致"), 400
    u.set_password(new)
    u.refresh_token()  # 改密后旧 token 失效
    db.session.commit()
    return jsonify(token=u.api_token, user=_user_json(u)), 200


# ---------- 诗词浏览 ----------

@api_bp.route("/poems")
def api_poems():
    q = request.args.get("q", "").strip()
    dynasty = request.args.get("dynasty", "").strip()
    author = request.args.get("author", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = min(max(request.args.get("per_page", 10, type=int), 1), 100)

    query = Poem.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Poem.title.like(like),
                                    Poem.author.like(like),
                                    Poem.content.like(like)))
    if dynasty:
        query = query.filter(Poem.dynasty == dynasty)
    if author:
        query = query.filter(Poem.author == author)

    total = query.count()
    items = query.order_by(Poem.id).paginate(page=page, per_page=per_page, error_out=False)

    u = get_token_user()
    fav_ids = set()
    if u:
        fav_ids = {r.poem_id for r in
                   UserPoem.query.filter_by(user_id=u.id, is_favorite=True).all()}
    return jsonify({
        "items": [_poem_json(p, p.id in fav_ids) for p in items.items],
        "page": items.page, "per_page": items.per_page,
        "total": total, "pages": items.pages,
    })


@api_bp.route("/poems/<int:poem_id>")
def api_poem_detail(poem_id):
    p = db.get_or_404(Poem, poem_id)
    prev_p = Poem.query.filter(Poem.id < p.id).order_by(Poem.id.desc()).first()
    next_p = Poem.query.filter(Poem.id > p.id).order_by(Poem.id.asc()).first()
    u = get_token_user()
    record = None
    if u:
        r = UserPoem.query.filter_by(user_id=u.id, poem_id=p.id).first()
        if r:
            record = {
                "is_favorite": r.is_favorite,
                "tags": r.tag_list(),
                "note": r.note,
                "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
            }
    return jsonify({"poem": _poem_json(p), "prev": _brief(prev_p),
                    "next": _brief(next_p), "my_record": record})


@api_bp.route("/daily")
def api_daily():
    total = Poem.query.count()
    if total == 0:
        return jsonify(error="诗词库为空"), 404
    offset = datetime.now().toordinal() % total
    p = Poem.query.order_by(Poem.id).offset(offset).first()
    return jsonify(_poem_json(p))


@api_bp.route("/authors")
def api_authors():
    rows = (db.session.query(Poem.author, Poem.dynasty, db.func.count(Poem.id))
            .group_by(Poem.author).order_by(db.func.count(Poem.id).desc()).all())
    return jsonify([{"name": a, "dynasty": d, "count": c} for a, d, c in rows])


@api_bp.route("/authors/<name>")
def api_author_poems(name):
    poems = Poem.query.filter(Poem.author == name).order_by(Poem.id).all()
    return jsonify([_poem_json(p) for p in poems])


@api_bp.route("/dynasties")
def api_dynasties():
    ds = [d[0] for d in db.session.query(Poem.dynasty).distinct().order_by(Poem.dynasty)]
    return jsonify(ds)


# ---------- 个人记录：收藏 / 标签 / 笔记 ----------

def _get_record(uid, poem_id):
    rec = UserPoem.query.filter_by(user_id=uid, poem_id=poem_id).first()
    if not rec:
        rec = UserPoem(user_id=uid, poem_id=poem_id)
        db.session.add(rec)
    return rec


@api_bp.route("/favorites")
@api_login_required
def api_favorites():
    u = get_token_user()
    recs = (UserPoem.query.filter_by(user_id=u.id, is_favorite=True)
            .order_by(UserPoem.updated_at.desc()).all())
    return jsonify([{"poem": _poem_json(r.poem, True),
                    "tags": r.tag_list(), "note": r.note} for r in recs])


@api_bp.route("/poems/<int:poem_id>/favorite", methods=["POST"])
@api_login_required
def api_toggle_favorite(poem_id):
    u = get_token_user()
    db.get_or_404(Poem, poem_id)
    rec = _get_record(u.id, poem_id)
    rec.is_favorite = not rec.is_favorite
    db.session.commit()
    return jsonify(is_favorite=rec.is_favorite)


@api_bp.route("/notes")
@api_login_required
def api_notes():
    u = get_token_user()
    recs = UserPoem.query.filter_by(user_id=u.id).order_by(UserPoem.updated_at.desc()).all()
    recs = [r for r in recs if r.note or r.tags]
    return jsonify([{
        "poem": _poem_json(r.poem, r.is_favorite),
        "tags": r.tag_list(), "note": r.note,
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
    } for r in recs])


@api_bp.route("/poems/<int:poem_id>/note", methods=["PUT", "POST"])
@api_login_required
def api_save_note(poem_id):
    u = get_token_user()
    db.get_or_404(Poem, poem_id)
    data = request.get_json(silent=True) or {}
    note = (data.get("note") or "").strip()
    tags_raw = (data.get("tags") or "").strip()
    tags = ",".join(t for t in (x.strip() for x in tags_raw.replace("，", ",").split(",")) if t)[:200]
    rec = _get_record(u.id, poem_id)
    rec.note = note
    rec.tags = tags
    db.session.commit()
    return jsonify(is_favorite=rec.is_favorite, tags=rec.tag_list(), note=rec.note,
                  updated_at=rec.updated_at.strftime("%Y-%m-%d %H:%M:%S") if rec.updated_at else None)


@api_bp.route("/poems/<int:poem_id>/recite", methods=["POST"])
@api_login_required
def api_recite_checkin(poem_id):
    """背诵全对后的打卡（客户端本地判分，服务端只负责记录）"""
    u = get_token_user()
    db.get_or_404(Poem, poem_id)
    db.session.add(ReciteLog(user_id=u.id, poem_id=poem_id))
    db.session.commit()
    logs = ReciteLog.query.filter_by(user_id=u.id).order_by(ReciteLog.created_at.desc()).all()
    today = datetime.now().date()
    days = sorted({r.created_at.date() for r in logs}, reverse=True)
    streak = 0
    if days and (days[0] == today or (today - days[0]).days == 1):
        streak = 1
        for prev, cur in zip(days, days[1:]):
            if (prev - cur).days == 1:
                streak += 1
            else:
                break
    return jsonify(ok=True, today_checked=today in set(days), streak=streak,
                   total=len(logs), poems=len({r.poem_id for r in logs}))


@api_bp.route("/tags")
@api_login_required
def api_tags():
    u = get_token_user()
    recs = UserPoem.query.filter_by(user_id=u.id).all()
    stat = {}
    for r in recs:
        for t in r.tag_list():
            stat[t] = stat.get(t, 0) + 1
    return jsonify([{"name": t, "count": c}
                    for t, c in sorted(stat.items(), key=lambda x: -x[1])])


@api_bp.route("/tags/<name>")
@api_login_required
def api_tag_poems(name):
    u = get_token_user()
    recs = UserPoem.query.filter_by(user_id=u.id).all()
    recs = [r for r in recs if name in r.tag_list()]
    return jsonify([{"poem": _poem_json(r.poem, r.is_favorite),
                     "tags": r.tag_list(), "note": r.note} for r in recs])


@api_bp.route("/stats")
@api_login_required
def api_stats():
    u = get_token_user()
    records = UserPoem.query.filter_by(user_id=u.id).all()
    fav = sum(1 for r in records if r.is_favorite)
    note = sum(1 for r in records if r.note)
    tagged = sum(1 for r in records if r.tags)
    tag_stat, dyn_stat = {}, {}
    for r in records:
        for t in r.tag_list():
            tag_stat[t] = tag_stat.get(t, 0) + 1
        if r.is_favorite or r.note or r.tags:
            dyn_stat[r.poem.dynasty] = dyn_stat.get(r.poem.dynasty, 0) + 1
    total = Poem.query.count()
    touched = len({r.poem_id for r in records if r.is_favorite or r.note or r.tags})
    # 背诵打卡汇总
    logs = ReciteLog.query.filter_by(user_id=u.id).order_by(ReciteLog.created_at.desc()).all()
    today = datetime.now().date()
    days = sorted({r.created_at.date() for r in logs}, reverse=True)
    streak = 0
    if days and (days[0] == today or (today - days[0]).days == 1):
        streak = 1
        for prev, cur in zip(days, days[1:]):
            if (prev - cur).days == 1:
                streak += 1
            else:
                break
    return jsonify({
        "total_poems": total, "touched": touched,
        "favorite": fav, "note": note, "tagged": tagged,
        "tags": [{"name": t, "count": c} for t, c in sorted(tag_stat.items(), key=lambda x: -x[1])],
        "dynasties": [{"name": d, "count": c} for d, c in sorted(dyn_stat.items(), key=lambda x: -x[1])],
        "recite": {"today_checked": today in set(days), "streak": streak,
                   "total": len(logs), "poems": len({r.poem_id for r in logs})},
    })


@api_bp.route("/export")
@api_login_required
def api_export():
    u = get_token_user()
    recs = UserPoem.query.filter_by(user_id=u.id).order_by(UserPoem.poem_id).all()
    data = {
        "username": u.username,
        "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": [
            {"poem_id": r.poem_id, "title": r.poem.title, "author": r.poem.author,
             "dynasty": r.poem.dynasty, "is_favorite": r.is_favorite,
             "tags": r.tag_list(), "note": r.note}
            for r in recs if r.is_favorite or r.note or r.tags
        ],
    }
    return jsonify(data)
