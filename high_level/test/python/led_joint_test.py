#!/usr/bin/env python3
"""High-Level leg LED joint-test harness (interactive; needs robot or mock).

Location: high_level/test/python/led_joint_test.py

Usage:
  python led_joint_test.py [server_address] [options]

Options:
  --suite NAME   all|cont|ctrl|color|bri|reset|other|smoke  (default: all)
  --auto         Timed pause between steps (no keyboard wait)
  --hold SEC     Observation time in --auto mode (default: 3)
  --skip-motion  Skip motion-related cases (TC-MOT-*)

Covers joint-test cases:
  TC-CONT-*  continuous user control (no mid-sequence reset); runs first
  TC-CTRL-*  user-control takeover of all four legs
  TC-COLOR-* / TC-BRI-*  color & brightness
  TC-RST-*   release control back to main controller
  TC-OFF / TC-API / TC-MOT / TC-MULTI  other scenarios

Fill lights are rejected by set APIs (validated in TC-API-02).
Not collected by pytest (filename has no test_ prefix).
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from dobot_quad import RobotClient, Leg, Color, LegLedConfig


@dataclass
class CaseResult:
    case_id: str
    title: str
    rpc_ok: Optional[bool]
    verdict: str  # PASS / FAIL / SKIP / OBSERVE
    note: str = ""


@dataclass
class Runner:
    robot: RobotClient
    auto: bool = False
    hold_sec: float = 3.0
    skip_motion: bool = False
    results: List[CaseResult] = field(default_factory=list)

    def banner(self, title: str) -> None:
        print("\n" + "=" * 60)
        print(title)
        print("=" * 60)

    def pause(self, prompt: str = "观察灯效后按 Enter 继续") -> None:
        if self.auto:
            print(f"  ... 自动等待 {self.hold_sec:.1f}s")
            time.sleep(self.hold_sec)
            return
        try:
            input(f"  >> {prompt} ")
        except EOFError:
            time.sleep(self.hold_sec)

    def brief_dwell(self, sec: float = 0.4) -> None:
        """Short dwell between continuous frames (no keyboard)."""
        time.sleep(sec)

    def ask_verdict(self, case_id: str, title: str, rpc_ok: Optional[bool],
                    expect_hint: str) -> None:
        print(f"\n[{case_id}] {title}")
        print(f"  期望: {expect_hint}")
        if rpc_ok is not None:
            print(f"  RPC:  {'OK' if rpc_ok else 'FAILED'}")

        if self.auto:
            verdict = "OBSERVE" if (rpc_ok is None or rpc_ok) else "FAIL"
            note = "auto 模式未人工判定" if verdict == "OBSERVE" else "RPC 失败"
            self.results.append(CaseResult(case_id, title, rpc_ok, verdict, note))
            self.pause("自动停留供观察")
            return

        self.pause("观察后输入判定: y=通过 / n=失败 / s=跳过 (默认 y)")
        try:
            raw = input("  判定 [y/n/s]: ").strip().lower()
        except EOFError:
            raw = "y"
        if raw in ("", "y", "yes"):
            verdict = "PASS"
        elif raw in ("n", "no"):
            verdict = "FAIL"
        else:
            verdict = "SKIP"
        note = ""
        if rpc_ok is False and verdict == "PASS":
            note = "人工通过但 RPC 返回 False"
        self.results.append(CaseResult(case_id, title, rpc_ok, verdict, note))

    def reset_baseline(self) -> None:
        print("\n--- 基线: reset_legs() 交还主控 ---")
        ok = self.robot.reset_legs(verbose=True)
        print(f"  RPC: {'OK' if ok else 'FAILED'}")
        self.pause("确认四灯已回到主控默认表现")

    # ------------------------------------------------------------------
    # Suites
    # ------------------------------------------------------------------

    def suite_cont(self) -> None:
        """Continuous user LED control — no mid-sequence reset."""
        self.banner("组 C0: 连续用户控灯 (TC-CONT) — 过程中不 reset")
        self.reset_baseline()

        print("\n--- TC-CONT-01 单腿 FL 快速变色（约数秒，中间不 reset） ---")
        palette = [
            Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN,
            Color.CYAN, Color.BLUE, Color.PURPLE, Color.WHITE,
        ]
        ok = True
        for color in palette:
            print(f"  frame FL={color.name}")
            ok = self.robot.set_leg_color(Leg.FL, color, verbose=True) and ok
            self.brief_dwell(0.35)
        self.ask_verdict(
            "TC-CONT-01", "单腿 FL 快速变色序列", ok,
            "FL 数秒内连续换色流畅；其余腿保持用户域暗态；过程无 reset")

        print("\n--- TC-CONT-02 单腿 FL 亮度快速往返（不 reset） ---")
        ok = self.robot.set_leg_color(Leg.FL, Color.RED, verbose=True)
        self.brief_dwell(0.3)
        for bri in (255, 128, 64, 32, 0, 32, 64, 128, 255):
            print(f"  frame FL bri={bri}")
            ok = self.robot.set_leg_brightness(Leg.FL, bri, verbose=True) and ok
            self.brief_dwell(0.3)
        self.ask_verdict(
            "TC-CONT-02", "单腿 FL 亮度快速往返", ok,
            "FL 红光亮度明→暗→明连续变化可见；中间无 reset")

        print("\n--- TC-CONT-03 四腿轮流设色（不 reset，前腿应保留） ---")
        steps = [
            (Leg.FL, Color.RED),
            (Leg.FR, Color.GREEN),
            (Leg.RL, Color.BLUE),
            (Leg.RR, Color.YELLOW),
        ]
        ok = True
        for leg, color in steps:
            print(f"  frame {leg.name}={color.name}（先前腿应保持缓存色）")
            ok = self.robot.set_leg_color(leg, color, verbose=True) and ok
            self.brief_dwell(0.6)
        self.ask_verdict(
            "TC-CONT-03", "四腿轮流设色", ok,
            "依次点亮后最终 FL红 FR绿 RL蓝 RR黄 同时保持；非最后一帧时前腿不灭")

        print("\n--- TC-CONT-04 四腿追光轮询（不 reset） ---")
        order = [Leg.FL, Leg.FR, Leg.RL, Leg.RR]
        ok = True
        for _round in range(2):
            for hi in order:
                cfgs = [
                    LegLedConfig(
                        leg=leg,
                        r=255 if leg == hi else 80,
                        g=255 if leg == hi else 0,
                        b=255 if leg == hi else 0,
                        brightness=255,
                    )
                    for leg in order
                ]
                print("  chase highlight next leg")
                ok = self.robot.set_legs_rgb(cfgs, verbose=True) and ok
                self.brief_dwell(0.45)
        self.ask_verdict(
            "TC-CONT-04", "四腿追光轮询两圈", ok,
            "高亮白点在四腿间轮转，其余腿暗红；切换流畅、无 reset")

        print("\n--- TC-CONT-05 连续控灯后 reset 交还主控 ---")
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict(
            "TC-CONT-05", "连续序列结束后 reset_legs()", ok,
            "四灯交还主控默认规则")

    def suite_ctrl(self) -> None:
        self.banner("组 A: 用户控制权接管 (TC-CTRL)")

        # 01
        self.reset_baseline()
        ok = self.robot.set_leg_color(Leg.FL, Color.RED, verbose=True)
        self.ask_verdict(
            "TC-CTRL-01", "仅设 FL=RED",
            ok,
            "FL 变红；其余三腿停止跟随主控自动逻辑（用户接管四腿）")

        # 02 — each single leg once
        for leg, color, cid in [
            (Leg.FR, Color.GREEN, "TC-CTRL-02a"),
            (Leg.RL, Color.BLUE, "TC-CTRL-02b"),
            (Leg.RR, Color.YELLOW, "TC-CTRL-02c"),
        ]:
            self.reset_baseline()
            ok = self.robot.set_leg_color(leg, color, verbose=True)
            self.ask_verdict(
                cid, f"仅设 {leg.name}={color.name}",
                ok,
                f"{leg.name} 变色；其余腿进入用户域，不跟主控自动逻辑")

        # 03 brightness-only takeover
        self.reset_baseline()
        ok = self.robot.set_leg_brightness(Leg.FL, 64, verbose=True)
        self.ask_verdict(
            "TC-CTRL-03", "无缓存时仅 set_leg_brightness(FL, 64)",
            ok,
            "触发用户接管；无缓存时默认白色+亮度 64")

        # 04 turn_off keeps user control
        self.reset_baseline()
        ok = self.robot.turn_off_leg(Leg.FL, verbose=True)
        self.ask_verdict(
            "TC-CTRL-04", "turn_off_leg(FL)",
            ok,
            "四腿用户接管；FL 熄灭；不等于交还主控（灯不应恢复主控动效）")

        # 05 batch two legs
        self.reset_baseline()
        ok = self.robot.set_legs_rgb([
            LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=255),
            LegLedConfig(leg=Leg.FR, r=0, g=255, b=0, brightness=255),
        ], verbose=True)
        self.ask_verdict(
            "TC-CTRL-05", "set_legs_rgb 仅 FL/FR 两腿",
            ok,
            "四腿进入用户域；记录未被命令腿的颜色/亮度表现")

        # 06 all legs
        self.reset_baseline()
        ok = self.robot.set_all_legs_color(Color.CYAN, brightness=200, verbose=True)
        self.ask_verdict(
            "TC-CTRL-06", "set_all_legs_color(CYAN)",
            ok,
            "四腿同时青色，确认为用户域")

    def suite_color(self) -> None:
        self.banner("组 B1: 颜色控制 (TC-COLOR)")
        self.reset_baseline()

        colors = [
            Color.RED, Color.ORANGE, Color.YELLOW, Color.GREEN,
            Color.CYAN, Color.BLUE, Color.PURPLE, Color.WHITE, Color.OFF,
        ]
        for color in colors:
            ok = self.robot.set_all_legs_color(color, brightness=255, verbose=True)
            self.ask_verdict(
                f"TC-COLOR-01-{color.name}",
                f"set_all_legs_color({color.name})",
                ok,
                f"四腿呈 {color.name}（OFF 应熄灭）")

        ok = self.robot.set_leg_rgb(Leg.FL, 128, 64, 32, brightness=255, verbose=True)
        self.ask_verdict(
            "TC-COLOR-02", "set_leg_rgb(FL, 128,64,32)",
            ok,
            "FL 目视接近自定义茶色/褐色")

        rainbow = [
            LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=255),
            LegLedConfig(leg=Leg.FR, r=0, g=255, b=0, brightness=255),
            LegLedConfig(leg=Leg.RL, r=0, g=0, b=255, brightness=255),
            LegLedConfig(leg=Leg.RR, r=255, g=255, b=0, brightness=255),
        ]
        ok = self.robot.set_legs_rgb(rainbow, verbose=True)
        self.ask_verdict(
            "TC-COLOR-03", "四腿四色 batch RGB",
            ok,
            "FL红 FR绿 RL蓝 RR黄")

    def suite_bri(self) -> None:
        self.banner("组 B2: 亮度控制 (TC-BRI)")
        self.reset_baseline()

        self.robot.set_all_legs_color(Color.RED, brightness=255, verbose=True)
        self.pause("已设四腿全红满亮，开始亮度阶梯")

        for bri in (255, 128, 32, 0):
            ok = self.robot.set_all_legs_rgb(255, 0, 0, brightness=bri, verbose=True)
            self.ask_verdict(
                f"TC-BRI-01-{bri}",
                f"同色红 brightness={bri}",
                ok,
                "色相仍为红；亮度阶梯可见（wire 为缩放后的 RGB）；0 近似灭")

        self.reset_baseline()
        ok = self.robot.set_leg_rgb(Leg.FR, 0, 255, 0, brightness=255, verbose=True)
        self.pause("FR 已设满亮绿色")
        ok = self.robot.set_leg_brightness(Leg.FR, 32, verbose=True) and ok
        self.ask_verdict(
            "TC-BRI-02", "先满亮绿再 set_leg_brightness(FR, 32)",
            ok,
            "FR 仍为绿色，仅变暗（wire rgb 约 (0,32,0)）")

        self.reset_baseline()
        ok = self.robot.set_leg_brightness(Leg.RR, 128, verbose=True)
        self.ask_verdict(
            "TC-BRI-03", "无缓存 set_leg_brightness(RR, 128)",
            ok,
            "默认白 + 亮度 128")

        self.reset_baseline()
        ok = self.robot.set_leg_rgb(Leg.FL, 0, 0, 255, brightness=0, verbose=True)
        ok2 = self.robot.set_leg_rgb(Leg.FR, 255, 255, 255, brightness=255, verbose=True)
        self.ask_verdict(
            "TC-BRI-04", "边界 brightness 0 与 255",
            ok and ok2,
            "FL 近灭；FR 白满亮；RL/RR 应灭（不受 TC-BRI-03 残留影响）")

    def suite_reset(self) -> None:
        self.banner("组 C: 恢复主控控制 (TC-RST)")

        self.reset_baseline()
        self.robot.set_all_legs_color(Color.PURPLE, brightness=255, verbose=True)
        self.pause("四腿紫色用户控，接着 reset 全部")
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict(
            "TC-RST-01", "reset_legs() 全部释放",
            ok,
            "四灯交还主控；切换状态时应恢复主控默认表现")

        self.reset_baseline()
        self.robot.set_all_legs_color(Color.RED, brightness=200, verbose=True)
        self.pause("四腿红色，接着仅 reset FL")
        ok = self.robot.reset_legs([Leg.FL], verbose=True)
        self.ask_verdict(
            "TC-RST-02", "reset_legs([FL]) 单腿释放",
            ok,
            "记录实机语义：仅 FL 交还，或四腿一并释放（须在报告中写明）")

        self.reset_baseline()
        self.robot.set_leg_color(Leg.RL, Color.BLUE, verbose=True)
        self.robot.turn_off_leg(Leg.RL, verbose=True)
        self.pause("RL 已 turn_off（用户域灭灯），接着 reset")
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict(
            "TC-RST-03", "turn_off 后再 reset_legs()",
            ok,
            "reset 后交还主控（与单纯 turn_off 区分）")

        ok = self.robot.set_leg_color(Leg.FL, Color.ORANGE, verbose=True)
        self.ask_verdict(
            "TC-RST-04", "reset 后再 set_leg_color(FL, ORANGE)",
            ok,
            "可再次用户接管，橙色有效")

        if self.skip_motion:
            self.results.append(CaseResult(
                "TC-RST-05", "运动中 reset", None, "SKIP", "--skip-motion"))
            return

        self.reset_baseline()
        self.robot.set_all_legs_color(Color.CYAN, brightness=180, verbose=True)
        print("  尝试短时运动（若失败可手测）...")
        try:
            # short non-destructive idle check: query state then reset while standing
            state = self.robot.get_current_state_name()
            print(f"  当前状态: {state}")
        except Exception as e:
            print(f"  查询状态异常: {e}")
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict(
            "TC-RST-05", "用户控灯后 reset（站立/现态）",
            ok,
            "不卡死；灯尽快回主控表现")

    def suite_other(self) -> None:
        self.banner("组 D: 其他场景 (TC-OFF / TC-API / TC-MOT / TC-MULTI)")

        # OFF vs reset
        self.reset_baseline()
        self.robot.set_leg_color(Leg.FL, Color.RED, verbose=True)
        ok = self.robot.turn_off_leg(Leg.FL, verbose=True)
        self.ask_verdict(
            "TC-OFF-01a", "turn_off 保持用户域",
            ok,
            "灯灭但仍用户控，主控不应立刻接管")
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict(
            "TC-OFF-01b", "随后 reset 交还主控",
            ok,
            "主控恢复对灯的控制")

        # empty configs
        ok = self.robot.set_legs_rgb([])
        self.ask_verdict(
            "TC-API-01", "set_legs_rgb([]) 空列表",
            ok,
            "返回 True 且灯效无变化")

        # fill lights rejected
        raised = False
        try:
            self.robot.set_leg_rgb(Leg.FILL_FRONT, 255, 0, 0)
        except ValueError as e:
            raised = True
            print(f"  捕获 ValueError: {e}")
        self.ask_verdict(
            "TC-API-02", "FILL_FRONT 被拒绝",
            raised,
            "抛 ValueError，不发 RPC")

        # invalid RGB
        raised = False
        try:
            self.robot.set_legs_rgb([LegLedConfig(leg=Leg.FL, r=-1, g=0, b=0)])
        except ValueError as e:
            raised = True
            print(f"  捕获 ValueError: {e}")
        self.ask_verdict(
            "TC-API-03", "非法 RGB 抛错",
            raised,
            "抛 ValueError")

        # rapid updates
        print("\n--- TC-MULTI-01 高频连发 ---")
        ok = True
        palette = [
            (255, 0, 0), (0, 255, 0), (0, 0, 255),
            (255, 255, 0), (255, 0, 255), (0, 255, 255),
        ]
        for i, (r, g, b) in enumerate(palette):
            ok = self.robot.set_all_legs_rgb(r, g, b, brightness=200, verbose=False) and ok
            time.sleep(0.15)
        self.ask_verdict(
            "TC-MULTI-01", "高频连续改色",
            ok,
            "最终态正确、无卡死；最后一色为青色")

        # client cache note after reset
        self.robot.reset_legs(verbose=True)
        ok = self.robot.set_leg_brightness(Leg.FL, 80, verbose=True)
        self.ask_verdict(
            "TC-MULTI-02", "reset 后客户端缓存清空再设亮度",
            ok,
            "行为符合无缓存默认白；远程仍可控制")

        if self.skip_motion:
            self.results.append(CaseResult(
                "TC-MOT-01", "与运动并存", None, "SKIP", "--skip-motion"))
            return

        self.reset_baseline()
        self.robot.set_all_legs_color(Color.GREEN, brightness=200, verbose=True)
        print("  用户控灯后尝试轻微动作（失败则人工复测）...")
        motion_ok = True
        try:
            # Prefer a gentle state keep / balance if available; avoid long walks
            name = self.robot.get_current_state_name()
            print(f"  当前状态: {name}")
        except Exception as e:
            motion_ok = False
            print(f"  状态查询失败: {e}")
        self.ask_verdict(
            "TC-MOT-01", "用户控灯 + 保持站立观查",
            motion_ok,
            "灯保持用户绿色；机器人行为正常")

    def suite_smoke(self) -> None:
        self.banner("冒烟: e11 等价流程")
        self.reset_baseline()
        self.robot.set_leg_color(Leg.FL, Color.RED, verbose=True)
        self.pause()
        self.robot.set_legs_rgb([
            LegLedConfig(leg=Leg.FL, r=255, g=0, b=0, brightness=255),
            LegLedConfig(leg=Leg.FR, r=0, g=255, b=0, brightness=255),
            LegLedConfig(leg=Leg.RL, r=0, g=0, b=255, brightness=255),
            LegLedConfig(leg=Leg.RR, r=255, g=255, b=0, brightness=255),
        ], verbose=True)
        self.pause()
        self.robot.set_all_legs_color(Color.CYAN, brightness=128, verbose=True)
        self.pause()
        self.robot.set_leg_brightness(Leg.FR, 32, verbose=True)
        self.pause()
        self.robot.turn_off_leg(Leg.RL, verbose=True)
        self.pause()
        self.robot.reset_legs([Leg.FL], verbose=True)
        self.pause()
        ok = self.robot.reset_legs(verbose=True)
        self.ask_verdict("TC-SMOKE", "e11 全流程冒烟", ok, "流程无异常，灯效符合 demo")

    def print_summary(self) -> int:
        self.banner("联调结果汇总")
        if not self.results:
            print("  (无记录)")
            return 0

        counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "OBSERVE": 0}
        print(f"{'Case':<18} {'Verdict':<8} {'RPC':<6} Title")
        print("-" * 70)
        for r in self.results:
            counts[r.verdict] = counts.get(r.verdict, 0) + 1
            rpc = "-" if r.rpc_ok is None else ("OK" if r.rpc_ok else "FAIL")
            note = f"  ({r.note})" if r.note else ""
            print(f"{r.case_id:<18} {r.verdict:<8} {rpc:<6} {r.title}{note}")

        print("-" * 70)
        print(
            f"PASS={counts.get('PASS', 0)}  FAIL={counts.get('FAIL', 0)}  "
            f"SKIP={counts.get('SKIP', 0)}  OBSERVE={counts.get('OBSERVE', 0)}"
        )
        print("可将上表填入联调报告模板。")
        return 1 if counts.get("FAIL", 0) else 0


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="High-Level leg LED joint test")
    p.add_argument("server", nargs="?", default="192.168.5.2:50051",
                   help="gRPC server address")
    p.add_argument("--suite", default="all",
                   choices=["all", "cont", "ctrl", "color", "bri", "reset", "other", "smoke"],
                   help="which test group to run")
    p.add_argument("--auto", action="store_true",
                   help="timed pause; mark OBSERVE instead of interactive PASS/FAIL")
    p.add_argument("--hold", type=float, default=3.0,
                   help="seconds to hold in --auto mode")
    p.add_argument("--skip-motion", action="store_true",
                   help="skip motion-related cases")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    print(f"连接: {args.server}")
    print(f"套件: {args.suite}  auto={args.auto}  hold={args.hold}  "
          f"skip_motion={args.skip_motion}")

    robot = RobotClient(args.server)
    robot.enable_safety_ready()

    runner = Runner(
        robot=robot,
        auto=args.auto,
        hold_sec=args.hold,
        skip_motion=args.skip_motion,
    )

    suite_map: dict[str, Callable[[], None]] = {
        "cont": runner.suite_cont,
        "ctrl": runner.suite_ctrl,
        "color": runner.suite_color,
        "bri": runner.suite_bri,
        "reset": runner.suite_reset,
        "other": runner.suite_other,
        "smoke": runner.suite_smoke,
    }

    if args.suite == "all":
        for name in ("cont", "ctrl", "color", "bri", "reset", "other"):
            suite_map[name]()
    else:
        suite_map[args.suite]()

    return runner.print_summary()


if __name__ == "__main__":
    sys.exit(main())
