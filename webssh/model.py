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
