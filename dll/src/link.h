#pragma once
// The link to the Python client: a journal of finished runs, and a localhost TCP socket.
//
// Protocol (one JSON object per line, UTF-8):
//   DLL -> client  {"ev":"hello","proto":1,"dll":"0.1.0","build_ok":true,"why":"","acked":N,"last":M}
//                  {"ev":"finished","seq":7,"time":1763000000,"content_id":"353ff992","run_cs":3026,
//                   "record_cs":2663,"delta_cs":363,"had_record":1,"new_record":0,"set":0}
//                  {"ev":"started","content_id":"353ff992"}   {"ev":"cancelled","content_id":"..."}
//                  {"ev":"applied","id":3,"hash":"67800619","value":1,"result":"applied","matched":1,
//                   "targets":1,"live":true}
//   client -> DLL  {"cmd":"ack","seq":7}
//                  {"cmd":"apply","id":3,"hash":"67800619","value":1}
//
// hello also carries "apply" (true when abilities can be applied now) and "apply_why". An apply
// result is one of: applied, already, no_flag, table_mismatch, no_entity, unsafe, failed, fault,
// disabled (apply.h). Apply requests and results are live only; nothing about them is journaled.
//
// Every finish gets a sequence number and is appended to mec_ap_events.jsonl before it is sent.
// The highest sequence the client has acknowledged is kept in mec_ap_acked.txt. On every
// connection the client is sent each finish after that, so a run done while the client was not
// running is not lost. Started / cancelled are live only.

#include <string>

namespace mecap::link {

constexpr unsigned short kPort = 47910; // 127.0.0.1 only
constexpr int kProtocol = 1;

// Starts the link thread. `buildOk` / `why` and whether applying is on are reported in every hello.
void start(bool buildOk, const std::string& why, const std::string& applyWhy);

} // namespace mecap::link
