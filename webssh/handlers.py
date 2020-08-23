# -*- encoding:utf-8 -*-

import tornado.web
import tornado.websocket
import tornado.httpserver
import tornado.ioloop
from tornado.ioloop import  IOLoop
import paramiko
from tornado.process import cpu_count
import logging
import socket
import struct
import traceback
import json
from concurrent.futures import ThreadPoolExecutor
from worker import Worker
import weakref
from webssh.worker import Worker, recycle_worker, clients
try:
    from types import UnicodeType
except ImportError:
    UnicodeType = str
try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        return self.get_secure_cookie("username")


class LoginHandler(BaseHandler):
    executor = ThreadPoolExecutor(max_workers=cpu_count() * 5)

    def initialize(self, loop=None):
        self.loop = loop
        self.result = dict(id=None, status=None)

    def get(self):
        self.render('index.html')

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
            ssh.connect(*args, timeout=30)
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
            self.result.update(id=worker.id)

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
            (r'/', LoginHandler, dict(loop=loop)),
            (r'/ws', WebSocketHandler, dict(loop=loop))
        ]

        settings = {"template_path": "templates", "static_path": "static",
                    "cookie_secret": "bZJc2sWbQLKos6GkHn/VB9oXwQt8S0R0kRvJ5/xJ89E="}
        tornado.web.Application.__init__(self, handlers, **settings)


if __name__ == '__main__':
    loop = tornado.ioloop.IOLoop.current()
    ws_app = Application(loop)
    server = tornado.httpserver.HTTPServer(ws_app)
    server.listen(8090)
    loop.start()
