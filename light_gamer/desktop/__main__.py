"""Windows上のMinecraft・カスタムゲームを画像から操作するCLI。"""

import argparse
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..runner import make_replay
from .models import load_profile
from .native import Win32Native
from .policies import MinecraftExplorePolicy, OllamaVisionPolicy
from .session import run_desktop_session
from .windows import WindowsGamePort, select_window


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile", default="minecraft", help="minecraft, generic, or JSON path"
    )
    parser.add_argument(
        "--window",
        default="Minecraft",
        help="Unique title substring; launcher excluded",
    )
    parser.add_argument("--hwnd", type=lambda value: int(value, 0))
    parser.add_argument("--capture", choices=("desktop", "window"), default="desktop")
    parser.add_argument(
        "--policy", choices=("minecraft-explore", "ollama"), default="minecraft-explore"
    )
    parser.add_argument(
        "--model", help="Already installed local image-capable Ollama model"
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--goal", default="Explore the terrain and gather wood when possible"
    )
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--start-delay", type=float, default=5)
    parser.add_argument("--settle", type=float, default=0.1)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-replay", action="store_true")
    parser.add_argument("--list-windows", action="store_true")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Read-only desktop/target diagnostics; no input",
    )
    args = parser.parse_args(argv)
    if not (
        1 <= args.steps <= 10000
        and math.isfinite(args.max_seconds)
        and 0 < args.max_seconds <= 3600
        and math.isfinite(args.start_delay)
        and 0 <= args.start_delay <= 30
        and math.isfinite(args.settle)
        and 0 <= args.settle <= 2
    ):
        parser.error("Invalid steps/time limits")
    output = args.output or Path("artifacts") / (
        "windows-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    native = None
    transferred = False
    try:
        native = Win32Native()
        windows = native.list_windows()
        if args.list_windows:
            print(
                json.dumps(
                    [asdict(window) for window in windows], indent=2, ensure_ascii=False
                )
            )
            return 0
        if args.probe:
            matching = [
                window
                for window in windows
                if args.window.casefold() in window.title.casefold()
            ]
            result = {
                "platform": sys.platform,
                "foreground_hwnd": native.foreground(),
                "visible_window_count": len(windows),
                "matching_windows": [asdict(window) for window in matching],
                "interactive_desktop": bool(native.foreground()),
                "dpi_context_ready": native.dpi_ready,
                "input_sent": False,
            }
            output.mkdir(parents=True, exist_ok=False)
            (output / "probe.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        profile_path = (
            Path(__file__).parent / "profiles" / (args.profile + ".json")
            if args.profile in ("minecraft", "generic")
            else Path(args.profile)
        )
        profile = load_profile(profile_path)
        if args.policy == "minecraft-explore":
            required = {
                "forward",
                "backward",
                "jump_forward",
                "turn_left",
                "turn_right",
                "mine",
            }
            if (
                profile.perception != "minecraft"
                or not required <= profile.actions.keys()
            ):
                parser.error(
                    "minecraft-explore requires a Minecraft profile with the built-in exploration actions"
                )
            policy = MinecraftExplorePolicy()
        else:
            if not args.model:
                parser.error(
                    "--policy ollama requires --model (local image-capable model)"
                )
            policy = OllamaVisionPolicy(profile, args.model, args.goal, args.ollama_url)
        window = select_window(windows, args.window, args.hwnd)
        print(
            f"Target: {window.title} (HWND={window.hwnd}). Focus the loaded game within {args.start_delay:g}s. F8 stops.",
            flush=True,
        )
        # 先に監視を開始し、開始待ちやVLM推論中もF8を記録する。
        port = WindowsGamePort(native, window, args.capture)
        transferred = True
        try:
            deadline = time.monotonic() + args.start_delay
            while time.monotonic() < deadline:
                if port.cancelled.is_set() or native.stop_pressed():
                    raise RuntimeError("F8 stop during start delay")
                time.sleep(0.02)
            summary = run_desktop_session(
                port, profile, policy, output, args.steps, args.max_seconds, args.settle
            )
        finally:
            # 出力先が既存など、session開始前に失敗した場合も終了する。
            port.close()
        if not args.no_replay and (output / "screenshots" / "0000.png").is_file():
            try:
                make_replay(output)
            except (OSError, ValueError, IndexError) as exc:
                (output / "replay_error.txt").write_text(str(exc), encoding="utf-8")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"Artifacts: {output.resolve()}")
        return 0 if summary["status"] == "step_limit" else 2
    except (OSError, ValueError, RuntimeError) as exc:
        if not output.exists():
            output.mkdir(parents=True)
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "status": "startup_blocked",
                        "error": str(exc),
                        "input_sent": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        print(f"Desktop session blocked: {exc}", file=sys.stderr)
        return 2
    finally:
        if native is not None and not transferred:
            native.close()


if __name__ == "__main__":
    raise SystemExit(main())
