from tornado_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, String, SMALLINT, INTEGER

db = SQLAlchemy("sqlite:///webssh.sqlite")


class SSHConnection(db.Model):
    __tablename__ = "SSHConnection"
    id = Column(INTEGER,
                primary_key=True,
                autoincrement=True)
    hostname = Column(String(length=50))
    port = Column(SMALLINT)
    username = Column(String(50))
    password = Column(String(100))


class UploadProgress(db.Model):
    __tablename__ = "UploadProgress"
    id = Column(INTEGER,
                primary_key=True,
                autoincrement=True)
    # 临时uuid目录名
    filename = Column(String(100))
    # 上传的文件名
    rel_filename = Column(String(100))
    cur_value = Column(INTEGER)
    total = Column(INTEGER)
    task_id = Column(SMALLINT)


def init():
    db.create_all()
