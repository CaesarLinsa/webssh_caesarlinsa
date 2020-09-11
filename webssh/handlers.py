# -*- encoding:utf-8 -*-
import tornado.web
from tornado.web import stream_request_body
import tornado.websocket
import tornado.httpserver
import tornado.ioloop
from tornado.ioloop import IOLoop
import paramiko
from tornado.process import cpu_count
import logging
import socket
import traceback
import json
import os
from concurrent.futures import ThreadPoolExecutor
import weakref
from worker import Worker, recycle_worker, clients
import struct
import uuid
try:
    from types import UnicodeType
except ImportError:
    UnicodeType = str
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError
from tornado.concurrent import run_on_executor
from tornado_sqlalchemy import SQLAlchemy
from tornado_sqlalchemy import SessionMixin
from model import SSHConnection, UploadProgress
from tornadostreamform.multipart_streamer import MultiPartStreamer

TMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmp_dir")

db = SQLAlchemy("sqlite:///webssh.sqlite")

MB = 1024 * 1024
GB = 1024 * MB
MAX_STREAM_SIZE = 5 * GB


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("username")


class RegisterConnectionHandler(SessionMixin, BaseHandler):

    def get(self):
        self.render("connection_register.html", edit=False)

    def post(self):
        id = self.get_argument("id")
        alias_name = self.get_argument("alias_name")
        hostname = self.get_argument("hostname")
        port = self.get_argument("port")
        username = self.get_argument("username")
        password = self.get_argument("password")
        # 添加ssh连接记录
        if not id:
            with self.make_session() as session:
                session.add(SSHConnection(alias_name=alias_name, hostname=hostname, port=port, username=username, password=password))
                session.commit()
        else:
            with self.make_session() as session:
                session.query(SSHConnection).filter_by(id=id).update({
                    "alias_name": alias_name,
                    "hostname": hostname,
                    "port": port,
                    "username": username,
                    "password": password})

                session.commit()
        # 更新ssh连接记录
        self.redirect("/connection/list")


class ConnectionListHandler(SessionMixin, BaseHandler):

    def get(self):
        return self.render("connection_list.html")


class ConnectionShowHandler(SessionMixin, BaseHandler):

    def get(self, worker_id):
        return self.render("index.html", worker_id=worker_id)


class ConnectionEditHandler(SessionMixin, BaseHandler):

    def get(self, connection_id):
        res = {}
        with self.make_session() as session:
            connection = session.query(SSHConnection).filter_by(id=connection_id).first()
            if connection:
                res["id"] = connection.id
                res["alias_name"] = connection.alias_name
                res["hostname"] = connection.hostname
                res["port"] = connection.port
                res["username"] = connection.username
                res["password"] = connection.password
        return self.render("connection_register.html", edit=True, **res)


class ConnectionDataHandler(SessionMixin, BaseHandler):

    def get(self):
        res = []
        with self.make_session() as session:
            connections = session.query(SSHConnection).all()
            for connection in connections:
                res.append({
                    "id": "<a href='%s'>%s</a>" % (connection.id, connection.id),
                    "alias_name": connection.alias_name,
                    "hostname": connection.hostname,
                    "port": connection.port,
                    "username": connection.username,
                    "connection": "<input type='submit' "
                                  "class='btn btn-primary' onclick='ws_connect(this)' id=%s value='连接'>"
                                  % str(connection.id),
                    "sftp": "<submit class='btn btn-primary' data-toggle='modal'"
                            "data-target='#myModal' id=%s>文件上传</submit>" % str(connection.id)
                })
        self.write(json.dumps(res))


@stream_request_body
class ConnectionUploadHandler(SessionMixin, BaseHandler):
    executor = ThreadPoolExecutor(max_workers=cpu_count() * 5)

    def update_upload_progress(self, filename, value, task_id, rel_filename=None, total=None, create=True):
        up = UploadProgress(filename=filename, cur_value=value, total=total, rel_filename=rel_filename, task_id=task_id)
        with self.make_session() as session:
            if create:
                session.add(up)
            else:
                data = {"cur_value": value, "task_id": task_id }
                if total:
                    data.update({"total": total})
                if rel_filename:
                    data.update({"rel_filename": rel_filename})
                session.query(UploadProgress).filter_by(filename=filename).update(data)
            session.commit()

    def initialize(self):
        self.chunk_bytes = 0

    def prepare(self):
        if self.request.method.lower() == "post":
            self.request.connection.set_max_body_size(MAX_STREAM_SIZE)
        try:
            total = int(self.request.headers.get("Content-Length", "0"))
        except KeyError:
            total = 0
        # 每次请求创建临时目录，上传完成后，清除目录
        # 保证并行上传，或其他请求
        uuid_str = str(uuid.uuid4())
        tmp_dir = os.path.join(TMP_DIR, uuid_str)
        if not os.path.exists(tmp_dir):
            os.mkdir(tmp_dir)
        self.ps = MultiPartStreamer(total, tmp_dir=tmp_dir)
        self.update_upload_progress(filename=uuid_str, value=0, total=total, task_id=1)

    @run_on_executor
    def data_received(self, chunk):
        self.chunk_bytes += len(chunk)
        self.ps.data_received(chunk)
        if self.ps.get_parts_by_name("upload_file"):
            rel_filename = self.ps.get_parts_by_name("upload_file")[0].get_filename()
        self.update_upload_progress(filename=os.path.basename(self.ps.tmp_dir),
                                    value=self.chunk_bytes, task_id=1, rel_filename=rel_filename, create=False)

    @tornado.gen.coroutine
    def post(self):
        try:
            self.ps.data_complete()
            id = filedir = filepath = None
            # 三个part， 第一个文件，第二个filepath， 第三个id
            for part in self.ps.parts:
                if part.get_filename():
                    filepath = os.path.join(os.path.dirname(part.f_out.name),
                                            part.get_filename())
                    part.move(filepath)
                if part.get_name() == "id":
                    id = int(part.get_payload())
                if part.get_name() == "filepath":
                    filedir = part.get_payload()
            self.ps.release_parts()
            if filepath or filedir:
                if id:
                    with self.make_session() as session:
                        connection = session.query(SSHConnection).filter_by(id=id).first()
                        futrue = self.executor.submit(self.ftp_upload, connection, filepath, filedir)
                        yield futrue
                else:
                    self.write({"status": 500, "result": "id is None"})
            else:
                self.write({"status": 500, "result": "file path is None"})
        except Exception as e:
            self.write({"status": 500, "result": str(e)})
            raise e
        self.write({"status": 200, "result": ""})

    def ftp_upload(self, connection, filepath, filedir):

        def callback(cur, total):
            uuid_str = os.path.basename(os.path.dirname(filepath))
            self.update_upload_progress(filename=uuid_str, value=cur, total=total, task_id=2, create=False)

        ftp_transport = paramiko.Transport(connection.hostname, connection.port)
        ftp_transport.connect(username=connection.username, password=connection.password)
        sftp_client = paramiko.SFTPClient.from_transport(ftp_transport)
        filename = os.path.basename(filepath)
        if connection.username != "root":
            target_file = "%s/%s" % (bytes.decode(filedir), filename) if filedir else "/home/%s/%s" % (connection.username, filename)
        else:
            target_file = "%s/%s" % (bytes.decode(filedir), filename) if filedir else "/root/%s" % filename
        sftp_client.put(filepath, target_file, callback=callback)
        self.rm_file(filepath)

    def rm_file(self, filepath):
        work_dir = os.path.dirname(filepath)
        files = os.listdir(work_dir)
        for file in files:
            os.remove(os.path.join(work_dir, file))
        os.rmdir(work_dir)


class UploadProgressHandler(SessionMixin, BaseHandler):

    def post(self):
        res = {}
        rel_filename = self.get_argument("filename")
        with self.make_session() as session:
            up = session.query(UploadProgress).filter_by(rel_filename=rel_filename).first()
            if up:
                if up.task_id == 1:
                    res['progress'] = float(up.cur_value/up.total) * 0.5
                elif up.task_id == 2:
                    res['progress'] = 0.5 + float(up.cur_value / up.total) * 0.5
            else:
                res['progress'] = 0
            if res.get("progress") >= 1:
                session.delete(up)
        self.write(res)


class ConnectionDeleteHandler(SessionMixin, BaseHandler):

    def delete(self, worker_id):
        with self.make_session() as session:
            connection = session.query(SSHConnection).filter_by(id=worker_id).first()
            session.delete(connection)
            session.commit()


class LoginHandler(SessionMixin, BaseHandler):
    executor = ThreadPoolExecutor(max_workers=cpu_count() * 5)

    def initialize(self, loop=None):
        self.loop = loop
        self.result = dict(id=None, status=None)

    def get(self):
        id = self.get_argument("id")
        res = {}
        with self.make_session() as session:
            connection = session.query(SSHConnection).filter_by(id=id).first()
            if connection:
                res["hostname"] = connection.hostname
                res["port"] = connection.port
                res["username"] = connection.username
                res["password"] = connection.password
        self.write(json.dumps(res))

    def get_args(self):
        hostname = self.get_argument("hostname")
        port = self.get_argument("port")
        username = self.get_argument("username")
        password = self.get_argument("password")
        args = (hostname, port, username, password)
        logging.debug(args)
        return args

    def get_ssh_client(self):
        sshclient = paramiko.SSHClient()
        sshclient.load_system_host_keys()
        sshclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return sshclient

    def ssh_connect(self, args):
        ssh = self.get_ssh_client()
        dst_addr = args[:2]
        logging.info('Connecting to {}:{}'.format(*dst_addr))

        try:
            ssh.connect(*args, timeout=10)
        except socket.error:
            raise ValueError('Unable to connect to {}:{}'.format(*dst_addr))
        except paramiko.BadAuthenticationType:
            raise ValueError('Bad authentication type.')
        except paramiko.AuthenticationException:
            raise ValueError('Authentication failed.')
        except paramiko.BadHostKeyException:
            raise ValueError('Bad host key.')

        term = self.get_argument('term', u'') or u'xterm'
        chan = ssh.invoke_shell(term=term)
        chan.setblocking(0)
        worker = Worker(self.loop, ssh, chan, dst_addr)
        worker.encoding = "utf-8"
        return worker

    @tornado.gen.coroutine
    def post(self):
        ip, port = self.request.connection.context.address[:2]
        workers = clients.get(ip, {})
        if workers and len(workers) >= 10:
            raise tornado.web.HTTPError(403, 'Too many live connections.')
        args = self.get_args()
        future = self.executor.submit(self.ssh_connect, args)

        try:
            worker = yield future
        except (ValueError, paramiko.SSHException) as exc:
            logging.error(traceback.format_exc())
            self.result.update(status=str(exc))
        else:
            if not workers:
                clients[ip] = workers
            worker.src_addr = (ip, port)
            workers[worker.id] = worker
            self.loop.call_later(3, recycle_worker,
                                 worker)
            self.result.update(id=worker.id, hostname=args[0])

        self.write(self.result)


class WebSocketHandler(tornado.websocket.WebSocketHandler):

    def initialize(self, loop):
        self.loop = loop
        self.worker_ref = None

    def open(self):
        self.src_addr = self.request.connection.context.address[:2]
        logging.info('Connected from {}:{}'.format(*self.src_addr))

        workers = clients.get(self.src_addr[0])
        if not workers:
            self.close(reason='Websocket authentication failed.')
            return

        try:
            worker_id = self.get_argument('id')
        except (tornado.web.MissingArgumentError, Exception) as exc:
            self.close(reason=str(exc))
        else:
            worker = workers.get(worker_id)
            if worker:
                workers[worker_id] = None
                self.set_nodelay(True)
                worker.set_handler(self)
                self.worker_ref = weakref.ref(worker)
                self.loop.add_handler(worker.fd, worker, IOLoop.READ)
            else:
                self.close(reason='Websocket authentication failed.')

    def on_message(self, message):
        logging.debug('{!r} from {}:{}'.format(message, *self.src_addr))
        worker = self.worker_ref()
        try:
            msg = json.loads(message)
        except JSONDecodeError:
            return

        if not isinstance(msg, dict):
            return

        resize = msg.get('resize')
        if resize and len(resize) == 2:
            try:
                worker.chan.resize_pty(*resize)
            except (TypeError, struct.error, paramiko.SSHException):
                pass

        data = msg.get('data')
        # 控制台输入字符，写入channel
        if data and isinstance(data, UnicodeType):
            worker.data_to_dst.append(data)
            worker.on_write()

    def on_close(self):
        logging.info('Disconnected from {}:{}'.format(*self.src_addr))
        if not self.close_reason:
            self.close_reason = 'client disconnected'

        worker = self.worker_ref() if self.worker_ref else None
        if worker:
            worker.close(reason=self.close_reason)


class Application(tornado.web.Application):
    def __init__(self, loop):
        handlers = [

            (r'/', RegisterConnectionHandler),
            (r'/connection/(\d+)', ConnectionEditHandler),
            (r'/connection/data', ConnectionDataHandler),
            (r'/upload', ConnectionUploadHandler),
            (r'/upload/progress', UploadProgressHandler),
            (r'/connection/delete/(\d+)', ConnectionDeleteHandler),
            (r'/connection/list', ConnectionListHandler),
            (r'/connection/\d+\.\d+\.\d+\.\d+/(\d+)', ConnectionShowHandler),
            (r'/login', LoginHandler, dict(loop=loop)),
            (r'/ws', WebSocketHandler, dict(loop=loop))
        ]

        settings = {"template_path": "templates", "static_path": "static",
                    "cookie_secret": "bZJc2sWbQLKos6GkHn/VB9oXwQt8S0R0kRvJ5/xJ89E="}
        tornado.web.Application.__init__(self, handlers, db=db, **settings)


if __name__ == '__main__':
    loop = tornado.ioloop.IOLoop.current()
    ws_app = Application(loop)
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(8090)
    loop.start()
