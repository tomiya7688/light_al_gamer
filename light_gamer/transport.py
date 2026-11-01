"""画像取得とキー入力のHTTPアダプター。盤面APIを持たない。"""

import io
import queue
import subprocess
import sys
import threading
from urllib.request import ProxyHandler, Request, build_opener

from PIL import Image

from .contracts import ACTIONS, Action


class HttpGamePort:
    def __init__(self, port: int):
        self.base = f"http://127.0.0.1:{port}"
        # ローカルゲームの通信を外部プロキシへ送信しない。
        self._http = build_opener(ProxyHandler({}))

    def capture(self) -> Image.Image:
        with self._http.open(self.base + "/frame.png", timeout=5) as response:
            if response.headers.get_content_type() != "image/png":
                raise ValueError("Expected screenshot PNG")
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError("Screenshot too large")
        with Image.open(io.BytesIO(data)) as image:
            return image.convert("RGB")

    def press(self, action: Action) -> None:
        if action not in ACTIONS:
            raise ValueError(f"Unknown action: {action}")
        request = Request(
            self.base + "/key", data=action.encode("ascii"), method="POST"
        )
        with self._http.open(request, timeout=5) as response:
            if response.status != 204:
                raise ValueError("Key not acknowledged")


class GameProcess:
    def __init__(self, seed: int):
        self.seed = seed
        self.process = None

    def __enter__(self) -> HttpGamePort:
        self.process = subprocess.Popen(
            [sys.executable, "-m", "light_gamer.game", "--seed", str(self.seed)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        lines = queue.Queue()
        threading.Thread(
            target=lambda: lines.put(self.process.stdout.readline()), daemon=True
        ).start()
        try:
            port = int(lines.get(timeout=10).strip())
            if not 1 <= port <= 65535:
                raise ValueError("Invalid port")
            return HttpGamePort(port)
        except Exception:
            self.close()
            raise RuntimeError("Game failed to start within 10 seconds") from None

    def close(self):
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.process.stdout.close()

    def __exit__(self, *args):
        self.close()
