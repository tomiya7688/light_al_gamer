"""観測→判断→入力→再観測→評価を繰り返し、実行証跡を保存する。"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .contracts import InputPort, Perception, Policy, ResultEvaluator, ScreenSource
from .evaluation import TransitionEvaluator
from .perception import PalettePerception
from .policy import ExpectimaxPolicy
from .transport import GameProcess


def run_session(
    screens: ScreenSource,
    inputs: InputPort,
    perception: Perception,
    policy: Policy,
    evaluator: ResultEvaluator,
    output: Path,
    turns: int,
) -> dict:
    if turns < 1:
        raise ValueError("turns must be positive")
    output.mkdir(parents=True, exist_ok=False)
    frames = output / "screenshots"
    frames.mkdir()
    started = time.perf_counter()
    summary = {
        "status": "running",
        "turns": 0,
        "score_from_merges": 0,
        "max_tile": 0,
        "recognition_errors": 0,
        "transition_errors": 0,
        "capture_backend": "game-rendered PNG framebuffer (not desktop capture)",
    }
    log = (output / "turns.jsonl").open("w", encoding="utf-8")
    try:
        screenshot = screens.capture()
        screenshot.save(frames / "0000.png")
        before = perception.observe(screenshot)
        summary["max_tile"] = max(before.board)
        for turn in range(1, turns + 1):
            tick = time.perf_counter()
            action = policy.choose(before, screenshot)
            if action is None:
                summary["status"] = "game_over"
                break
            inputs.press(action)
            # 本ゲームはキー応答前に描画状態を確定する同期プロトコル。
            screenshot = screens.capture()
            frame = frames / f"{turn:04d}.png"
            screenshot.save(frame)
            after = perception.observe(screenshot)
            result = evaluator.evaluate(before, action, after)
            if not result.changed:
                raise RuntimeError("Policy selected a no-op move; stopping")
            summary["turns"] = turn
            summary["score_from_merges"] += result.score_delta
            summary["max_tile"] = result.max_tile
            record = {
                "turn": turn,
                "action": action,
                "before": before.board,
                "after": after.board,
                "confidence": after.confidence,
                "score_delta": result.score_delta,
                "score_total": summary["score_from_merges"],
                "terminal": result.terminal,
                "empty_cells": result.empty_cells,
                "frame": str(frame.relative_to(output)),
                "frame_sha256": hashlib.sha256(frame.read_bytes()).hexdigest(),
                "elapsed_ms": round((time.perf_counter() - tick) * 1000, 3),
            }
            log.write(json.dumps(record) + "\n")
            log.flush()
            before = after
            if turn % 25 == 0:
                print(
                    f"turn={turn} score={summary['score_from_merges']} max={result.max_tile}",
                    flush=True,
                )
            if result.terminal:
                summary["status"] = "game_over"
                break
        else:
            summary["status"] = "turn_limit"
    except Exception as exc:
        from .evaluation import TransitionError
        from .perception import RecognitionError

        summary["status"] = "error"
        summary["error"] = f"{type(exc).__name__}: {exc}"
        summary["recognition_errors"] += isinstance(exc, RecognitionError)
        summary["transition_errors"] += isinstance(exc, TransitionError)
        raise
    finally:
        log.close()
        summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
    return summary


def make_replay(output: Path) -> None:
    # 長い実行でも全フレームをメモリへ蓄積しない。最大201枚のGIF。
    paths = sorted((output / "screenshots").glob("*.png"))
    stride = max(1, (len(paths) + 199) // 200)
    selected = paths[::stride]
    if selected[-1] != paths[-1]:
        selected.append(paths[-1])
    images = []
    for path in selected:
        with Image.open(path) as image:
            images.append(
                image.resize((320, 400)).convert("P", palette=Image.Palette.ADAPTIVE)
            )
    images[0].save(
        output / "replay.gif",
        save_all=True,
        append_images=images[1:],
        duration=150 * stride,
        loop=0,
        optimize=False,
    )
    for image in images:
        image.close()
    # ffmpegは任意。無ければGIFとPNGが成果物になる。
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-framerate",
                "6",
                "-i",
                str(output / "screenshots" / "%04d.png"),
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output / "replay.mp4"),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        status = "created" if result.returncode == 0 else result.stderr[-2000:]
    except (OSError, subprocess.TimeoutExpired) as exc:
        status = str(exc)
    (output / "video_status.txt").write_text(status, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=150)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--depth", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-replay", action="store_true")
    args = parser.parse_args()
    if args.turns < 1:
        parser.error("--turns must be positive")
    output = args.output or Path("artifacts") / datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    with GameProcess(args.seed) as port:
        summary = run_session(
            port,
            port,
            PalettePerception(),
            ExpectimaxPolicy(args.depth),
            TransitionEvaluator(),
            output,
            args.turns,
        )
    summary.update(
        {"seed": args.seed, "search_depth": args.depth, "requested_turns": args.turns}
    )
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    if not args.no_replay:
        make_replay(output)
    print(json.dumps(summary, indent=2))
    print(f"Artifacts: {output.resolve()}")
    return 0 if summary["turns"] >= args.turns else 2


if __name__ == "__main__":
    sys.exit(main())
