import pytest
from PIL import Image, ImageDraw

from light_gamer.game import Game2048
from light_gamer.perception import PalettePerception, RecognitionError
from light_gamer.theme import BOARD_X, BOARD_Y, HEIGHT, PALETTE, PITCH, TILE, WIDTH


def test_every_supported_color_from_pixels():
    # ゲームの状態を使わず、独立に生成した画面fixtureを認識する。
    values = list(PALETTE)
    for start in (0, 1):
        expected = tuple(values[start : start + 16])
        image = Image.new("RGB", (WIDTH, HEIGHT))
        draw = ImageDraw.Draw(image)
        for index, value in enumerate(expected):
            x = BOARD_X + index % 4 * PITCH
            y = BOARD_Y + index // 4 * PITCH
            draw.rectangle((x, y, x + TILE - 1, y + TILE - 1), fill=PALETTE[value])
        result = PalettePerception().observe(image)
        assert result.board == expected
        assert result.confidence == 1


def test_rendered_game_round_trip():
    game = Game2048(4)
    for action in ("left", "up", "right", "down") * 5:
        game.press(action)
        # 内部状態へのアクセスはゲーム単体テストでだけ許容する。
        assert PalettePerception().observe(game.screenshot()).board == game._board


@pytest.mark.parametrize(
    "image", [Image.new("RGB", (10, 10)), Image.new("RGB", (WIDTH, HEIGHT), "magenta")]
)
def test_reject_unknown_screen(image):
    with pytest.raises(RecognitionError):
        PalettePerception().observe(image)


def test_reject_partial_overlay():
    image = Game2048().screenshot()
    image.putpixel((BOARD_X + 14, BOARD_Y + 14), PALETTE[128])
    with pytest.raises(RecognitionError, match="Inconsistent"):
        PalettePerception().observe(image)
