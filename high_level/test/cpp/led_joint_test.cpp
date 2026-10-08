// High-Level leg LED joint-test harness (interactive; needs robot or mock).
// Location: high_level/test/cpp/led_joint_test.cpp
//
// Usage (from test/cpp/build):
//   ./led_joint_test [server_address] [options]
//
// Options:
//   --suite NAME   all|cont|ctrl|color|bri|reset|other|smoke  (default: all)
//   --auto         Timed pause between steps (no keyboard wait)
//   --hold SEC     Observation time in --auto mode (default: 3)
//   --skip-motion  Skip motion-related cases (TC-MOT-*)
//
// Suite "cont" (runs first in "all"): continuous user LED control without
// mid-sequence reset — single-leg rapid changes, four-leg round-robin.
//
// Mirrors high_level/test/python/led_joint_test.py

#include "robot_client.h"

#include <cctype>
#include <chrono>
#include <iostream>
#include <string>
#include <thread>
#include <vector>

namespace {

struct CaseResult {
    std::string case_id;
    std::string title;
    int rpc_ok;  // -1 unknown, 0 fail, 1 ok
    std::string verdict;
    std::string note;
};

struct Options {
    std::string server = "192.168.5.2:50051";
    std::string suite = "all";
    bool auto_mode = false;
    double hold_sec = 3.0;
    bool skip_motion = false;
};

struct Runner {
    robot::Client& client;
    Options opt;
    std::vector<CaseResult> results;

    void banner(const std::string& title)
    {
        std::cout << "\n" << std::string(60, '=') << "\n" << title << "\n"
                  << std::string(60, '=') << std::endl;
    }

    void pause(const std::string& prompt = "观察灯效后按 Enter 继续")
    {
        if (opt.auto_mode) {
            std::cout << "  ... 自动等待 " << opt.hold_sec << "s" << std::endl;
            std::this_thread::sleep_for(
                std::chrono::duration<double>(opt.hold_sec));
            return;
        }
        std::cout << "  >> " << prompt << " " << std::flush;
        std::string line;
        std::getline(std::cin, line);
    }

    /// Short dwell between continuous frames (no keyboard).
    void brief_dwell(double sec = 0.4)
    {
        std::this_thread::sleep_for(std::chrono::duration<double>(sec));
    }

    void ask_verdict(const std::string& case_id, const std::string& title,
                     int rpc_ok, const std::string& expect_hint)
    {
        std::cout << "\n[" << case_id << "] " << title << "\n";
        std::cout << "  期望: " << expect_hint << "\n";
        if (rpc_ok >= 0)
            std::cout << "  RPC:  " << (rpc_ok ? "OK" : "FAILED") << "\n";

        CaseResult r;
        r.case_id = case_id;
        r.title = title;
        r.rpc_ok = rpc_ok;

        if (opt.auto_mode) {
            r.verdict = (rpc_ok == 0) ? "FAIL" : "OBSERVE";
            r.note = (r.verdict == "OBSERVE") ? "auto 模式未人工判定" : "RPC 失败";
            results.push_back(r);
            pause("自动停留供观察");
            return;
        }

        pause("观察后输入判定: y=通过 / n=失败 / s=跳过 (默认 y)");
        std::cout << "  判定 [y/n/s]: " << std::flush;
        std::string raw;
        if (!std::getline(std::cin, raw))
            raw = "y";
        for (auto& c : raw)
            c = static_cast<char>(::tolower(c));
        if (raw.empty() || raw == "y" || raw == "yes")
            r.verdict = "PASS";
        else if (raw == "n" || raw == "no")
            r.verdict = "FAIL";
        else
            r.verdict = "SKIP";
        if (rpc_ok == 0 && r.verdict == "PASS")
            r.note = "人工通过但 RPC 返回 false";
        results.push_back(r);
    }

    void reset_baseline()
    {
        std::cout << "\n--- 基线: reset_legs() 交还主控 ---" << std::endl;
        bool ok = client.reset_legs({}, true);
        std::cout << "  RPC: " << (ok ? "OK" : "FAILED") << std::endl;
        pause("确认四灯已回到主控默认表现");
    }

    // ------------------------------------------------------------------
    // Continuous user control (no mid-sequence reset) — run first
    // ------------------------------------------------------------------

    void suite_cont()
    {
        banner("组 C0: 连续用户控灯 (TC-CONT) — 过程中不 reset");

        reset_baseline();

        // --- 单腿数秒内快速变色 ---
        std::cout << "\n--- TC-CONT-01 单腿 FL 快速变色（约数秒，中间不 reset） ---"
                  << std::endl;
        {
            const robot::Color palette[] = {
                robot::Color::RED,    robot::Color::ORANGE, robot::Color::YELLOW,
                robot::Color::GREEN,  robot::Color::CYAN,   robot::Color::BLUE,
                robot::Color::PURPLE, robot::Color::WHITE,
            };
            const char* names[] = {
                "RED", "ORANGE", "YELLOW", "GREEN", "CYAN", "BLUE", "PURPLE", "WHITE",
            };
            bool ok = true;
            for (size_t i = 0; i < sizeof(palette) / sizeof(palette[0]); ++i) {
                std::cout << "  frame FL=" << names[i] << std::endl;
                ok = client.set_leg_color(robot::Leg::FL, palette[i], true) && ok;
                brief_dwell(0.35);
            }
            ask_verdict("TC-CONT-01", "单腿 FL 快速变色序列", ok ? 1 : 0,
                        "FL 数秒内连续换色流畅；其余腿保持用户域暗态；过程无 reset");
        }

        // --- 单腿亮度快速往返（承接上一步，仍不 reset）---
        std::cout << "\n--- TC-CONT-02 单腿 FL 亮度快速往返（不 reset） ---" << std::endl;
        {
            bool ok = client.set_leg_color(robot::Leg::FL, robot::Color::RED, true);
            brief_dwell(0.3);
            for (int bri : {255, 128, 64, 32, 0, 32, 64, 128, 255}) {
                std::cout << "  frame FL bri=" << bri << std::endl;
                ok = client.set_leg_brightness(robot::Leg::FL, static_cast<uint8_t>(bri), true)
                     && ok;
                brief_dwell(0.3);
            }
            ask_verdict("TC-CONT-02", "单腿 FL 亮度快速往返", ok ? 1 : 0,
                        "FL 红光亮度明→暗→明连续变化可见；中间无 reset");
        }

        // --- 四腿轮流点亮（先前腿应保持缓存色）---
        std::cout << "\n--- TC-CONT-03 四腿轮流设色（不 reset，前腿应保留） ---"
                  << std::endl;
        {
            struct Step {
                robot::Leg leg;
                robot::Color color;
                const char* name;
            };
            const Step steps[] = {
                {robot::Leg::FL, robot::Color::RED, "FL=RED"},
                {robot::Leg::FR, robot::Color::GREEN, "FR=GREEN"},
                {robot::Leg::RL, robot::Color::BLUE, "RL=BLUE"},
                {robot::Leg::RR, robot::Color::YELLOW, "RR=YELLOW"},
            };
            bool ok = true;
            for (const auto& s : steps) {
                std::cout << "  frame " << s.name << "（先前腿应保持缓存色）" << std::endl;
                ok = client.set_leg_color(s.leg, s.color, true) && ok;
                brief_dwell(0.6);
            }
            ask_verdict("TC-CONT-03", "四腿轮流设色", ok ? 1 : 0,
                        "依次点亮后最终 FL红 FR绿 RL蓝 RR黄 同时保持；非最后一帧时前腿不灭");
        }

        // --- 追光/轮询高亮：一腿亮白，其余暗红 ---
        std::cout << "\n--- TC-CONT-04 四腿追光轮询（不 reset） ---" << std::endl;
        {
            const robot::Leg order[] = {
                robot::Leg::FL, robot::Leg::FR, robot::Leg::RL, robot::Leg::RR,
            };
            bool ok = true;
            for (int round = 0; round < 2; ++round) {
                for (robot::Leg hi : order) {
                    std::vector<robot::LegLedConfig> cfgs;
                    for (robot::Leg leg : order) {
                        if (leg == hi)
                            cfgs.push_back({leg, 255, 255, 255, 255});
                        else
                            cfgs.push_back({leg, 80, 0, 0, 255});
                    }
                    std::cout << "  chase highlight next leg" << std::endl;
                    ok = client.set_legs_rgb(cfgs, -1, true) && ok;
                    brief_dwell(0.45);
                }
            }
            ask_verdict("TC-CONT-04", "四腿追光轮询两圈", ok ? 1 : 0,
                        "高亮白点在四腿间轮转，其余腿暗红；切换流畅、无 reset");
        }

        // --- 收尾交还主控（本组唯一一次 reset，便于后续套件）---
        std::cout << "\n--- TC-CONT-05 连续控灯后 reset 交还主控 ---" << std::endl;
        {
            bool ok = client.reset_legs({}, true);
            ask_verdict("TC-CONT-05", "连续序列结束后 reset_legs()", ok ? 1 : 0,
                        "四灯交还主控默认规则");
        }
    }

    void suite_ctrl()
    {
        banner("组 A: 用户控制权接管 (TC-CTRL)");

        reset_baseline();
        bool ok = client.set_leg_color(robot::Leg::FL, robot::Color::RED, true);
        ask_verdict("TC-CTRL-01", "仅设 FL=RED", ok ? 1 : 0,
                    "FL 变红；其余三腿停止跟随主控自动逻辑（用户接管四腿）");

        struct Item {
            robot::Leg leg;
            robot::Color color;
            const char* cid;
            const char* leg_name;
            const char* color_name;
        };
        const Item items[] = {
            {robot::Leg::FR, robot::Color::GREEN, "TC-CTRL-02a", "FR", "GREEN"},
            {robot::Leg::RL, robot::Color::BLUE, "TC-CTRL-02b", "RL", "BLUE"},
            {robot::Leg::RR, robot::Color::YELLOW, "TC-CTRL-02c", "RR", "YELLOW"},
        };
        for (const auto& it : items) {
            reset_baseline();
            ok = client.set_leg_color(it.leg, it.color, true);
            std::string title = std::string("仅设 ") + it.leg_name + "=" + it.color_name;
            ask_verdict(it.cid, title, ok ? 1 : 0,
                        std::string(it.leg_name) + " 变色；其余腿进入用户域，不跟主控自动逻辑");
        }

        reset_baseline();
        ok = client.set_leg_brightness(robot::Leg::FL, 64, true);
        ask_verdict("TC-CTRL-03", "无缓存时仅 set_leg_brightness(FL, 64)", ok ? 1 : 0,
                    "触发用户接管；无缓存时默认白色+亮度 64");

        reset_baseline();
        ok = client.turn_off_leg(robot::Leg::FL, true);
        ask_verdict("TC-CTRL-04", "turn_off_leg(FL)", ok ? 1 : 0,
                    "四腿用户接管；FL 熄灭；不等于交还主控");

        reset_baseline();
        ok = client.set_legs_rgb({{robot::Leg::FL, 255, 0, 0, 255},
                                  {robot::Leg::FR, 0, 255, 0, 255}},
                                 -1, true);
        ask_verdict("TC-CTRL-05", "set_legs_rgb 仅 FL/FR 两腿", ok ? 1 : 0,
                    "四腿进入用户域；记录未被命令腿的颜色/亮度表现");

        reset_baseline();
        ok = client.set_all_legs_color(robot::Color::CYAN, 200, true);
        ask_verdict("TC-CTRL-06", "set_all_legs_color(CYAN)", ok ? 1 : 0,
                    "四腿同时青色，确认为用户域");
    }

    void suite_color()
    {
        banner("组 B1: 颜色控制 (TC-COLOR)");
        reset_baseline();

        struct NamedColor {
            robot::Color color;
            const char* name;
        };
        const NamedColor colors[] = {
            {robot::Color::RED, "RED"},       {robot::Color::ORANGE, "ORANGE"},
            {robot::Color::YELLOW, "YELLOW"}, {robot::Color::GREEN, "GREEN"},
            {robot::Color::CYAN, "CYAN"},     {robot::Color::BLUE, "BLUE"},
            {robot::Color::PURPLE, "PURPLE"}, {robot::Color::WHITE, "WHITE"},
            {robot::Color::OFF, "OFF"},
        };
        for (const auto& c : colors) {
            bool ok = client.set_all_legs_color(c.color, 255, true);
            ask_verdict(std::string("TC-COLOR-01-") + c.name,
                        std::string("set_all_legs_color(") + c.name + ")",
                        ok ? 1 : 0,
                        std::string("四腿呈 ") + c.name + "（OFF 应熄灭）");
        }

        bool ok = client.set_leg_rgb(robot::Leg::FL, 128, 64, 32, 255, true);
        ask_verdict("TC-COLOR-02", "set_leg_rgb(FL, 128,64,32)", ok ? 1 : 0,
                    "FL 目视接近自定义茶色/褐色");

        ok = client.set_legs_rgb({{robot::Leg::FL, 255, 0, 0, 255},
                                  {robot::Leg::FR, 0, 255, 0, 255},
                                  {robot::Leg::RL, 0, 0, 255, 255},
                                  {robot::Leg::RR, 255, 255, 0, 255}},
                                 -1, true);
        ask_verdict("TC-COLOR-03", "四腿四色 batch RGB", ok ? 1 : 0,
                    "FL红 FR绿 RL蓝 RR黄");
    }

    void suite_bri()
    {
        banner("组 B2: 亮度控制 (TC-BRI)");
        reset_baseline();

        client.set_all_legs_color(robot::Color::RED, 255, true);
        pause("已设四腿全红满亮，开始亮度阶梯");

        for (int bri : {255, 128, 32, 0}) {
            bool ok = client.set_all_legs_rgb(255, 0, 0, static_cast<uint8_t>(bri), true);
            ask_verdict("TC-BRI-01-" + std::to_string(bri),
                        "同色红 brightness=" + std::to_string(bri),
                        ok ? 1 : 0,
                        "色相仍为红；亮度阶梯可见（wire 为缩放后的 RGB）；0 近似灭");
        }

        reset_baseline();
        bool ok = client.set_leg_rgb(robot::Leg::FR, 0, 255, 0, 255, true);
        pause("FR 已设满亮绿色");
        ok = client.set_leg_brightness(robot::Leg::FR, 32, true) && ok;
        ask_verdict("TC-BRI-02", "先满亮绿再 set_leg_brightness(FR, 32)", ok ? 1 : 0,
                    "FR 仍为绿色，仅变暗（wire rgb 约 (0,32,0)）");

        reset_baseline();
        ok = client.set_leg_brightness(robot::Leg::RR, 128, true);
        ask_verdict("TC-BRI-03", "无缓存 set_leg_brightness(RR, 128)", ok ? 1 : 0,
                    "默认白 + 亮度 128");

        reset_baseline();
        ok = client.set_leg_rgb(robot::Leg::FL, 0, 0, 255, 0, true);
        bool ok2 = client.set_leg_rgb(robot::Leg::FR, 255, 255, 255, 255, true);
        ask_verdict("TC-BRI-04", "边界 brightness 0 与 255", (ok && ok2) ? 1 : 0,
                    "FL 近灭；FR 白满亮；RL/RR 应灭（不受 TC-BRI-03 残留影响）");
    }

    void suite_reset()
    {
        banner("组 C: 恢复主控控制 (TC-RST)");

        reset_baseline();
        client.set_all_legs_color(robot::Color::PURPLE, 255, true);
        pause("四腿紫色用户控，接着 reset 全部");
        bool ok = client.reset_legs({}, true);
        ask_verdict("TC-RST-01", "reset_legs() 全部释放", ok ? 1 : 0,
                    "四灯交还主控；切换状态时应恢复主控默认表现");

        reset_baseline();
        client.set_all_legs_color(robot::Color::RED, 200, true);
        pause("四腿红色，接着仅 reset FL");
        ok = client.reset_legs({robot::Leg::FL}, true);
        ask_verdict("TC-RST-02", "reset_legs([FL]) 单腿释放", ok ? 1 : 0,
                    "记录实机语义：仅 FL 交还，或四腿一并释放");

        reset_baseline();
        client.set_leg_color(robot::Leg::RL, robot::Color::BLUE, true);
        client.turn_off_leg(robot::Leg::RL, true);
        pause("RL 已 turn_off（用户域灭灯），接着 reset");
        ok = client.reset_legs({}, true);
        ask_verdict("TC-RST-03", "turn_off 后再 reset_legs()", ok ? 1 : 0,
                    "reset 后交还主控");

        ok = client.set_leg_color(robot::Leg::FL, robot::Color::ORANGE, true);
        ask_verdict("TC-RST-04", "reset 后再 set_leg_color(FL, ORANGE)", ok ? 1 : 0,
                    "可再次用户接管，橙色有效");

        if (opt.skip_motion) {
            results.push_back({"TC-RST-05", "运动中 reset", -1, "SKIP", "--skip-motion"});
            return;
        }

        reset_baseline();
        client.set_all_legs_color(robot::Color::CYAN, 180, true);
        std::cout << "  当前状态: " << client.get_current_state_name() << std::endl;
        ok = client.reset_legs({}, true);
        ask_verdict("TC-RST-05", "用户控灯后 reset（站立/现态）", ok ? 1 : 0,
                    "不卡死；灯尽快回主控表现");
    }

    void suite_other()
    {
        banner("组 D: 其他场景 (TC-OFF / TC-API / TC-MOT / TC-MULTI)");

        reset_baseline();
        client.set_leg_color(robot::Leg::FL, robot::Color::RED, true);
        bool ok = client.turn_off_leg(robot::Leg::FL, true);
        ask_verdict("TC-OFF-01a", "turn_off 保持用户域", ok ? 1 : 0,
                    "灯灭但仍用户控，主控不应立刻接管");
        ok = client.reset_legs({}, true);
        ask_verdict("TC-OFF-01b", "随后 reset 交还主控", ok ? 1 : 0,
                    "主控恢复对灯的控制");

        ok = client.set_legs_rgb({}, -1, false);
        ask_verdict("TC-API-01", "set_legs_rgb([]) 空列表", ok ? 1 : 0,
                    "返回 true 且灯效无变化");

        bool raised = false;
        try {
            client.set_leg_rgb(robot::Leg::FILL_FRONT, 255, 0, 0);
        } catch (const std::invalid_argument& e) {
            raised = true;
            std::cout << "  捕获 invalid_argument: " << e.what() << std::endl;
        }
        ask_verdict("TC-API-02", "FILL_FRONT 被拒绝", raised ? 1 : 0,
                    "抛 invalid_argument，不发 RPC");

        // C++ uint8_t RGB cannot express -1; skip invalid-RGB mirror of Python.
        results.push_back({"TC-API-03", "非法 RGB 抛错", -1, "SKIP",
                           "C++ uint8_t 无法表示越界 RGB；见 Python 联调"});

        std::cout << "\n--- TC-MULTI-01 高频连发 ---" << std::endl;
        ok = true;
        const uint8_t palette[][3] = {
            {255, 0, 0}, {0, 255, 0}, {0, 0, 255},
            {255, 255, 0}, {255, 0, 255}, {0, 255, 255},
        };
        for (const auto& rgb : palette) {
            ok = client.set_all_legs_rgb(rgb[0], rgb[1], rgb[2], 200, false) && ok;
            std::this_thread::sleep_for(std::chrono::milliseconds(150));
        }
        ask_verdict("TC-MULTI-01", "高频连续改色", ok ? 1 : 0,
                    "最终态正确、无卡死；最后一色为青色");

        client.reset_legs({}, true);
        ok = client.set_leg_brightness(robot::Leg::FL, 80, true);
        ask_verdict("TC-MULTI-02", "reset 后客户端缓存清空再设亮度", ok ? 1 : 0,
                    "行为符合无缓存默认白；远程仍可控制");

        if (opt.skip_motion) {
            results.push_back({"TC-MOT-01", "与运动并存", -1, "SKIP", "--skip-motion"});
            return;
        }

        reset_baseline();
        client.set_all_legs_color(robot::Color::GREEN, 200, true);
        std::cout << "  当前状态: " << client.get_current_state_name() << std::endl;
        ask_verdict("TC-MOT-01", "用户控灯 + 保持站立观察", 1,
                    "灯保持用户绿色；机器人行为正常");
    }

    void suite_smoke()
    {
        banner("冒烟: e11 等价流程");
        reset_baseline();
        client.set_leg_color(robot::Leg::FL, robot::Color::RED, true);
        pause();
        client.set_legs_rgb({{robot::Leg::FL, 255, 0, 0, 255},
                             {robot::Leg::FR, 0, 255, 0, 255},
                             {robot::Leg::RL, 0, 0, 255, 255},
                             {robot::Leg::RR, 255, 255, 0, 255}},
                            -1, true);
        pause();
        client.set_all_legs_color(robot::Color::CYAN, 128, true);
        pause();
        client.set_leg_brightness(robot::Leg::FR, 32, true);
        pause();
        client.turn_off_leg(robot::Leg::RL, true);
        pause();
        client.reset_legs({robot::Leg::FL}, true);
        pause();
        bool ok = client.reset_legs({}, true);
        ask_verdict("TC-SMOKE", "e11 全流程冒烟", ok ? 1 : 0,
                    "流程无异常，灯效符合 demo");
    }

    int print_summary()
    {
        banner("联调结果汇总");
        if (results.empty()) {
            std::cout << "  (无记录)" << std::endl;
            return 0;
        }

        int pass = 0, fail = 0, skip = 0, observe = 0;
        std::cout << "Case               Verdict  RPC    Title\n"
                  << std::string(70, '-') << "\n";
        for (const auto& r : results) {
            if (r.verdict == "PASS")
                ++pass;
            else if (r.verdict == "FAIL")
                ++fail;
            else if (r.verdict == "SKIP")
                ++skip;
            else
                ++observe;
            const char* rpc = "-";
            if (r.rpc_ok == 1)
                rpc = "OK";
            else if (r.rpc_ok == 0)
                rpc = "FAIL";
            std::cout << r.case_id;
            if (r.case_id.size() < 18)
                std::cout << std::string(18 - r.case_id.size(), ' ');
            std::cout << " " << r.verdict;
            if (r.verdict.size() < 8)
                std::cout << std::string(8 - r.verdict.size(), ' ');
            std::cout << " " << rpc;
            std::string rpc_pad = rpc;
            if (rpc_pad.size() < 6)
                std::cout << std::string(6 - rpc_pad.size(), ' ');
            std::cout << " " << r.title;
            if (!r.note.empty())
                std::cout << "  (" << r.note << ")";
            std::cout << "\n";
        }
        std::cout << std::string(70, '-') << "\n"
                  << "PASS=" << pass << "  FAIL=" << fail << "  SKIP=" << skip
                  << "  OBSERVE=" << observe << "\n"
                  << "可将上表填入联调报告模板。\n";
        return fail > 0 ? 1 : 0;
    }
};

Options parse_args(int argc, char** argv)
{
    Options opt;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--auto") {
            opt.auto_mode = true;
        } else if (a == "--skip-motion") {
            opt.skip_motion = true;
        } else if (a == "--suite" && i + 1 < argc) {
            opt.suite = argv[++i];
        } else if (a == "--hold" && i + 1 < argc) {
            opt.hold_sec = std::stod(argv[++i]);
        } else if (a.rfind("--", 0) == 0) {
            std::cerr << "Unknown option: " << a << std::endl;
        } else if (a.find(':') != std::string::npos || a.find('.') != std::string::npos) {
            opt.server = a;
        } else {
            // allow bare suite name as positional convenience
            opt.suite = a;
        }
    }
    return opt;
}

} // namespace

int main(int argc, char** argv)
{
    Options opt = parse_args(argc, argv);
    std::cout << "连接: " << opt.server << "\n"
              << "套件: " << opt.suite << "  auto=" << (opt.auto_mode ? "true" : "false")
              << "  hold=" << opt.hold_sec
              << "  skip_motion=" << (opt.skip_motion ? "true" : "false") << std::endl;

    robot::Client client(opt.server);
    robot::enable_safety_ready(client);

    Runner runner{client, opt, {}};

    if (opt.suite == "all") {
        runner.suite_cont();
        runner.suite_ctrl();
        runner.suite_color();
        runner.suite_bri();
        runner.suite_reset();
        runner.suite_other();
    } else if (opt.suite == "cont") {
        runner.suite_cont();
    } else if (opt.suite == "ctrl") {
        runner.suite_ctrl();
    } else if (opt.suite == "color") {
        runner.suite_color();
    } else if (opt.suite == "bri") {
        runner.suite_bri();
    } else if (opt.suite == "reset") {
        runner.suite_reset();
    } else if (opt.suite == "other") {
        runner.suite_other();
    } else if (opt.suite == "smoke") {
        runner.suite_smoke();
    } else {
        std::cerr << "Unknown suite: " << opt.suite
                  << " (all|cont|ctrl|color|bri|reset|other|smoke)" << std::endl;
        return 2;
    }

    return runner.print_summary();
}
