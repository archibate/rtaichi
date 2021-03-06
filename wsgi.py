from multiprocessing import Process, RawArray, Queue
from flask import Flask, request, render_template, send_file
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocket
from base64 import b64encode
from gevent.pywsgi import WSGIServer
from threading import Thread
from gevent import Timeout
from PIL import Image
from io import BytesIO
import numpy as np
import ctypes
import struct
import time
import sys
import os

os.environ['TI_ARCH'] = 'cc'


B64 = 1
FPS = 2
SCALE = 1.6
QUALITY = 20


app = Flask('rtaichi')


@app.route('/')
@app.route('/index')
def index():
    app.logger.info('request /index')
    return render_template('index.html')


@app.route('/static/index.js')
def index_js():
    app.logger.info('request /static/index.js')
    return render_template('index.js')


def my_program():
    import examples.waterwave


class WorkerProcess:
    MAX_SHM_SIZE = 1920 * 1080 * 4

    def __init__(self, entry):
        self.entry = entry
        self.queue = Queue()
        self.raw = RawArray('B', self.MAX_SHM_SIZE)
        self.proc = Process(target=self.p_main, args=[], daemon=True)
        self.proc.start()
        self.joint = Thread(target=self.proc.join, args=[], daemon=True)
        self.joint.start()

    def do_key(self, type, key, x, y):
        x = float(x)
        y = float(y)
        event = type, key, x, y
        self.queue.put(event)

    def p_main(worker):
        import taichi as ti
        import numpy as np

        class RemoteGUI(ti.GUI):
            def __init__(self, *args, **kwargs):
                assert not kwargs.get('fast_gui', False)
                kwargs.setdefault('show_gui', False)
                super().__init__(*args, **kwargs)
                self.cursor_pos = 0, 0

            def show(self, *args, **kwargs):
                img = self.get_image()
                worker.p_update(img)
                super().show(*args, **kwargs)

            def get_cursor_pos(self):
                return self.cursor_pos

            def has_key_event(self):
                return not worker.queue.empty()

            def get_key_event(self):
                type, key, x, y = worker.queue.get()

                e = self.Event()
                e.type = getattr(self, type)
                e.key = getattr(self, key, key.lower())
                e.pos = x, y
                e.modifier = []
                self.cursor_pos = x, y

                if e.key == self.WHEEL:
                    raise NotImplementedError
                else:
                    e.delta = (0, 0)

                for mod in ['Shift', 'Alt', 'Control']:
                    if self.is_pressed(mod):
                        e.modifier.append(mod)

                if e.type == self.PRESS:
                    self.key_pressed.add(e.key)
                else:
                    self.key_pressed.discard(e.key)
                return e

        RemoteGUI._wrapped = ti.GUI
        ti.GUI = RemoteGUI

        worker.entry()

    def p_update(self, img):
        img = img[:, ::-1, :3].swapaxes(0, 1)
        img = np.ascontiguousarray(np.uint8(img * 255))
        h, w, _ = img.shape
        for i, b in enumerate(struct.pack('<ii', w, h)):
            self.raw[i] = b

        imgbuf = ctypes.addressof(self.raw) + 8
        if h * w * 3 > self.MAX_SHM_SIZE:
            raise ValueError(f'image size too big: {w}x{h}x3')
        ctypes.memmove(imgbuf, img.ctypes.data, w * h * 3)

    def request_frame(self):
        w, h = struct.unpack('<ii', bytes(self.raw[:8]))
        if h <= 0 or w <= 0 or h * w * 3 > self.MAX_SHM_SIZE:
            return 0, 0, b''

        imgbuf = ctypes.addressof(self.raw) + 8
        img = ctypes.string_at(imgbuf, w * h * 3)

        im = Image.new('RGB', (w, h))
        im.frombytes(img)
        w = int(w / SCALE)
        h = int(h / SCALE)
        im = im.resize((w, h))
        with BytesIO() as f:
            im.save(f, 'jpeg', quality=QUALITY, optimize=True)
            im = f.getvalue()
        return w, h, im


@app.route('/wsock')
def wsock():
    app.logger.info('request /wsock')
    ws = request.environ.get('wsgi.websocket')
    assert isinstance(ws, WebSocket)

    wp = WorkerProcess(my_program)
    while not ws.closed:
        w, h, im = wp.request_frame()
        if B64:
            im = f'{w:04d}{h:04d}' + b64encode(im).decode('ascii')
        else:
            im = struct.pack('<ii', w, h) + im
        ws.send(im)

        with Timeout(1 / FPS, False):
            msg = ws.receive()
            if msg is not None:
                cmd, *args = msg.split(':')
                app.logger.debug('ws received:', cmd, args)
                getattr(wp, f'do_{cmd}', lambda *x: x)(*args)

    app.logger.info('ws closed')
    wp.proc.kill()
    return ''


if __name__ == '__main__':
    os.system('clear')
    host, port = '0.0.0.0', 3389
    print(f'listening at {host}:{port}')
    server = WSGIServer((host, port), app, handler_class=WebSocketHandler)
    server.serve_forever()
