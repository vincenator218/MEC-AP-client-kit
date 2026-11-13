#include "link.h"

#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <string>
#include <vector>

#include "apply.h"
#include "listener.h"
#include "log.h"
#include "version.h"

namespace mecap::link {
namespace {

bool g_buildOk = false;
std::string g_why, g_applyWhy;
std::vector<apply::Request> g_applyRequests; // read from the client, submitted once per loop
std::wstring g_journalPath, g_ackedPath;
long long g_lastSeq = 0, g_acked = 0;
SOCKET g_listen = INVALID_SOCKET, g_client = INVALID_SOCKET;
std::string g_inbuf;

// The number after "key": in a flat JSON line (our own protocol: no nesting, no spaces in keys).
long long numOf(const std::string& line, const char* key, long long fallback = 0) {
    const std::string k = std::string("\"") + key + "\":";
    const size_t at = line.find(k);
    if (at == std::string::npos) return fallback;
    size_t p = at + k.size();
    while (p < line.size() && line[p] == ' ') ++p;
    return std::strtoll(line.c_str() + p, nullptr, 10);
}

long long seqOf(const std::string& line) { return numOf(line, "seq"); }

// The string after "key": ("key": "x" or "key":"x"), or "" when missing.
std::string strOf(const std::string& line, const char* key) {
    const std::string k = std::string("\"") + key + "\":";
    size_t p = line.find(k);
    if (p == std::string::npos) return "";
    p += k.size();
    while (p < line.size() && line[p] == ' ') ++p;
    if (p >= line.size() || line[p] != '"') return "";
    const size_t end = line.find('"', p + 1);
    return end == std::string::npos ? "" : line.substr(p + 1, end - p - 1);
}

std::string cmdOf(const std::string& line) { return strOf(line, "cmd"); }

// "hash": "67800619" -> 0x67800619; 0 when missing.
uint32_t hashOf(const std::string& line) {
    return static_cast<uint32_t>(std::strtoul(strOf(line, "hash").c_str(), nullptr, 16));
}

std::string jsonSafe(const std::string& s) {
    std::string out;
    for (char c : s) out += (c == '"' || c == '\\') ? '\'' : c;
    return out;
}

std::vector<std::string> journalLines() {
    std::vector<std::string> out;
    std::ifstream f(g_journalPath);
    for (std::string line; std::getline(f, line);)
        if (!line.empty() && line.back() == '}') out.push_back(line); // a torn last line is skipped
    return out;
}

void loadState() {
    for (const std::string& line : journalLines()) g_lastSeq = std::max(g_lastSeq, seqOf(line));
    std::ifstream a(g_ackedPath);
    a >> g_acked;
    LOG("journal: %lld finishes recorded, %lld acknowledged by the client", g_lastSeq, g_acked);
}

void saveAcked() {
    std::ofstream a(g_ackedPath, std::ios::trunc);
    a << g_acked << "\n";
}

std::string hex8(uint32_t v) {
    char b[9];
    snprintf(b, sizeof(b), "%08x", v);
    return b;
}

void closeClient() {
    if (g_client != INVALID_SOCKET) {
        closesocket(g_client);
        g_client = INVALID_SOCKET;
        g_inbuf.clear();
        LOG("client disconnected");
    }
}

bool sendLine(const std::string& line) {
    if (g_client == INVALID_SOCKET) return false;
    const std::string data = line + "\n";
    size_t done = 0;
    while (done < data.size()) {
        const int n = send(g_client, data.data() + done, static_cast<int>(data.size() - done), 0);
        if (n == SOCKET_ERROR) {
            if (WSAGetLastError() == WSAEWOULDBLOCK) {
                Sleep(5);
                continue;
            }
            closeClient();
            return false;
        }
        done += static_cast<size_t>(n);
    }
    return true;
}

void sendHello() {
    char b[768];
    const bool canApply = apply::enabled();
    snprintf(b, sizeof(b),
             "{\"ev\":\"hello\",\"proto\":%d,\"dll\":\"%s\",\"build_ok\":%s,\"why\":\"%s\",\"apply\":%s,"
             "\"apply_why\":\"%s\",\"acked\":%lld,\"last\":%lld}",
             kProtocol, kVersion, g_buildOk ? "true" : "false", jsonSafe(g_why).c_str(), canApply ? "true" : "false",
             canApply ? "" : jsonSafe(g_applyWhy).c_str(), g_acked, g_lastSeq);
    if (!sendLine(b)) return;
    for (const std::string& line : journalLines())
        if (seqOf(line) > g_acked && !sendLine(line)) return;
}

void onEvent(const listener::Event& e) {
    using listener::Kind;
    if (e.kind != Kind::Finished) {
        LOG("challenge %s %s", hex8(e.contentId).c_str(), e.kind == Kind::Started ? "started" : "cancelled");
        const std::string line = std::string("{\"ev\":\"") + (e.kind == Kind::Started ? "started" : "cancelled") +
                                 "\",\"content_id\":\"" + hex8(e.contentId) + "\"}";
        sendLine(line);
        return;
    }
    char b[384];
    snprintf(b, sizeof(b),
             "{\"ev\":\"finished\",\"seq\":%lld,\"time\":%lld,\"content_id\":\"%s\",\"run_cs\":%lld,"
             "\"record_cs\":%lld,\"delta_cs\":%d,\"had_record\":%d,\"new_record\":%d,\"set\":%u}",
             ++g_lastSeq, static_cast<long long>(time(nullptr)), hex8(e.contentId).c_str(),
             static_cast<long long>(e.runCs), static_cast<long long>(e.recordCs), e.deltaCs, e.hadRecord ? 1 : 0,
             e.newRecord ? 1 : 0, e.set);
    {
        std::ofstream j(g_journalPath, std::ios::app); // written before it is sent: the journal is the truth
        j << b << "\n";
    }
    LOG("finished %s in %lld.%02lld (seq %lld)", hex8(e.contentId).c_str(), e.runCs / 100, e.runCs % 100, g_lastSeq);
    sendLine(b);
}

// What the game showed after an apply request. Live only: the client re-asks after a reconnect.
void onApplied(const apply::Result& r) {
    LOG("apply %s=%d: %s (%d entities check it, %d targeted%s)", hex8(r.hash).c_str(), r.value, r.result, r.matched,
        r.targets, r.live ? ", the live one" : "");
    char b[256];
    snprintf(b, sizeof(b),
             "{\"ev\":\"applied\",\"id\":%u,\"hash\":\"%s\",\"value\":%d,\"result\":\"%s\",\"matched\":%d,"
             "\"targets\":%d,\"live\":%s}",
             r.id, hex8(r.hash).c_str(), r.value, r.result, r.matched, r.targets, r.live ? "true" : "false");
    sendLine(b);
}

void readClient() {
    char buf[512];
    for (;;) {
        const int n = recv(g_client, buf, sizeof(buf), 0);
        if (n == 0) {
            closeClient();
            return;
        }
        if (n == SOCKET_ERROR) {
            if (WSAGetLastError() != WSAEWOULDBLOCK) closeClient();
            return;
        }
        g_inbuf.append(buf, static_cast<size_t>(n));
        size_t nl;
        while ((nl = g_inbuf.find('\n')) != std::string::npos) {
            const std::string line = g_inbuf.substr(0, nl);
            g_inbuf.erase(0, nl + 1);
            if (cmdOf(line) == "ack") {
                const long long seq = seqOf(line);
                if (seq > g_acked && seq <= g_lastSeq) {
                    g_acked = seq;
                    saveAcked();
                }
            } else if (cmdOf(line) == "apply") {
                const long long value = numOf(line, "value", -1);
                const uint32_t hash = hashOf(line);
                const auto id = static_cast<uint32_t>(numOf(line, "id"));
                if (hash && value >= 0 && value <= 0xFFFF && g_applyRequests.size() < 256)
                    g_applyRequests.push_back({id, hash, static_cast<int32_t>(value)});
            }
        }
        if (g_inbuf.size() > 65536) g_inbuf.clear();
    }
}

bool openListen() {
    WSADATA wsa;
    if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return false;
    g_listen = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (g_listen == INVALID_SOCKET) return false;
    sockaddr_in a{};
    a.sin_family = AF_INET;
    a.sin_port = htons(kPort);
    inet_pton(AF_INET, "127.0.0.1", &a.sin_addr); // never reachable from another machine
    if (bind(g_listen, reinterpret_cast<sockaddr*>(&a), sizeof(a)) == SOCKET_ERROR ||
        listen(g_listen, 1) == SOCKET_ERROR) {
        LOG("link: cannot listen on 127.0.0.1:%u (error %d); is another copy loaded?", kPort, WSAGetLastError());
        closesocket(g_listen);
        g_listen = INVALID_SOCKET;
        return false;
    }
    u_long nb = 1;
    ioctlsocket(g_listen, FIONBIO, &nb);
    LOG("link: listening on 127.0.0.1:%u", kPort);
    return true;
}

DWORD WINAPI run(void*) {
    const bool net = openListen();
    for (;;) {
        if (net && g_client == INVALID_SOCKET) {
            const SOCKET c = accept(g_listen, nullptr, nullptr);
            if (c != INVALID_SOCKET) {
                u_long nb = 1;
                ioctlsocket(c, FIONBIO, &nb);
                g_client = c;
                LOG("client connected");
                sendHello();
            }
        }
        for (const listener::Event& e : listener::drain()) onEvent(e);
        if (g_client != INVALID_SOCKET) readClient();
        if (!g_applyRequests.empty()) {
            apply::submit(g_applyRequests); // the scan runs here, on this thread, not the game's
            g_applyRequests.clear();
        }
        for (const apply::Result& r : apply::drainResults()) onApplied(r);
        Sleep(100);
    }
}

} // namespace

void start(bool buildOk, const std::string& why, const std::string& applyWhy) {
    g_buildOk = buildOk;
    g_why = why;
    g_applyWhy = applyWhy;
    g_journalPath = mecap::log::dllFolder() + L"mec_ap_events.jsonl";
    g_ackedPath = mecap::log::dllFolder() + L"mec_ap_acked.txt";
    loadState();
    CloseHandle(CreateThread(nullptr, 0, &run, nullptr, 0, nullptr));
}

} // namespace mecap::link
