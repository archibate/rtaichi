from multiprocessing import Process, RawArray
from flask import Flask, request, render_template, send_file
from geventwebsocket.handler import WebSocketHandler
from geventwebsocket.websocket import WebSocket
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


app = Flask('falcon9')


@app.route('/')
@app.route('/index')
def index():
    print('request /index')
    return render_template('index.html')


def my_program():
    import examples.simple_uv


class WorkerProcess:
    MAX_SHM_SIZE = 1920 * 1080 * 4

    def __init__(self, entry):
        self.entry = entry
        self.raw = RawArray('B', self.MAX_SHM_SIZE)
        self.proc = Process(target=self.p_main, args=[], daemon=True)
        self.proc.start()
        self.joint = Thread(target=self.proc.join, args=[], daemon=True)
        self.joint.start()

    def p_main(worker):
        import taichi as ti
        import numpy as np

        class RemoteGUI(ti.GUI):
            def __init__(self, *args, **kwargs):
                assert not kwargs.get('fast_gui', False)
                kwargs.setdefault('show_gui', False)
                super().__init__(*args, **kwargs)

            def show(self, *args, **kwargs):
                img = self.get_image()
                worker.p_update(img)
                super().show(*args, **kwargs)

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
        h, w = struct.unpack('<ii', bytes(self.raw[:8]))
        if h <= 0 or w <= 0 or h * w * 3 > self.MAX_SHM_SIZE:
            return struct.pack('<ii', 0, 0)

        imgbuf = ctypes.addressof(self.raw) + 8
        img = ctypes.string_at(imgbuf, w * h * 3)

        im = Image.new('RGB', (w, h))
        im.frombytes(img)
        with BytesIO() as f:
            im.save(f, 'jpeg')
            im = f.getvalue()

        im = struct.pack('<ii', w, h) + im
        return im


@app.route('/wsock')
def wsock():
    print('request /wsock')
    ws = request.environ.get('wsgi.websocket')
    assert isinstance(ws, WebSocket)

    wp = WorkerProcess(my_program)
    while not ws.closed:
        im = wp.request_frame()
        ws.send(im)

        with Timeout(1 / 24, False):
            cmd = ws.receive()
            print('ws received:', cmd)

    print('ws closed')
    wp.proc.kill()
    return ''


if __name__ == '__main__':
    os.system('clear')
    host, port = '0.0.0.0', 8123
    print(f'listening at {host}:{port}')
    server = WSGIServer((host, port), app, handler_class=WebSocketHandler)
    server.serve_forever()
