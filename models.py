"""数据模型：用户 / 诗词 / 个人学习记录（收藏、标签、笔记）"""
import secrets
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # 移动端 / API 鉴权令牌（Bearer Token）。网页端用 session，此字段可空。
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship("UserPoem", backref="user", lazy="dynamic",
                              cascade="all, delete-orphan")

    def refresh_token(self) -> str:
        """生成新的 API 令牌（登录 / 改密时调用，旧令牌即失效）"""
        self.api_token = secrets.token_hex(32)
        return self.api_token

    def set_password(self, raw: str):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, raw)


class Poem(db.Model):
    __tablename__ = "poems"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False, index=True)
    author = db.Column(db.String(64), nullable=False, index=True)
    dynasty = db.Column(db.String(32), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)          # 原文，换行分隔
    translation = db.Column(db.Text, default="")           # 译文
    annotation = db.Column(db.Text, default="")            # 注释
    appreciation = db.Column(db.Text, default="")          # 赏析
    background = db.Column(db.Text, default="")            # 创作背景：写作时作者人生阶段/经历
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class UserPoem(db.Model):
    """每个用户对每首诗词的个人记录：收藏 / 标签 / 笔记，三者合一"""
    __tablename__ = "user_poems"
    __table_args__ = (db.UniqueConstraint("user_id", "poem_id", name="uq_user_poem"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    poem_id = db.Column(db.Integer, db.ForeignKey("poems.id"), nullable=False, index=True)
    is_favorite = db.Column(db.Boolean, default=False, nullable=False)
    tags = db.Column(db.String(256), default="")   # 逗号分隔的自定义标签
    note = db.Column(db.Text, default="")          # 个人学习笔记
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    poem = db.relationship("Poem")

    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]


class Author(db.Model):
    """作者信息表：生平简介、字号、生卒年。

    与 Poem 解耦——Poem.author 仍是自由字符串，Author 仅作为可选的「生平档案」。
    某作者没有档案时，作者页正常显示诗词列表，仅提示「暂无简介」。
    """

    __tablename__ = "authors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False, index=True)
    dynasty = db.Column(db.String(32), default="")        # 朝代，如「唐」
    zihao = db.Column(db.String(128), default="")         # 字号，如「字太白，号青莲居士」
    birth_year = db.Column(db.String(16), default="")     # 生年（字符串容错，如 701 / 约701）
    death_year = db.Column(db.String(16), default="")     # 卒年
    bio = db.Column(db.Text, default="")                  # 生平简介（概述性文字）


class ReciteLog(db.Model):
    """背诵打卡记录：每次全对通过背诵记一条。

    「今日打卡」= 今天有至少一条记录；「连续天数」按本地日期计算。
    同一首诗一天可多次通过（都记录，便于看练习次数）。
    """

    __tablename__ = "recite_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    poem_id = db.Column(db.Integer, db.ForeignKey("poems.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now, index=True)  # 本地时间（容器 TZ=Asia/Shanghai）

    poem = db.relationship("Poem")
