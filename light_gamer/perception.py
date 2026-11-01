"""固定レイアウト2048の画素認識。未知の画面では操作を停止する。"""

from PIL import Image

from .contracts import Observation
from .theme import BOARD_X, BOARD_Y, HEIGHT, PALETTE, PITCH, WIDTH


class RecognitionError(ValueError):
    pass


class PalettePerception:
    def __init__(self, tolerance: int = 8):
        self.tolerance = tolerance

    def observe(self, screenshot: Image.Image) -> Observation:
        if screenshot.size != (WIDTH, HEIGHT):
            raise RecognitionError(f"Unexpected image size: {screenshot.size}")
        image = screenshot.convert("RGB")
        cells = []
        worst = 0
        for index in range(16):
            x = BOARD_X + index % 4 * PITCH
            y = BOARD_Y + index // 4 * PITCH
            # 数字や角丸を避けた複数画素で色を照合する。
            samples = [
                image.getpixel((x + dx, y + dy))
                for dx, dy in ((14, 14), (84, 14), (14, 84), (84, 84))
            ]
            matches = []
            for pixel in samples:
                distance, value = min(
                    (max(abs(a - b) for a, b in zip(pixel, color)), value)
                    for value, color in PALETTE.items()
                )
                if distance > self.tolerance:
                    raise RecognitionError(
                        f"Unknown tile color at cell {index}: {pixel}"
                    )
                worst = max(worst, distance)
                matches.append(value)
            if len(set(matches)) != 1:
                raise RecognitionError(f"Inconsistent tile samples at cell {index}")
            cells.append(matches[0])
        return Observation(tuple(cells), 1 - worst / (self.tolerance + 1))
