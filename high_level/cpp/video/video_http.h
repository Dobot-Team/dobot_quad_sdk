#pragma once
// =============================================================================
// Minimal HTTP client and TCP reachability check (no dependencies).
//
// Only two calls are ever made:
//   * POST http://<ip>:22000/settings/streaming/start|stop   robot streaming switch
//   * GET  http://<ip>:1984/api/streams                      camera state
//
// That is why there is no HTTPS, no redirect handling and no keep-alive: the
// less this layer does, the less it can go wrong.
// =============================================================================

#include <arpa/inet.h>
#include <cctype>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <unistd.h>

#include "video_types.h"

namespace robot {
namespace video {

/// HTTP status code and body.
struct HttpResponse {
    int status = 0;
    std::string body;
};

/// Splits ``"192.168.5.2:50051"`` (or ``"192.168.5.2"``) into host and port.
void split_host_port(const std::string& address, int default_port, std::string* host, int* port);

/// Whether a TCP connection to host:port can be established.
bool tcp_reachable(const std::string& host, int port, double timeout_s);

/// Sends one HTTP/1.1 request.
///
/// \param method "GET" / "POST"
/// \param path   Request path, e.g. ``/settings/streaming/start``
/// \param body   Request body (empty for GET)
/// \return false when the request never produced a response (unreachable,
///         timeout, malformed answer), with the reason in \p error. Any HTTP
///         answer - including 4xx/5xx - returns true: read ``response->status``.
bool http_request(
    const std::string& host,
    int port,
    const std::string& method,
    const std::string& path,
    const std::string& body,
    double timeout_s,
    HttpResponse* response,
    std::string* error);


// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

namespace {

/// Connects with a timeout; on failure returns -1 and sets *error.
int connect_with_timeout(const std::string& host, int port, double timeout_s, std::string* error)
{
    struct addrinfo hints;
    std::memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    const std::string service = std::to_string(port);
    struct addrinfo* result = nullptr;
    const int rc = ::getaddrinfo(host.c_str(), service.c_str(), &hints, &result);
    if (rc != 0 || result == nullptr) {
        if (error != nullptr) {
            *error = std::string("cannot resolve host: ") + gai_strerror(rc);
        }
        return -1;
    }

    int fd = -1;
    std::string last_error = "connect failed";

    for (struct addrinfo* it = result; it != nullptr; it = it->ai_next) {
        fd = ::socket(it->ai_family, it->ai_socktype, it->ai_protocol);
        if (fd < 0) {
            last_error = std::string("socket(): ") + std::strerror(errno);
            continue;
        }
        // Non-blocking connect plus poll, so the timeout is exact
        const int flags = ::fcntl(fd, F_GETFL, 0);
        ::fcntl(fd, F_SETFL, flags | O_NONBLOCK);
        int ok = ::connect(fd, it->ai_addr, it->ai_addrlen);
        if (ok != 0 && errno == EINPROGRESS) {
            struct pollfd pfd;
            pfd.fd = fd;
            pfd.events = POLLOUT;
            pfd.revents = 0;
            const int timeout_ms = static_cast<int>(timeout_s * 1000.0);
            const int polled = ::poll(&pfd, 1, timeout_ms > 0 ? timeout_ms : 1);
            if (polled <= 0) {
                last_error = polled == 0 ? "connect timed out" : std::string("poll(): ") + std::strerror(errno);
                ::close(fd);
                fd = -1;
                continue;
            }
            int so_error = 0;
            socklen_t len = sizeof(so_error);
            if (::getsockopt(fd, SOL_SOCKET, SO_ERROR, &so_error, &len) != 0 || so_error != 0) {
                last_error = std::string("connection refused or unreachable: ")
                    + std::strerror(so_error != 0 ? so_error : errno);
                ::close(fd);
                fd = -1;
                continue;
            }
        } else if (ok != 0) {
            last_error = std::string("connect(): ") + std::strerror(errno);
            ::close(fd);
            fd = -1;
            continue;
        }
        ::fcntl(fd, F_SETFL, flags); // back to blocking mode
        break;
    }
    ::freeaddrinfo(result);

    if (fd < 0 && error != nullptr) {
        *error = last_error;
    }
    return fd;
}

bool send_all(int fd, const std::string& data, std::string* error)
{
    size_t sent = 0;
    while (sent < data.size()) {
        const ssize_t n = ::send(fd, data.data() + sent, data.size() - sent, MSG_NOSIGNAL);
        if (n > 0) {
            sent += static_cast<size_t>(n);
            continue;
        }
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) {
            continue;
        }
        if (error != nullptr) {
            *error = std::string("send failed: ") + std::strerror(errno);
        }
        return false;
    }
    return true;
}

/// Waits until fd becomes readable: 1 readable, 0 timeout, -1 error.
int wait_readable(int fd, double timeout_s)
{
    struct pollfd pfd;
    pfd.fd = fd;
    pfd.events = POLLIN;
    pfd.revents = 0;
    const int timeout_ms = static_cast<int>(timeout_s * 1000.0);
    const int rc = ::poll(&pfd, 1, timeout_ms > 0 ? timeout_ms : 1);
    if (rc == 0) {
        return 0;
    }
    if (rc < 0) {
        return -1;
    }
    return 1;
}

/// Lower-cases ASCII text, so headers can be matched case-insensitively.
std::string lower_ascii(std::string text)
{
    for (char& c : text) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return text;
}

/// Reads one header value; empty when the header is absent.
std::string header_value(const std::string& headers, const std::string& name)
{
    const std::string wanted = lower_ascii(name);
    size_t pos = headers.find("\r\n");
    if (pos == std::string::npos) {
        return std::string();
    }
    pos += 2;
    while (pos < headers.size()) {
        const size_t eol = headers.find("\r\n", pos);
        const size_t end = eol == std::string::npos ? headers.size() : eol;
        const std::string line = headers.substr(pos, end - pos);
        const size_t colon = line.find(':');
        if (colon != std::string::npos && lower_ascii(line.substr(0, colon)) == wanted) {
            size_t value_start = colon + 1;
            while (value_start < line.size() && line[value_start] == ' ') {
                ++value_start;
            }
            return line.substr(value_start);
        }
        if (eol == std::string::npos) {
            break;
        }
        pos = eol + 2;
    }
    return std::string();
}

/// Decodes ``Transfer-Encoding: chunked``.
///
/// The robot's video service answers with chunked encoding as soon as the body
/// grows past a couple of kilobytes, which is the normal case while a player is
/// pulling a stream.
enum class ChunkStatus { Incomplete, Complete, Malformed };

ChunkStatus decode_chunked(const std::string& encoded, std::string* out, std::string* error)
{
    size_t pos = 0;
    out->clear();
    while (true) {
        const size_t eol = encoded.find("\r\n", pos);
        if (eol == std::string::npos) {
            return ChunkStatus::Incomplete; // the size line has not arrived yet
        }
        const std::string size_text = encoded.substr(pos, eol - pos);
        if (size_text.empty()
            || size_text.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos) {
            if (error != nullptr) {
                *error = "chunked answer has an invalid size line";
            }
            return ChunkStatus::Malformed;
        }
        const unsigned long size = std::strtoul(size_text.c_str(), nullptr, 16);
        pos = eol + 2;
        if (size == 0) {
            return ChunkStatus::Complete; // last chunk
        }
        if (pos + size > encoded.size()) {
            return ChunkStatus::Incomplete; // chunk still on its way
        }
        out->append(encoded, pos, size);
        pos += size;
        // The payload can arrive complete while its trailing CRLF is still in
        // the next TCP segment: those two bytes are on their way, not broken.
        // (Comparing straight away would report Malformed because a short
        // buffer never equals "\r\n".)
        if (pos + 2 > encoded.size()) {
            return ChunkStatus::Incomplete;
        }
        if (encoded.compare(pos, 2, "\r\n") != 0) {
            if (error != nullptr) {
                *error = "chunked answer misses its trailing CRLF";
            }
            return ChunkStatus::Malformed;
        }
        pos += 2;
    }
}

} // namespace

inline void split_host_port(const std::string& address, int default_port, std::string* host, int* port)
{
    std::string value = address;
    // drop a possible scheme
    const size_t scheme = value.find("://");
    if (scheme != std::string::npos) {
        value = value.substr(scheme + 3);
    }
    // drop the path
    const size_t slash = value.find('/');
    if (slash != std::string::npos) {
        value = value.substr(0, slash);
    }

    std::string host_part = value;
    int port_part = default_port;
    const size_t colon = value.rfind(':');
    if (colon != std::string::npos && value.find(']', colon) == std::string::npos) {
        host_part = value.substr(0, colon);
        const std::string digits = value.substr(colon + 1);
        if (!digits.empty()) {
            port_part = std::atoi(digits.c_str());
        }
    }
    if (!host_part.empty() && host_part[0] == '[' && host_part.back() == ']') {
        host_part = host_part.substr(1, host_part.size() - 2);
    }
    if (host != nullptr) {
        *host = host_part;
    }
    if (port != nullptr) {
        *port = port_part;
    }
}

inline bool tcp_reachable(const std::string& host, int port, double timeout_s)
{
    std::string error;
    const int fd = connect_with_timeout(host, port, timeout_s, &error);
    if (fd < 0) {
        return false;
    }
    ::close(fd);
    return true;
}

inline bool http_request(
    const std::string& host,
    int port,
    const std::string& method,
    const std::string& path,
    const std::string& body,
    double timeout_s,
    HttpResponse* response,
    std::string* error)
{
    const int fd = connect_with_timeout(host, port, timeout_s, error);
    if (fd < 0) {
        return false;
    }

    std::ostringstream head;
    head << method << " " << path << " HTTP/1.1\r\n"
         << "Host: " << host << ":" << port << "\r\n"
         << "Connection: close\r\n"
         << "User-Agent: DobotQuadSDK/1.3.0\r\n";
    if (method == "POST" || !body.empty()) {
        head << "Content-Type: application/json\r\n"
             << "Content-Length: " << body.size() << "\r\n";
    }
    head << "\r\n";
    if (!send_all(fd, head.str() + body, error)) {
        ::close(fd);
        return false;
    }

    std::string raw;
    const double deadline = monotonic_s() + timeout_s;
    while (true) {
        const double remaining = deadline - monotonic_s();
        if (remaining <= 0) {
            if (error != nullptr) {
                *error = "timed out while reading the response";
            }
            ::close(fd);
            return false;
        }
        const int ready = wait_readable(fd, remaining);
        if (ready <= 0) {
            if (ready < 0 && error != nullptr) {
                *error = std::string("poll(): ") + std::strerror(errno);
            } else if (error != nullptr) {
                *error = "timed out while reading the response";
            }
            ::close(fd);
            return false;
        }
        char buffer[8192];
        const ssize_t n = ::recv(fd, buffer, sizeof(buffer), 0);
        if (n > 0) {
            raw.append(buffer, static_cast<size_t>(n));
            // done when the headers and the whole body have arrived
            const size_t header_end = raw.find("\r\n\r\n");
            if (header_end != std::string::npos) {
                const std::string headers = raw.substr(0, header_end);
                const std::string chunked = header_value(headers, "Transfer-Encoding");
                if (lower_ascii(chunked).find("chunked") != std::string::npos) {
                    std::string decoded;
                    std::string decode_error;
                    const ChunkStatus status =
                        decode_chunked(raw.substr(header_end + 4), &decoded, &decode_error);
                    if (status == ChunkStatus::Complete) {
                        break;
                    }
                    if (status == ChunkStatus::Malformed) {
                        if (error != nullptr) {
                            *error = decode_error;
                        }
                        ::close(fd);
                        return false;
                    }
                } else {
                    const std::string length = header_value(headers, "Content-Length");
                    if (!length.empty()) {
                        const size_t want = static_cast<size_t>(std::atoi(length.c_str()));
                        if (raw.size() >= header_end + 4 + want) {
                            break;
                        }
                    }
                }
            }
            continue;
        }
        if (n == 0) {
            break; // peer closed the connection
        }
        if (errno == EINTR || errno == EAGAIN) {
            continue;
        }
        if (error != nullptr) {
            *error = std::string("receive failed: ") + std::strerror(errno);
        }
        ::close(fd);
        return false;
    }
    ::close(fd);

    const size_t header_end = raw.find("\r\n\r\n");
    if (header_end == std::string::npos) {
        if (error != nullptr) {
            *error = "response carries no HTTP headers";
        }
        return false;
    }
    const std::string status_line = raw.substr(0, raw.find("\r\n"));
    const size_t first_space = status_line.find(' ');
    int status = 0;
    if (first_space != std::string::npos) {
        status = std::atoi(status_line.substr(first_space + 1, 4).c_str());
    }

    const std::string headers = raw.substr(0, header_end);
    std::string received = raw.substr(header_end + 4);
    if (lower_ascii(header_value(headers, "Transfer-Encoding")).find("chunked") != std::string::npos) {
        std::string decoded;
        std::string decode_error;
        if (decode_chunked(received, &decoded, &decode_error) != ChunkStatus::Complete) {
            if (error != nullptr) {
                *error = decode_error.empty() ? std::string("chunked answer is incomplete")
                                             : decode_error;
            }
            return false;
        }
        received = decoded;
    }

    if (response != nullptr) {
        response->status = status;
        response->body = received;
    }
    return true;
}


} // namespace video
} // namespace robot
