"""数据模型：用户 / 诗词 / 个人学习记录（收藏、标签、笔记）"""
from datetime import datetime

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    records = db.relationship("UserPoem", backref="user", lazy="dynamic",
                              cascade="all, delete-orphan")

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
