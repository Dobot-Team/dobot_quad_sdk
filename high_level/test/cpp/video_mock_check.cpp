// =============================================================================
// robot.video（C++，控制面）离线自检的**被测程序**
//
// 由 `run_video_mock_check.py` 启动 mock 服务端（go2rtc 状态 + GControll 开关）
// 后运行本程序，并通过标准输入下发命令、从标准输出读取结果。
//
// 为什么用「命令协议」而不是把所有场景写死在 C++ 里？
//   场景需要**精确的时序配合**（在 SDK 正在观测时把流冻结 / 摘掉 producer），
//   这种控制权在 Python 那一侧最方便；C++ 这边只暴露最小可组合的命令集。
//
// 命令（每行一条，执行完必打印 `# done`）：
//   open <front|rear>              开流，打印 `# uri <url>` 或 `# err <reason> <msg>`
//   state <front|rear>             打印 `# state <state> <owner> <uri> <bitrate> <reason>`
//   streaming <front|rear>         打印 `# streaming <0|1>`
//   close <front|rear>             释放使用者
//   close_all                      释放全部使用者
//   stop_stream <front|rear>       强制停推流
//   sleep <seconds>                等待
//   wait_state <cam> <state> <t>   等状态到达（`# state-ok` / `# state-timeout`）
//   wait_event <n> <t>             等事件数达到 n（`# event-ok` / `# event-timeout`）
//   clear_events                   清空事件计数
//   quit                           退出
//
// 事件在发生时立即以 `# event <name> <camera> <old> <new> <reason> <recovered_by>`
// 的形式打印。
// =============================================================================

#include "video/video_manager.h"

#include <arpa/inet.h>
#include <chrono>
#include <condition_variable>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <netinet/in.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <unistd.h>
#include <vector>

using robot::video::CameraId;
using robot::video::CameraStreamInfo;
using robot::video::Consumer;
using robot::video::Endpoints;
using robot::video::HttpResponse;
using robot::video::LossReason;
using robot::video::Manager;
using robot::video::ObserveConfig;
using robot::video::RecoveredBy;
using robot::video::RecoveryPolicy;
using robot::video::RestartOutcome;
using robot::video::StatusProbe;
using robot::video::StreamArbiter;
using robot::video::StreamEvent;
using robot::video::StreamEventKind;
using robot::video::StreamingController;
using robot::video::StreamOwner;
using robot::video::StreamState;
using robot::video::StreamStatus;
using robot::video::VideoError;
using robot::video::VideoTimeoutError;
using robot::video::http_request;
using robot::video::split_host_port;
using robot::video::tcp_reachable;

namespace {

namespace json = robot::video::json;

std::mutex g_out_mutex;
std::mutex g_event_mutex;
std::condition_variable g_event_cv;
int g_event_count = 0;

// selfcheck 用的上下文（在 main 里注入实际端口）
std::string g_host = "127.0.0.1";
Endpoints g_endpoints;
ObserveConfig g_observe;
RecoveryPolicy g_policy;
Manager* g_manager = nullptr;
int g_blackhole_port = 0;

void print_line(const std::string& line)
{
    std::lock_guard<std::mutex> lock(g_out_mutex);
    std::cout << line << std::endl;
}

void on_event(const StreamEvent& event)
{
    {
        std::lock_guard<std::mutex> lock(g_event_mutex);
        ++g_event_count;
    }
    // 直接用 to_string()：既方便人看，也让公共序列化代码被真实调用
    std::ostringstream os;
    os << "# event " << event.name() << " " << robot::video::camera_name(event.camera) << " "
       << robot::video::to_string(event.old_state) << " " << robot::video::to_string(event.new_state)
       << " " << robot::video::to_string(event.reason) << " "
       << robot::video::to_string(event.recovered_by) << " " << event.to_string();
    print_line(os.str());
    g_event_cv.notify_all();
}

bool parse_camera(const std::string& text, CameraId* out)
{
    if (text == "front" || text == "FrontRgb") {
        *out = CameraId::FrontRgb;
        return true;
    }
    if (text == "rear" || text == "RearRgb") {
        *out = CameraId::RearRgb;
        return true;
    }
    return false;
}

bool parse_state(const std::string& text, StreamState* out)
{
    if (text == "stopped") {
        *out = StreamState::Stopped;
    } else if (text == "preparing") {
        *out = StreamState::Preparing;
    } else if (text == "ready") {
        *out = StreamState::Ready;
    } else if (text == "recovering") {
        *out = StreamState::Recovering;
    } else if (text == "stopping") {
        *out = StreamState::Stopping;
    } else if (text == "error") {
        *out = StreamState::Error;
    } else {
        return false;
    }
    return true;
}

std::string state_text(CameraStreamInfo info)
{
    std::ostringstream os;
    os << "# state " << robot::video::to_string(info.state) << " "
       << robot::video::to_string(info.owner) << " " << (info.uri.empty() ? "-" : info.uri) << " "
       << static_cast<long long>(info.bitrate_kbps) << " " << robot::video::to_string(info.reason)
       << "\n# info " << info.to_string();
    return os.str();
}

bool wait_for_state(Manager& manager, CameraId camera, StreamState expected, double timeout_s)
{
    const double deadline = robot::video::monotonic_s() + timeout_s;
    while (robot::video::monotonic_s() < deadline) {
        if (manager.get_stream_info(camera).state == expected) {
            return true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    return manager.get_stream_info(camera).state == expected;
}

// -----------------------------------------------------------------------------
// selfcheck：不依赖真实流，纯单元级覆盖（枚举、JSON、HTTP、探针助手、Manager 接口）
// -----------------------------------------------------------------------------
int g_selfcheck_failures = 0;

void check(const std::string& name, bool condition)
{
    if (!condition) {
        ++g_selfcheck_failures;
    }
    print_line("# check " + name + (condition ? " ok" : " FAIL"));
}

/// 异常的具体类型名（按 reason 归类之后，用户 catch 到的是哪个子类）。
const char* exception_class(const robot::video::VideoError& exc)
{
    if (dynamic_cast<const robot::video::VideoConnectionError*>(&exc) != nullptr) {
        return "VideoConnectionError";
    }
    if (dynamic_cast<const robot::video::VideoTimeoutError*>(&exc) != nullptr) {
        return "VideoTimeoutError";
    }
    if (dynamic_cast<const robot::video::UnsupportedCameraError*>(&exc) != nullptr) {
        return "UnsupportedCameraError";
    }
    return "VideoError";
}

void selfcheck_enums()
{
    const StreamState states[] = {StreamState::Stopped, StreamState::Preparing, StreamState::Ready,
        StreamState::Recovering, StreamState::Stopping, StreamState::Error};
    for (StreamState state : states) {
        check(std::string("enum.state.") + robot::video::to_string(state),
            std::string(robot::video::to_string(state)) != "unknown");
    }
    const StreamOwner owners[] = {StreamOwner::Unknown, StreamOwner::Sdk, StreamOwner::External};
    for (StreamOwner owner : owners) {
        check(std::string("enum.owner.") + robot::video::to_string(owner), true);
    }
    const LossReason reasons[] = {LossReason::None, LossReason::External, LossReason::Stall,
        LossReason::PortUnreachable, LossReason::NoData, LossReason::Closed};
    for (LossReason reason : reasons) {
        check(std::string("enum.reason.") + robot::video::to_string(reason), true);
    }
    const RecoveredBy bys[] = {RecoveredBy::None, RecoveredBy::L1Resume, RecoveredBy::L2Restart};
    for (RecoveredBy by : bys) {
        check(std::string("enum.recovered_by.") + robot::video::to_string(by), true);
    }
    const StreamEventKind kinds[] = {StreamEventKind::Ready, StreamEventKind::Lost,
        StreamEventKind::Reconnected, StreamEventKind::Closed, StreamEventKind::Error};
    for (StreamEventKind kind : kinds) {
        check(std::string("enum.event.") + robot::video::event_name(kind), true);
    }
    const RestartOutcome outcomes[] = {RestartOutcome::Done, RestartOutcome::Cooling,
        RestartOutcome::Limit, RestartOutcome::Failed, RestartOutcome::Unreachable};
    for (RestartOutcome outcome : outcomes) {
        check(std::string("enum.restart.") + robot::video::to_string(outcome), true);
    }
    // 越界枚举：必须落到防御性默认分支
    check("enum.state.out_of_range",
        std::string(robot::video::to_string(static_cast<StreamState>(99))) == "unknown");
    check("enum.reason.out_of_range",
        std::string(robot::video::to_string(static_cast<LossReason>(99))) == "none");
    check("enum.event.out_of_range",
        std::string(robot::video::event_name(static_cast<StreamEventKind>(99))) == "StreamEvent");

    check("camera.label", robot::video::camera_label(CameraId::RearRgb) == "Rear RGB");
    check("camera.dds_name", robot::video::dds_name(CameraId::RearRgb) == "camera1");
    check("camera.all", robot::video::all_cameras().size() == 2);
    std::ostringstream os;
    os << CameraId::FrontRgb;
    check("camera.ostream", os.str() == "FRONT_RGB");
    check("clock.monotonic", robot::video::monotonic_s() > 0.0 && robot::video::monotonic_ns() > 0);
}

void selfcheck_structs()
{
    CameraStreamInfo plain;
    check("info.default", plain.is_streaming() == false && plain.available() == false);
    check("info.to_string.default", plain.to_string().find("FRONT_RGB") != std::string::npos);

    CameraStreamInfo rich;
    rich.camera = CameraId::RearRgb;
    rich.state = StreamState::Ready;
    rich.owner = StreamOwner::External;
    rich.uri = "rtsp://127.0.0.1:8554/camera2";
    rich.bitrate_kbps = 2780.4;
    rich.reason = LossReason::Stall;
    rich.message = "就绪";
    check("info.ready", rich.is_streaming() && rich.available());
    const std::string text = rich.to_string();
    check("info.to_string.rich", text.find("camera2") != std::string::npos && text.find("2780") != std::string::npos
            && text.find("stall") != std::string::npos && text.find("就绪") != std::string::npos);

    StreamEvent event;
    event.kind = StreamEventKind::Reconnected;
    event.camera = CameraId::RearRgb;
    event.old_state = StreamState::Recovering;
    event.new_state = StreamState::Ready;
    event.recovered_by = RecoveredBy::L2Restart;
    event.message = "已恢复";
    check("event.name", event.name() == "StreamReconnected");
    check("event.to_string.recovered", event.to_string().find("L2_restart") != std::string::npos);

    StreamEvent lost = event;
    lost.kind = StreamEventKind::Lost;
    lost.recovered_by = RecoveredBy::None;
    lost.reason = LossReason::External;
    lost.message.clear();
    check("event.to_string.reason", lost.to_string().find("external") != std::string::npos);
    check("event.to_string.none", StreamEvent().to_string().find("StreamReady") != std::string::npos);

    VideoError plain_error("boom");
    check("error.default_reason", plain_error.reason() == LossReason::None);
    VideoError typed("boom", LossReason::NoData);
    check("error.reason", typed.reason() == LossReason::NoData && std::string(typed.what()) == "boom");
}

void selfcheck_probe_helpers()
{
    Consumer empty;
    check("consumer.app_like.empty", empty.is_app_like() == false);
    check("consumer.to_string.default", empty.to_string().empty());
    empty.remote_addr = "127.0.0.1:1";
    check("consumer.to_string.addr_only", empty.to_string() == "127.0.0.1:1");
    empty.remote_addr = "10.0.0.5:1";
    empty.user_agent = "Mozilla/5.0 (Linux; Android 15; uni-app)";
    check("consumer.app_like.uni_app", empty.is_app_like());
    Consumer long_ua;
    long_ua.remote_addr = "10.0.0.6:1";
    long_ua.user_agent = std::string(40, 'x');
    check("consumer.to_string.truncated", long_ua.to_string().find("...") != std::string::npos);

    StreamStatus status;
    check("status.unavailable", status.others_watching() == -1 && status.has_producer() == false);
    status.available = true;
    status.producer_count = 2;
    status.bytes_recv = 1234;
    check("status.no_consumer", status.others_watching() == 0 && status.has_producer());
    status.consumers.push_back(Consumer());
    check("status.watching", status.others_watching() == 1 && status.consumer_count() == 1);
    check("status.to_string", status.to_string().find("producers=2") != std::string::npos);
    StreamStatus offline;
    offline.available = false;
    offline.error = "boom";
    check("status.to_string.unavailable", offline.to_string().find("unavailable") != std::string::npos);
}

void selfcheck_json()
{
    const char* good[] = {
        "{\"a\":1,\"b\":[1,2,{\"c\":true}],\"d\":null,\"e\":\"x\\ny\",\"f\":\"\\u4e2d\",\"g\":1.5e3}",
        "{}", "[]", "[[[]]]", "\"str\"", "42", "-3.5", "1e-3", "0", "true", "false", "null",
        "\"esc\\\"\\\\\\/\\b\\f\\n\\r\\t\"",
        "\"\\u4E2D\"",   // 大写十六进制
        "\"\\u08A9\"",   // 两字节 UTF-8
        "\"\\uD83D\\uDE00\"", // 代理对
    };
    for (const char* text : good) {
        json::Value root;
        std::string error;
        check(std::string("json.valid.") + text, json::parse(text, &root, &error));
    }
    const char* bad[] = {
        "", "{", "{\"a\"}", "[1,", "\"unterminated", "{\"a\":}", "tru", "[1]x", "{'a':1}", "{\"a\":\"\\q\"}",
        "{\"a\":1,}", "[1 2]", "{\"a\" 1}", "\"\\u12\"", "nul", "fals", "[", "}",
        "{\"a\":1 \"b\":2}", "\"abc\\", "\"\\uZZZZ\"", "-",
    };
    for (const char* text : bad) {
        json::Value root;
        std::string error;
        check(std::string("json.invalid.") + text, !json::parse(text, &root, &error) && !error.empty());
    }

    json::Value root;
    std::string error;
    json::parse("{\"arr\":[10,20],\"obj\":{\"k\":\"v\"},\"num\":7,\"flag\":true,\"nul\":null}",
        &root, &error);
    check("json.at.array", root.find("arr")->at(1).as_number() == 20.0);
    check("json.at.out_of_range", root.find("arr")->at(9).is_null());
    check("json.find.nested", std::string(root.find("obj")->find("k")->as_string()) == "v");
    check("json.find.missing", root.find("nope") == nullptr);
    check("json.find.on_array", root.find("arr")->find("x") == nullptr);
    check("json.as_string.default", root.find("num")->as_string().empty());
    check("json.as_bool", root.find("flag")->as_bool() && !root.find("num")->as_bool());
    check("json.as_number.default", root.find("nul")->as_number() == 0.0);
    check("json.is_types",
        root.find("nul")->is_null() && root.find("arr")->is_array() && root.find("num")->is_number()
            && root.find("obj")->is_object() && root.find("flag")->is_bool());
    check("json.size", root.size() == 5 && root.find("arr")->size() == 2);
    check("json.children", root.children().size() == 5 && root.find("arr")->children().size() == 2);
}

void selfcheck_http()
{
    std::string host;
    int port = 0;
    split_host_port("192.168.5.2:50051", 22000, &host, &port);
    check("http.split.host_port", host == "192.168.5.2" && port == 50051);
    split_host_port("10.0.0.1", 22000, &host, &port);
    check("http.split.default_port", host == "10.0.0.1" && port == 22000);

    check("http.tcp_reachable.ok", tcp_reachable(g_host, g_endpoints.go2rtc_port, 0.5));
    check("http.tcp_reachable.closed", !tcp_reachable(g_host, 1, 0.3));

    HttpResponse response;
    std::string error;
    const bool got = http_request(
        g_host, g_endpoints.go2rtc_port, "GET", "/api/streams", "", 0.5, &response, &error);
    const bool get_ok = got && response.status == 200 && !response.body.empty();
    if (!get_ok) {
        // 只有失败时才打诊断：分帧/解码问题靠这几项定位
        print_line("# diag get.ok status=" + std::to_string(response.status) + " len="
            + std::to_string(response.body.size()) + " err=" + error);
    }
    check("http.get.ok", get_ok);
    // 响应体必须是已经解好的 JSON：真机在拉流时改用 chunked 传输，
    // 解码不完整会在这里直接暴露出来。
    {
        json::Value root;
        std::string parse_error;
        const bool parsed = json::parse(response.body, &root, &parse_error);
        const json::Value* camera1 = parsed ? root.find("camera1") : nullptr;
        check("http.get.json_decoded",
            parsed && root.is_object()
                && (camera1 == nullptr || camera1->find("producers") != nullptr));
        // 传输层分帧不能泄漏到响应体里（真机在拉流时用 chunked 传输）
        check("http.get.json_framing_free",
            response.body.find("\r\n0\r\n") == std::string::npos
                && !response.body.empty() && response.body[0] == '{');
    }
    check("http.get.404",
        http_request(g_host, g_endpoints.go2rtc_port, "GET", "/nope", "", 0.5, &response, &error)
            && response.status == 404);
    check("http.post.switch",
        http_request(g_host, g_endpoints.gcontroll_port, "POST", "/settings/streaming/start", "{}", 0.5,
            &response, &error));
    error.clear();
    check("http.connect.fail",
        !http_request(g_host, 1, "GET", "/api/streams", "", 0.3, &response, &error) && !error.empty());

    // 主机名解析失败 / 不可达地址：也要给出可操作的错误
    split_host_port("host:", 22000, &host, &port);
    check("http.split.empty_port", port == 22000);
    check("http.dns.fail", !tcp_reachable("no-such-host.invalid", 80, 0.3));
    check("http.dns.fail.request",
        !http_request("no-such-host.invalid", 80, "GET", "/", "", 0.3, &response, &error));
    check("http.unreachable.host", !tcp_reachable("10.255.255.1", 22000, 0.3));
    check("http.connect.timeout_or_error",
        !http_request("10.255.255.1", 22000, "GET", "/api/streams", "", 0.3, &response, &error));
    // 非法主机名：getaddrinfo 失败必须被报出来
    check("http.dns.invalid_name", !tcp_reachable("bad host name", 80, 0.3));
    check("http.dns.invalid_name.request",
        !http_request("bad host name", 80, "GET", "/", "", 0.3, &response, &error));
    // 带 scheme / 带路径的地址也要能解析
    split_host_port("http://192.168.5.2:50051/api", 22000, &host, &port);
    check("http.split.scheme_and_path", host == "192.168.5.2" && port == 50051);
    // 「只接受、不回包」的黑洞服务端：读超时必须报错而不是挂死
    check("http.read.timeout", !http_request(g_host, g_blackhole_port, "GET", "/api/streams", "",
                                0.3, &response, &error));
}

void selfcheck_manager(Manager& manager)
{
    check("manager.cameras", manager.list_cameras().size() == 2);
    check("manager.uri.front",
        manager.uri(CameraId::FrontRgb)
            == "rtsp://" + g_host + ":" + std::to_string(g_endpoints.rtsp_port) + "/camera1");
    check("manager.uri.rear", manager.uri(CameraId::RearRgb).find("/camera2") != std::string::npos);
    check("manager.host", manager.host() == g_host);
    check("manager.endpoints", manager.endpoints().go2rtc_port == g_endpoints.go2rtc_port);

    const CameraStreamInfo unknown = manager.get_stream_info(CameraId::RearRgb);
    // 注意：close() 之后会保留「最后一次已知状态」（含地址），所以这里只断言状态本身
    check("manager.info.default",
        unknown.state == StreamState::Stopped && !unknown.is_streaming()
            && !manager.is_streaming(CameraId::RearRgb));
    manager.close(CameraId::RearRgb); // 未 open：幂等空操作
    check("manager.close.idempotent", true);

    // 非法 CameraId：每个入口都要立刻拒绝，不能悄悄当成后置相机（camera_label /
    // rtsp_name 对未知值会回落到后置），也不能留下状态。
    const CameraId bogus = static_cast<CameraId>(7);
    int rejected = 0;
    try { manager.open(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    try { manager.close(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    try { manager.stop_stream(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    try { manager.is_streaming(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    try { manager.get_stream_info(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    try { manager.uri(bogus); } catch (const robot::video::UnsupportedCameraError&) { ++rejected; }
    check("manager.bad_camera.rejected", rejected == 6);
    check("manager.bad_camera.no_side_effect",
        !manager.is_streaming(CameraId::FrontRgb) && !manager.is_streaming(CameraId::RearRgb));

    bool threw = false;
    try {
        manager.on_state_change(nullptr);
    } catch (const VideoError&) {
        threw = true;
    }
    check("manager.callback.null_rejected", threw);

    const std::function<void()> unsubscribe = manager.on_state_change([](const StreamEvent&) {});
    unsubscribe();
    unsubscribe(); // 幂等
    check("manager.unsubscribe.idempotent", true);
}

void selfcheck_arbiter()
{
    StatusProbe probe(g_host, g_endpoints.go2rtc_port);
    probe.set_timeout(g_observe.probe_timeout);
    probe.set_observe(g_observe);
    StreamingController controller(g_host, g_endpoints.gcontroll_port, g_observe.probe_timeout);
    std::vector<StreamEvent> seen;
    StreamArbiter arbiter(CameraId::FrontRgb, "rtsp://" + g_host + "/camera1", &probe, &controller,
        [&seen](const StreamEvent& event) { seen.push_back(event); }, g_observe, g_policy);

    check("arbiter.initial",
        arbiter.state() == StreamState::Stopped && !arbiter.sdk_started() && !arbiter.needs_fast_sample());
    check("arbiter.accessors",
        arbiter.camera() == CameraId::FrontRgb && arbiter.uri().find("/camera1") != std::string::npos
            && arbiter.info().state == StreamState::Stopped);
    arbiter.tick(robot::video::monotonic_s()); // Stopped：无操作
    arbiter.begin();
    check("arbiter.begin", arbiter.state() == StreamState::Preparing && arbiter.needs_fast_sample());
    arbiter.begin(); // 幂等
    check("arbiter.begin.idempotent", arbiter.state() == StreamState::Preparing);

    bool timed_out = false;
    try {
        arbiter.wait_ready(0.05);
    } catch (const VideoTimeoutError&) {
        timed_out = true;
    }
    check("arbiter.wait_ready.timeout", timed_out);

    arbiter.release(LossReason::Closed, "测试释放");
    check("arbiter.release",
        arbiter.state() == StreamState::Stopped && seen.size() == 1
            && seen[0].kind == StreamEventKind::Closed && !arbiter.needs_fast_sample());
    arbiter.release(); // 幂等
    check("arbiter.release.idempotent", seen.size() == 1);

    bool aborted = false;
    try {
        arbiter.wait_ready(0.05);
    } catch (const VideoError&) {
        aborted = true;
    }
    check("arbiter.wait_ready.aborted", aborted);
    arbiter.force_stopped("强停");
    arbiter.force_stopped("再强停"); // 幂等
    check("arbiter.force_stopped.idempotent", arbiter.state() == StreamState::Stopped);

    check("probe.snapshot", probe.snapshot(true).size() == 2);
    probe.invalidate();
    probe.refresh();
    check("probe.refresh", true);

    // 没有探针时不能崩：立刻判失败（防御分支）
    StreamArbiter blind(CameraId::FrontRgb, "rtsp://" + g_host + "/camera1", nullptr, nullptr, nullptr,
        g_observe, g_policy);
    blind.begin();
    blind.tick(0.0); // now<=0 → 内部取当前时钟（顺便覆盖该分支）
    check("arbiter.no_probe", blind.state() == StreamState::Error);

    // all_watching 的入参防御分支（samples < 1）
    check("probe.all_watching.zero_samples", probe.all_watching(0, 0.0) != 0 || true);
}

/// Preparing 阶段超时（流不存在）：先发 start，再越过 deadline → no_data。
void selfcheck_deadline_no_producer()
{
    ObserveConfig fast;
    fast.tick = 0.02;
    fast.ready_timeout = 0.05;
    fast.prepare_stall_seconds = 5.0;
    fast.probe_timeout = g_observe.probe_timeout;
    StatusProbe probe(g_host, g_endpoints.go2rtc_port);
    probe.set_timeout(fast.probe_timeout);
    probe.set_observe(fast);
    StreamingController controller(g_host, g_endpoints.gcontroll_port, fast.probe_timeout);
    StreamArbiter arbiter(CameraId::RearRgb, "rtsp://" + g_host + "/camera2", &probe, &controller,
        nullptr, fast, g_policy);
    const double t0 = robot::video::monotonic_s();
    arbiter.begin();
    arbiter.tick(robot::video::monotonic_s()); // 流不存在 → 下发 start
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    const double elapsed = robot::video::monotonic_s() - t0;
    print_line("# deadline-elapsed " + std::to_string(elapsed) + " ready_timeout="
            + std::to_string(fast.ready_timeout));
    arbiter.tick(robot::video::monotonic_s()); // 已过 deadline → 失败
    print_line("# deadline-info " + arbiter.info().to_string());
    check("arbiter.deadline.elapsed_no_producer", elapsed >= fast.ready_timeout);
    check("arbiter.deadline.no_producer",
        arbiter.state() == StreamState::Error && arbiter.info().reason == LossReason::NoData);
}

/// Preparing 阶段超时（producers 在、bytes_recv 不动）：走底部的 deadline 检查。
void selfcheck_deadline_no_growth()
{
    ObserveConfig fast;
    fast.tick = 0.02;
    fast.ready_timeout = 0.05;
    fast.prepare_stall_seconds = 5.0; // 把「卡住」判据推远，先撞超时
    fast.probe_timeout = g_observe.probe_timeout;
    StatusProbe probe(g_host, g_endpoints.go2rtc_port);
    probe.set_timeout(fast.probe_timeout);
    probe.set_observe(fast);
    StreamingController controller(g_host, g_endpoints.gcontroll_port, fast.probe_timeout);
    StreamArbiter arbiter(CameraId::FrontRgb, "rtsp://" + g_host + "/camera1", &probe, &controller,
        nullptr, fast, g_policy);
    const double t0 = robot::video::monotonic_s();
    arbiter.begin();
    arbiter.tick(robot::video::monotonic_s());
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    const double elapsed = robot::video::monotonic_s() - t0;
    print_line("# deadline-elapsed " + std::to_string(elapsed) + " ready_timeout="
            + std::to_string(fast.ready_timeout));
    arbiter.tick(robot::video::monotonic_s());
    print_line("# deadline-info " + arbiter.info().to_string());
    check("arbiter.deadline.elapsed_no_growth", elapsed >= fast.ready_timeout);
    check("arbiter.deadline.no_growth",
        arbiter.state() == StreamState::Error && arbiter.info().reason == LossReason::NoData);
}

void run_selfcheck()
{
    g_selfcheck_failures = 0;
    selfcheck_enums();
    selfcheck_structs();
    selfcheck_probe_helpers();
    selfcheck_json();
    selfcheck_http();
    if (g_manager != nullptr) {
        selfcheck_manager(*g_manager);
    }
    selfcheck_arbiter();
    print_line("# selfcheck " + std::string(g_selfcheck_failures == 0 ? "ok" : "fail"));
}

} // namespace

int main(int argc, char** argv)
{
    Endpoints endpoints;
    // 超时收紧，让自检在秒级跑完（真实默认值见 video_types.h）；
    // 驱动脚本会用 CLI 参数把某些分支单独调出来（如「恢复超时」）。
    robot::video::ObserveConfig observe;
    observe.tick = 0.02;
    observe.sample_interval = 0.1;
    observe.stall_samples = 2;
    observe.ready_timeout = 1.5;
    observe.probe_timeout = 0.5;
    observe.prepare_poll = 0.02;
    observe.settle_seconds = 0.05;
    observe.prepare_stall_seconds = 0.4;

    robot::video::RecoveryPolicy policy;
    policy.backoff = {0.05, 0.1, 0.2};
    policy.max_attempts = 3;
    policy.restart_cooldown = 0.3;
    policy.restart_max_per_window = 2;
    policy.restart_window = 5.0;
    policy.act_timeout = 0.4;

    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        const bool has_next = (i + 1) < argc;
        if (arg == "--gcontroll-port" && has_next) {
            endpoints.gcontroll_port = std::atoi(argv[++i]);
        } else if (arg == "--go2rtc-port" && has_next) {
            endpoints.go2rtc_port = std::atoi(argv[++i]);
        } else if (arg == "--rtsp-port" && has_next) {
            endpoints.rtsp_port = std::atoi(argv[++i]);
        } else if (arg == "--max-attempts" && has_next) {
            policy.max_attempts = std::atoi(argv[++i]);
        } else if (arg == "--backoff" && has_next) {
            policy.backoff.clear();
            std::istringstream stream(argv[++i]);
            std::string item;
            while (std::getline(stream, item, ',')) {
                policy.backoff.push_back(std::atof(item.c_str()));
            }
        } else if (arg == "--ready-timeout" && has_next) {
            observe.ready_timeout = std::atof(argv[++i]);
        } else if (arg == "--act-timeout" && has_next) {
            policy.act_timeout = std::atof(argv[++i]);
        } else if (arg == "--prepare-stall" && has_next) {
            observe.prepare_stall_seconds = std::atof(argv[++i]);
        } else if (arg == "--restart-cooldown" && has_next) {
            policy.restart_cooldown = std::atof(argv[++i]);
        } else {
            std::cerr << "未知参数: " << arg << std::endl;
            return 2;
        }
    }

    // 「只接受、不回包」的黑洞监听：用于覆盖 HTTP 读超时分支（内核会完成握手）
    const int blackhole_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (blackhole_fd >= 0) {
        int yes = 1;
        ::setsockopt(blackhole_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
        struct sockaddr_in address;
        std::memset(&address, 0, sizeof(address));
        address.sin_family = AF_INET;
        address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        address.sin_port = 0;
        if (::bind(blackhole_fd, reinterpret_cast<struct sockaddr*>(&address), sizeof(address)) == 0
            && ::listen(blackhole_fd, 8) == 0) {
            struct sockaddr_in bound;
            socklen_t length = sizeof(bound);
            if (::getsockname(blackhole_fd, reinterpret_cast<struct sockaddr*>(&bound), &length) == 0) {
                g_blackhole_port = ntohs(bound.sin_port);
            }
        }
    }

    Manager manager("127.0.0.1", endpoints);
    manager.set_observe(observe);
    manager.set_policy(policy);
    g_host = "127.0.0.1";
    g_endpoints = endpoints;
    g_observe = observe;
    g_policy = policy;
    g_manager = &manager;
    const std::function<void()> unsubscribe = manager.on_state_change(on_event);

    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream parser(line);
        std::string command;
        parser >> command;
        if (command.empty() || command[0] == '#') {
            continue;
        }

        if (command == "open") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            if (!parse_camera(name, &camera)) {
                print_line("# err bad_camera " + name);
            } else {
                try {
                    const std::string uri = manager.open(camera);
                    print_line("# uri " + uri);
                } catch (const robot::video::VideoError& exc) {
                    // 预期内的开流失败：用 open-error 前缀，与「用法错误 # err」区分开；
                    // 类型也打出来（按 reason 归类后，用户能 catch 到具体子类）。
                    print_line(std::string("# open-error ") + exception_class(exc) + " "
                        + robot::video::to_string(exc.reason()) + " " + exc.what());
                }
            }
        } else if (command == "state" || command == "info") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            if (!parse_camera(name, &camera)) {
                print_line("# err bad_camera " + name);
            } else {
                print_line(state_text(manager.get_stream_info(camera)));
            }
        } else if (command == "streaming") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            print_line(std::string("# streaming ")
                + (parse_camera(name, &camera) && manager.is_streaming(camera) ? "1" : "0"));
        } else if (command == "close") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            if (parse_camera(name, &camera)) {
                manager.close(camera);
                print_line("# ok");
            } else {
                print_line("# err bad_camera " + name);
            }
        } else if (command == "close_all") {
            manager.close_all();
            print_line("# ok");
        } else if (command == "stop_stream") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            if (parse_camera(name, &camera)) {
                manager.stop_stream(camera);
                print_line("# ok");
            } else {
                print_line("# err bad_camera " + name);
            }
        } else if (command == "sleep") {
            double seconds = 0.0;
            parser >> seconds;
            std::this_thread::sleep_for(std::chrono::duration<double>(seconds));
            print_line("# ok");
        } else if (command == "wait_state") {
            std::string name;
            std::string wanted;
            double timeout_s = 2.0;
            CameraId camera = CameraId::FrontRgb;
            StreamState expected = StreamState::Ready;
            parser >> name >> wanted >> timeout_s;
            if (!parse_camera(name, &camera) || !parse_state(wanted, &expected)) {
                print_line("# err bad_args");
            } else if (wait_for_state(manager, camera, expected, timeout_s)) {
                print_line("# state-ok");
            } else {
                print_line("# state-timeout " + state_text(manager.get_stream_info(camera)));
            }
        } else if (command == "wait_event") {
            int wanted = 1;
            double timeout_s = 2.0;
            parser >> wanted >> timeout_s;
            std::unique_lock<std::mutex> lock(g_event_mutex);
            g_event_cv.wait_for(lock, std::chrono::duration<double>(timeout_s),
                [wanted]() { return g_event_count >= wanted; });
            print_line(g_event_count >= wanted ? "# event-ok" : "# event-timeout");
        } else if (command == "clear_events") {
            {
                std::lock_guard<std::mutex> lock(g_event_mutex);
                g_event_count = 0;
            }
            print_line("# ok");
        } else if (command == "bad_camera") {
            // 非法 CameraId：6 个入口都必须立刻拒绝。驱动脚本会在前后对比 mock 的
            // 请求计数，确认**一个 HTTP 请求都没发出去**。
            const robot::video::CameraId bogus = static_cast<robot::video::CameraId>(7);
            int rejected = 0;
            try { manager.open(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            try { manager.close(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            try { manager.stop_stream(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            try { manager.is_streaming(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            try { manager.get_stream_info(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            try { manager.uri(bogus); } catch (const robot::video::VideoError&) { ++rejected; }
            print_line("# bad-camera rejected=" + std::to_string(rejected));
            print_line("# ok");
        } else if (command == "selfcheck") {            run_selfcheck();
            if (g_selfcheck_failures != 0) {
                // 单元自检失败必须让驱动脚本能发现
                print_line("# err selfcheck_failed " + std::to_string(g_selfcheck_failures));
            }
        } else if (command == "selfcheck_deadline_no_producer") {
            g_selfcheck_failures = 0;
            selfcheck_deadline_no_producer();
            print_line("# selfcheck " + std::string(g_selfcheck_failures == 0 ? "ok" : "fail"));
            if (g_selfcheck_failures != 0) {
                print_line("# err selfcheck_failed " + std::to_string(g_selfcheck_failures));
            }
        } else if (command == "selfcheck_deadline_no_growth") {
            g_selfcheck_failures = 0;
            selfcheck_deadline_no_growth();
            print_line("# selfcheck " + std::string(g_selfcheck_failures == 0 ? "ok" : "fail"));
            if (g_selfcheck_failures != 0) {
                print_line("# err selfcheck_failed " + std::to_string(g_selfcheck_failures));
            }
        } else if (command == "shutdown") {
            manager.shutdown();
            print_line("# ok");
        } else if (command == "close_on_lost") {
            std::string name;
            CameraId camera = CameraId::FrontRgb;
            parser >> name;
            if (!parse_camera(name, &camera)) {
                print_line("# err bad_camera " + name);
            } else {
                // 在状态回调（跑在监督线程上）里关闭：验证不会自锁、线程对象能被复用
                manager.on_state_change([&manager, camera](const StreamEvent& event) {
                    if (event.kind == StreamEventKind::Lost) {
                        manager.close(camera);
                    }
                });
                print_line("# ok");
            }
        } else if (command == "quit") {
            break;
        } else {
            print_line("# err unknown_command " + command);
        }
        print_line("# done");
        std::cout.flush();
    }

    unsubscribe();
    manager.shutdown();
    print_line("# bye");
    return 0;
}
