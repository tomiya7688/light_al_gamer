"""画像だけの軽量特徴抽出。地形や達成状態の確定判定ではない。"""

from PIL import Image, ImageChops, ImageStat

from .models import VisualFeedback, VisualObservation


def has_crosshair(image: Image.Image) -> bool:
    # Vanillaの中央十字を複数GUIスケールで照合する。色は背景で反転し得る。
    gray = image.convert("L")
    cx, cy = image.width // 2, image.height // 2
    for scale in range(1, 5):
        reach = 5 * scale
        if cx <= reach + 2 or cy <= reach + 2:
            continue
        arms = [
            gray.getpixel((cx + dx, cy + dy))
            for dx, dy in ((-reach, 0), (reach, 0), (0, -reach), (0, reach))
        ]
        corners = [
            gray.getpixel((cx + dx, cy + dy))
            for dx, dy in (
                (-reach, -reach),
                (reach, -reach),
                (-reach, reach),
                (reach, reach),
            )
        ]
        if abs(sum(arms) - sum(corners)) / 4 >= 50 and max(arms) - min(arms) <= 45:
            return True
    return False


class VisualPerception:
    def observe(self, screenshot: Image.Image) -> VisualObservation:
        if screenshot.width < 160 or screenshot.height < 120:
            raise ValueError("Game client image must be at least 160x120")
        image = screenshot.convert("RGB").resize((128, 96))
        stat = ImageStat.Stat(image)
        ground = list(image.crop((32, 48, 96, 80)).get_flattened_data())
        center = list(image.crop((54, 32, 74, 62)).get_flattened_data())
        lava = sum(
            r > 165 and 45 < g < 170 and b < 75 and r > g * 1.35 for r, g, b in ground
        ) / len(ground)
        water = sum(
            b > 85 and b > r * 1.4 and b > g * 1.15 for r, g, b in ground
        ) / len(ground)
        brown = sum(
            45 < r < 175 and 25 < g < 140 and r > g * 1.15 and g > b * 1.2
            for r, g, b in center
        ) / len(center)
        brightness = sum(stat.mean) / 3
        return VisualObservation(
            usable=sum(stat.stddev) > 12 and 3 < brightness < 252,
            crosshair=has_crosshair(screenshot),
            lava_fraction=lava,
            water_fraction=water,
            brown_fraction=brown,
            brightness=brightness,
        )


class VisualEvaluator:
    def evaluate(self, before: Image.Image, after: Image.Image) -> VisualFeedback:
        if before.size != after.size:
            raise ValueError("Game window resized during action; stopping")
        # HUDやタイル数を読まず、中央視野の変化だけを測る。
        width, height = before.size
        region = (width // 8, height // 6, width * 7 // 8, height * 4 // 5)
        left = before.convert("RGB").crop(region).resize((64, 48))
        right = after.convert("RGB").crop(region).resize((64, 48))
        motion = sum(ImageStat.Stat(ImageChops.difference(left, right)).mean) / (
            3 * 255
        )
        return VisualFeedback(motion=motion, changed=motion >= 0.008)
