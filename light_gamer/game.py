"""独立した2048ゲーム。公開I/Oは画面PNGとキーだけ。"""

import argparse
import io
import random
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import Image, ImageDraw, ImageFont

from .contracts import ACTIONS, Action
from .rules import legal_actions, slide
from .theme import BOARD_X, BOARD_Y, HEIGHT, PALETTE, PITCH, TILE, WIDTH


class Game2048:
    def __init__(self, seed: int = 7):
        self._rng = random.Random(seed)
        self._board = (0,) * 16
        self._score = 0
        self._spawn()
        self._spawn()

    def _spawn(self) -> None:
        empty = [i for i, value in enumerate(self._board) if value == 0]
        board = list(self._board)
        board[self._rng.choice(empty)] = 2 if self._rng.random() < 0.9 else 4
        self._board = tuple(board)

    def press(self, action: Action) -> None:
        board, reward = slide(self._board, action)
        if board != self._board:
            self._board = board
            self._score += reward
            self._spawn()

    def screenshot(self) -> Image.Image:
        # 同じフレームバッファをPNG出力と任意のGUI表示に使う。
        image = Image.new("RGB", (WIDTH, HEIGHT), (250, 248, 239))
        draw = ImageDraw.Draw(image)
        title = ImageFont.load_default(size=30)
        font = ImageFont.load_default(size=24)
        small = ImageFont.load_default(size=16)
        draw.text((24, 18), "2048 / Light AI Gamer", fill="#776e65", font=title)
        draw.text((24, 65), f"Score: {self._score}", fill="#776e65", font=font)
        draw.rounded_rectangle((16, 104, 464, 552), radius=10, fill="#bbada0")
        for index, value in enumerate(self._board):
            x = BOARD_X + index % 4 * PITCH
            y = BOARD_Y + index // 4 * PITCH
            draw.rounded_rectangle(
                (x, y, x + TILE - 1, y + TILE - 1),
                radius=6,
                fill=PALETTE.get(value, (40, 40, 40)),
            )
            if value:
                draw.text(
                    (x + TILE // 2, y + TILE // 2),
                    str(value),
                    anchor="mm",
                    fill="#776e65" if value <= 4 else "white",
                    font=font,
                )
        status = "GAME OVER" if not legal_actions(self._board) else "Arrow keys to play"
        draw.text((24, 566), status + " | Tomiya", fill="#776e65", font=small)
        return image


def make_server(seed: int, port: int = 0) -> HTTPServer:
    game = Game2048(seed)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data = VIEWER_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if self.path != "/frame.png":
                self.send_error(404)
                return
            buffer = io.BytesIO()
            game.screenshot().save(buffer, format="PNG")
            data = buffer.getvalue()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/key":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 8:
                self.send_error(400)
                return
            action = self.rfile.read(length).decode("ascii", errors="replace")
            if action not in ACTIONS:
                self.send_error(400)
                return
            game.press(action)
            # 成功応答には盤面・スコア・乱数・ターン番号を含めない。
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    return HTTPServer(("127.0.0.1", port), Handler)


# 表示DOMは画像だけ。盤面数値をHTMLやJavaScriptに渡さない。
VIEWER_HTML = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>2048 - Tomiya</title><style>
body{background:#faf8ef;display:grid;justify-content:center;font:16px sans-serif}
img{max-width:100%;height:auto}button{padding:12px;margin:3px}
</style><img id="screen" alt="2048 game screen" src="/frame.png">
<div><button data-key="left">Left</button><button data-key="up">Up</button>
<button data-key="down">Down</button><button data-key="right">Right</button></div>
<script>
let busy=false;
async function press(key){
 if(busy)return; busy=true;
 try{
  const response=await fetch('/key',{method:'POST',body:key});
  if(!response.ok)throw Error('Input failed');
  const frame=await fetch('/frame.png',{cache:'no-store'});
  const url=URL.createObjectURL(await frame.blob());
  const image=document.getElementById('screen'), old=image.src;
  image.onload=()=>URL.revokeObjectURL(old); image.src=url;
 }finally{busy=false;}
}
document.addEventListener('keydown',event=>{
 const key={ArrowLeft:'left',ArrowUp:'up',ArrowRight:'right',ArrowDown:'down'}[event.key];
 if(key){event.preventDefault();press(key);}
});
document.querySelectorAll('button').forEach(button=>button.onclick=()=>press(button.dataset.key));
</script></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    with make_server(args.seed, args.port) as server:
        print(server.server_port, flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
