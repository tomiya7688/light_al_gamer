"""ゲーム共通の観測・判断・実行・再観測・記録ループ。"""

import hashlib
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

from .models import (
    DesktopEvaluator,
    DesktopPerception,
    DesktopPort,
    GameProfile,
    VisualPolicy,
)
from .vision import VisualEvaluator, VisualPerception
from .windows import StopRequested


def run_desktop_session(
    port: DesktopPort,
    profile: GameProfile,
    policy: VisualPolicy,
    output: Path,
    steps: int = 100,
    max_seconds: float = 180,
    settle_seconds: float = 0.1,
    clock=time.monotonic,
    sleep=time.sleep,
    perception: DesktopPerception | None = None,
    evaluator: DesktopEvaluator | None = None,
) -> dict:
    if (
        type(steps) is not int
        or not 1 <= steps <= 10000
        or not 0 < max_seconds <= 3600
        or not 0 <= settle_seconds <= 2
    ):
        raise ValueError("Invalid session limits")
    output.mkdir(parents=True, exist_ok=False)
    frames = output / "screenshots"
    frames.mkdir()
    perception = perception or VisualPerception()
    evaluator = evaluator or VisualEvaluator()
    started = clock()
    summary = {
        "profile": profile.name,
        "status": "running",
        "steps": 0,
        "requested_steps": steps,
        "capture_backend": type(port).__name__,
        "goal_achievement": "not_verified",
        "policy": type(policy).__name__,
        "model": getattr(policy, "model", None),
    }
    previous = None
    try:
        (output / "profile.json").write_text(
            json.dumps(asdict(profile), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with (output / "events.jsonl").open("w", encoding="utf-8") as log:

            def record(event):
                event["elapsed_seconds"] = round(clock() - started, 3)
                log.write(json.dumps(event, ensure_ascii=False) + "\n")
                log.flush()

            port.check_ready()
            before = port.capture()
            before.save(frames / "0000.png")
            for step in range(1, steps + 1):
                if clock() - started >= max_seconds:
                    summary["status"] = "time_limit"
                    break
                port.check_ready()
                observation = perception.observe(before)
                if not observation.usable:
                    summary.update(
                        status="observation_blocked", reason="Blank/unusable frame"
                    )
                    break
                if (
                    getattr(
                        policy, "requires_crosshair", profile.perception == "minecraft"
                    )
                    and not observation.crosshair
                ):
                    summary.update(
                        status="observation_blocked",
                        reason="Minecraft crosshair not detected; load world, first-person view, HUD on",
                    )
                    break
                decision = policy.choose(observation, before, previous)
                # VLM推論中のF8・フォーカス変更・時間切れも実入力の前に検出する。
                port.check_ready()
                if clock() - started >= max_seconds:
                    summary["status"] = "time_limit"
                    break
                if decision.action is None:
                    summary.update(status="policy_stopped", reason=decision.reason)
                    break
                if decision.action not in profile.actions:
                    raise ValueError("Policy action is outside configured profile")
                action = profile.actions[decision.action]
                if decision.pointer is not None:
                    if not action.aim:
                        raise ValueError(
                            "Policy supplied a pointer for an unpointed action"
                        )
                    action = replace(action, pointer=decision.pointer)
                record(
                    {
                        "event": "action_start",
                        "step": step,
                        "action": decision.action,
                        "controls": asdict(action),
                        "reason": decision.reason,
                        "observation": asdict(observation),
                    }
                )
                port.perform(action)
                deadline = clock() + settle_seconds
                while clock() < deadline:
                    port.check_ready()
                    sleep(min(0.02, max(0, deadline - clock())))
                after = port.capture()
                path = frames / f"{step:04d}.png"
                after.save(path)
                previous = evaluator.evaluate(before, after)
                record(
                    {
                        "event": "action_result",
                        "step": step,
                        "feedback": asdict(previous),
                        "frame": path.relative_to(output).as_posix(),
                        "frame_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
                summary["steps"] = step
                before = after
                if step % 10 == 0:
                    print(
                        f"step={step} action={decision.action} visual_motion={previous.motion:.4f}",
                        flush=True,
                    )
            else:
                summary["status"] = "step_limit"
    except StopRequested as exc:
        summary.update(status="stopped", reason=str(exc))
    except KeyboardInterrupt:
        summary.update(status="stopped", reason="KeyboardInterrupt")
    except Exception as exc:
        summary.update(status="error", error=f"{type(exc).__name__}: {exc}")
        if getattr(exc, "__notes__", None):
            summary["notes"] = exc.__notes__
    finally:
        try:
            port.close()
        except Exception as exc:
            summary.update(status="error", cleanup_error=str(exc))
        summary["elapsed_seconds"] = round(clock() - started, 3)
        (output / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return summary
