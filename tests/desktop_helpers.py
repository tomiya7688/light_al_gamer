"""Minecraft実機ではない、画像・入力境界のテスト専用fixture。"""

from PIL import Image, ImageDraw


def scene(step=0, kind="terrain", crosshair=True):
    image = Image.new("RGB", (640, 360), (100, 155, 220))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 180, 639, 359), fill=(50, 110 + step % 50, 45))
    for x in range(-80, 720, 80):
        offset = (step * 19) % 80
        draw.polygon(
            (
                (x + offset, 180),
                (x + offset + 40, 180),
                (x + offset + 70, 330),
                (x + offset, 330),
            ),
            fill=(80, 150, 65),
        )
    if kind == "lava":
        draw.rectangle((160, 185, 480, 300), fill=(240, 95, 20))
    if kind == "water":
        draw.rectangle((160, 185, 480, 300), fill=(30, 65, 180))
    if kind == "wood":
        draw.rectangle((260, 115, 380, 245), fill=(115, 75, 35))
    if crosshair:
        draw.line((312, 180, 328, 180), fill="white", width=3)
        draw.line((320, 172, 320, 188), fill="white", width=3)
    return image


class Clock:
    def __init__(self):
        self.now = 0.0
        self.on_sleep = None

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        if self.on_sleep:
            self.on_sleep()


class FakeNative:
    def __init__(self):
        self.focus = 10
        self.exists = True
        self.stop = False
        self.events = []
        self.user_keys = set()
        self.user_buttons = set()
        self.closed = False
        self.raise_on = None

    def valid(self, window):
        return self.exists

    def foreground(self):
        return self.focus

    def stop_pressed(self):
        return self.stop

    def key_pressed(self, key):
        return key in self.user_keys

    def button_pressed(self, button):
        return button in self.user_buttons

    def key(self, value, down):
        self.events.append(("key", value, down))
        if self.raise_on == (value, down):
            raise OSError("injected input failure")

    def button(self, value, down):
        self.events.append(("button", value, down))

    def move(self, dx, dy):
        self.events.append(("move", dx, dy))

    def point(self, hwnd, x, y):
        self.events.append(("point", hwnd, x, y))

    def wheel(self, amount):
        self.events.append(("wheel", amount))

    def capture(self, hwnd, mode):
        self.events.append(("capture", hwnd, mode))
        return scene()

    def close(self):
        self.closed = True
