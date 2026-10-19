"""10-19 开跑当天用的最小本地服务：只把 `/mandala` 与 `/vr_assets/**` 开在 127.0.0.1:8777。

为什么不起生产 console_server：那条路由（`console_server.py:2229 @app.get("/mandala")`）
会连带起监测、SSE 与档案面——真机体验只需这一个静态页。少起一面＝少一面副作用，
且本窗不碰数据根。头显侧经 `adb reverse tcp:8777 tcp:8777` 走的就是这个 8777。

用法：`python _analysis_tmp/serve_mandala_8777.py`（Ctrl+C 停）。
起前请先现查端口空：`netstat -ano | grep :8777`（有输出＝别抢，先报 W3）。
"""
import os
import http.server as H
import datetime

ROOT = os.getcwd()
MIME = {".js": "text/javascript; charset=utf-8", ".html": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8", ".wasm": "application/wasm"}


class Handler(H.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/mandala":
            f = os.path.join(ROOT, "vr_mandala.html")
        elif path.startswith("/vr_assets/"):
            f = os.path.join(ROOT, path.lstrip("/").replace("..", ""))
        else:
            self.send_error(404)
            return
        if not os.path.isfile(f):
            self.send_error(404)
            return
        body = open(f, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(f)[1],
                                                 "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *a):
        print(f"{datetime.datetime.now().strftime('%H:%M:%S')} {fmt % a}", flush=True)


if __name__ == "__main__":
    src = os.path.join(ROOT, "vr_mandala.html")
    print(f"服务起 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
          f"｜正源 {src}｜{os.path.getsize(src)} B"
          f"｜mtime {datetime.datetime.fromtimestamp(os.stat(src).st_mtime):%m-%d %H:%M:%S}"
          f"｜Ctrl+C 停", flush=True)
    H.ThreadingHTTPServer(("127.0.0.1", 8777), Handler).serve_forever()
