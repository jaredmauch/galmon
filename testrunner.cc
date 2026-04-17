#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN

#include "ext/doctest.h"
#include "ephemeris.hh"
#include "glonass.hh"
#include "gps.hh"
#include "beidou.hh"
#include "sbas.hh"
#include "bits.hh"
#include "influxpush.hh"
#include "navmon.hh"
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <httplib.h>
#include <nlohmann/json.hpp>
#include <thread>

TEST_CASE("testing ephemeris age") {
    CHECK(ephAge(0,0) == 0);
    CHECK(ephAge(100,0) == 100);
    CHECK(ephAge(0,100) == -100);
    CHECK(ephAge(0,2*86400) == -2*86400);
    CHECK(ephAge(0,3*86400) == -3*86400);
    CHECK(ephAge(0, 3.49*86400) == -3.49*86400);    

    CHECK(ephAge(0, 3.51*86400) != -3.51*86400);
    CHECK(ephAge(0, 3.6*86400) != -3.6*86400);        


    CHECK(ephAge(2*86400, 0) == 2*86400);
    CHECK(ephAge(3*86400, 0) == 3*86400);    
    
    CHECK(ephAge(3.49*86400, 0) == 3.49*86400);        
}

#include "sp3.hh"
TEST_CASE("sp3") {
  SP3Reader sp3("./sp3/WUM0MGXULA_20192610100_01D_05M_ORB.SP3");
  SP3Entry e;
  CHECK(sp3.get(e));
  CHECK(e.gnss == 0);
  CHECK(e.sv == 1);
  CHECK(e.x ==-18824158.694000002  ) ;

  CHECK(sp3.get(e));
  CHECK(e.gnss == 0);
  CHECK(e.sv == 2);
  CHECK(e.clockBias == 1000.0 * -306.607761);
  
}

TEST_CASE("sp3 parses synthetic GPS and Galileo entries with unit conversion") {
  const char* path = "test_sp3_basic.sp3";
  {
    FILE* fp = fopen(path, "w");
    REQUIRE(fp != nullptr);
    fputs("*  2026  4 16 12 34 56.00000000\n", fp);
    fputs("PG12  12345.678901  -23456.789012   34567.890123    123.456789\n", fp);
    fputs("PE11  -1000.000000   2000.500000   -3000.250000    -10.000000\n", fp);
    fclose(fp);
  }

  SP3Reader sp3(path);
  SP3Entry e{};
  REQUIRE(sp3.get(e));
  CHECK(e.gnss == 0);
  CHECK(e.sv == 12);
  CHECK(e.x == doctest::Approx(12345.678901 * 1000.0));
  CHECK(e.y == doctest::Approx(-23456.789012 * 1000.0));
  CHECK(e.z == doctest::Approx(34567.890123 * 1000.0));
  CHECK(e.clockBias == doctest::Approx(123.456789 * 1000.0));

  struct tm tm{};
  tm.tm_year = 2026 - 1900;
  tm.tm_mon = 4 - 1;
  tm.tm_mday = 16;
  tm.tm_hour = 12;
  tm.tm_min = 34;
  tm.tm_sec = 56;
  CHECK(e.t == timegm(&tm) - 18);

  REQUIRE(sp3.get(e));
  CHECK(e.gnss == 2);
  CHECK(e.sv == 11);
  CHECK(e.x == doctest::Approx(-1000.0 * 1000.0));
  CHECK(e.y == doctest::Approx(2000.5 * 1000.0));
  CHECK(e.z == doctest::Approx(-3000.25 * 1000.0));
  CHECK(e.clockBias == doctest::Approx(-10.0 * 1000.0));

  CHECK_FALSE(sp3.get(e));
  remove(path);
}

TEST_CASE("sp3 skips unsupported constellations and keeps epoch for later records") {
  const char* path = "test_sp3_skip.sp3";
  {
    FILE* fp = fopen(path, "w");
    REQUIRE(fp != nullptr);
    fputs("*  2024  1  2  3  4  5.00000000\n", fp);
    fputs("PR01   1111.000000   2222.000000   3333.000000      1.000000\n", fp);
    fputs("PC07   4444.000000   5555.000000   6666.000000      2.500000\n", fp);
    fclose(fp);
  }

  SP3Reader sp3(path);
  SP3Entry e{};
  REQUIRE(sp3.get(e));
  CHECK(e.gnss == 3);
  CHECK(e.sv == 7);
  CHECK(e.x == doctest::Approx(4444.0 * 1000.0));
  CHECK(e.clockBias == doctest::Approx(2.5 * 1000.0));

  struct tm tm{};
  tm.tm_year = 2024 - 1900;
  tm.tm_mon = 1 - 1;
  tm.tm_mday = 2;
  tm.tm_hour = 3;
  tm.tm_min = 4;
  tm.tm_sec = 5;
  CHECK(e.t == timegm(&tm) - 18);

  CHECK_FALSE(sp3.get(e));
  remove(path);
}

#include "rinex.hh"
#include "ubx.hh"
TEST_CASE("rinex") {
  RINEXReader rinex("./rinex/PTGG00PHL_R_20193500000_01D_MN.rnx.gz");
  RINEXEntry e;
  REQUIRE(rinex.get(e));
  CHECK(e.gnss == 0);
  CHECK(e.sv == 2 );
  CHECK(e.sisa==2 ) ;

  REQUIRE(rinex.get(e));
  CHECK(e.gnss == 0);
  CHECK(e.sv == 5);
  CHECK(e.sisa==2.0);

  RINEXNavWriter rnw("test.rnx");
}


TEST_CASE("truncation") {
  CHECK(truncPrec(123.0, 0) == 123.0);
  CHECK(truncPrec(123.123, 1) == 123.1);
  CHECK(truncPrec(123.123, 2) == 123.12);
  CHECK(truncPrec(123.123, 3) == 123.123);
  CHECK(truncPrec(123.191, 1) == 123.2);
  CHECK(truncPrec(123.191, 2) == 123.19);
  CHECK(truncPrec(123.999, 0) == 124.0);
  
  
}

TEST_CASE("ubx message framing and checksum") {
  std::vector<uint8_t> payload{0x10, 0x20, 0x30, 0x40};
  auto msg = buildUbxMessage(0x01, 0x07, payload);

  REQUIRE(msg.size() == payload.size() + 8);
  CHECK(msg[0] == 0xB5);
  CHECK(msg[1] == 0x62);
  CHECK(msg[2] == 0x01);
  CHECK(msg[3] == 0x07);
  CHECK(msg[4] == payload.size());
  CHECK(msg[5] == 0x00);

  std::vector<uint8_t> extracted{msg.begin() + 6, msg.end() - 2};
  CHECK(extracted == payload);

  uint16_t checksum = calcUbxChecksum(msg[2], msg[3], extracted);
  CHECK((checksum & 0xFF) == msg[msg.size() - 2]);
  CHECK((checksum >> 8) == msg[msg.size() - 1]);
}

TEST_CASE("ubx empty payload framing") {
  auto msg = buildUbxMessage(0x06, 0x01, {});
  REQUIRE(msg.size() == 8);
  CHECK(msg[0] == 0xB5);
  CHECK(msg[1] == 0x62);
  CHECK(msg[2] == 0x06);
  CHECK(msg[3] == 0x01);
  CHECK(msg[4] == 0x00);
  CHECK(msg[5] == 0x00);

  std::vector<uint8_t> empty_payload;
  uint16_t checksum = calcUbxChecksum(msg[2], msg[3], empty_payload);
  CHECK((checksum & 0xFF) == msg[6]);
  CHECK((checksum >> 8) == msg[7]);
}

TEST_CASE("httplib client server integration on high port") {
  httplib::Server server;
  server.Get("/health", [](const httplib::Request&, httplib::Response& res) {
    res.set_content("ok", "text/plain");
    res.status = 200;
  });

  auto port = server.bind_to_any_port("127.0.0.1");
  REQUIRE(port > 1024);

  std::atomic<bool> listening{false};
  std::thread serverThread([&]() {
    listening = true;
    server.listen_after_bind();
  });

  while (!listening) {
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }

  httplib::Client client("127.0.0.1", port);
  client.set_connection_timeout(1, 0);
  client.set_read_timeout(1, 0);
  client.set_write_timeout(1, 0);

  auto response = client.Get("/health");
  for (int attempt = 0; attempt < 20 && !response; ++attempt) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
    response = client.Get("/health");
  }

  REQUIRE(response);
  CHECK(response->status == 200);
  CHECK(response->body == "ok");

  server.stop();
  serverThread.join();
}

TEST_CASE("httplib detailed checks for navparse-style URL codepaths") {
  httplib::Server server;
  auto set_json = [](httplib::Response& res, const nlohmann::json& body) {
    res.set_content(body.dump(), "application/json");
    res.status = 200;
  };

  server.Get("/global.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "global"}, {"method", req.method}, {"ok", true}});
  });
  server.Post("/global.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "global"}, {"method", req.method}, {"ok", true}});
  });

  server.Get("/almanac.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "almanac"}, {"method", req.method}, {"entries", nlohmann::json::array()}});
  });
  server.Post("/almanac.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "almanac"}, {"method", req.method}, {"entries", nlohmann::json::array()}});
  });

  server.Get("/observers.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "observers"}, {"method", req.method}, {"observers", nlohmann::json::array()}});
  });
  server.Post("/observers.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "observers"}, {"method", req.method}, {"observers", nlohmann::json::array()}});
  });

  server.Get("/sv.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res,
             {{"endpoint", "sv"},
              {"method", req.method},
              {"sv", req.get_param_value("sv")},
              {"gnssid", req.get_param_value("gnssid")},
              {"sigid", req.has_param("sigid") ? req.get_param_value("sigid") : "1"}});
  });
  server.Post("/sv.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res,
             {{"endpoint", "sv"},
              {"method", req.method},
              {"sv", req.get_param_value("sv")},
              {"gnssid", req.get_param_value("gnssid")},
              {"sigid", req.has_param("sigid") ? req.get_param_value("sigid") : "1"}});
  });

  server.Get("/cov.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res,
             {{"endpoint", "cov"},
              {"method", req.method},
              {"gps", req.has_param("gps") ? req.get_param_value("gps") : "0"},
              {"galileo", req.has_param("galileo") ? req.get_param_value("galileo") : "1"},
              {"beidou", req.has_param("beidou") ? req.get_param_value("beidou") : "0"},
              {"glonass", req.has_param("glonass") ? req.get_param_value("glonass") : "0"}});
  });
  server.Post("/cov.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res,
             {{"endpoint", "cov"},
              {"method", req.method},
              {"gps", req.has_param("gps") ? req.get_param_value("gps") : "0"},
              {"galileo", req.has_param("galileo") ? req.get_param_value("galileo") : "1"},
              {"beidou", req.has_param("beidou") ? req.get_param_value("beidou") : "0"},
              {"glonass", req.has_param("glonass") ? req.get_param_value("glonass") : "0"}});
  });

  server.Get("/sbas.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "sbas"}, {"method", req.method}, {"status", nlohmann::json::object()}});
  });
  server.Post("/sbas.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "sbas"}, {"method", req.method}, {"status", nlohmann::json::object()}});
  });

  server.Get("/svs.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "svs"}, {"method", req.method}, {"svs", nlohmann::json::object()}});
  });
  server.Post("/svs.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "svs"}, {"method", req.method}, {"svs", nlohmann::json::object()}});
  });

  server.Get("/sbstatus.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "sbstatus"}, {"method", req.method}, {"entries", nlohmann::json::array()}});
  });
  server.Post("/sbstatus.json", [&](const httplib::Request& req, httplib::Response& res) {
    set_json(res, {{"endpoint", "sbstatus"}, {"method", req.method}, {"entries", nlohmann::json::array()}});
  });

  auto port = server.bind_to_any_port("127.0.0.1");
  REQUIRE(port > 1024);
  std::thread serverThread([&]() { server.listen_after_bind(); });

  httplib::Client client("127.0.0.1", port);
  client.set_connection_timeout(1, 0);
  client.set_read_timeout(1, 0);
  client.set_write_timeout(1, 0);

  auto callAndCheck = [&](const std::string& method,
                          const std::string& path,
                          const std::string& endpoint,
                          const std::function<void(const nlohmann::json&)>& verify) {
    httplib::Result response;
    for (int attempt = 0; attempt < 20 && !response; ++attempt) {
      if (method == "GET") {
        response = client.Get(path.c_str());
      }
      else {
        response = client.Post(path.c_str(), "", "text/plain");
      }
      if (!response) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
    }
    REQUIRE(response);
    CHECK(response->status == 200);
    CHECK(response->get_header_value("Content-Type").find("application/json") != std::string::npos);
    auto parsed = nlohmann::json::parse(response->body);
    CHECK(parsed.at("endpoint").get<std::string>() == endpoint);
    CHECK(parsed.at("method").get<std::string>() == method);
    verify(parsed);
  };

  callAndCheck("GET", "/global.json", "global", [&](const nlohmann::json& parsed) { CHECK(parsed.at("ok").get<bool>()); });
  callAndCheck("POST", "/global.json", "global", [&](const nlohmann::json& parsed) { CHECK(parsed.at("ok").get<bool>()); });

  callAndCheck("GET", "/almanac.json", "almanac", [&](const nlohmann::json& parsed) { CHECK(parsed.at("entries").is_array()); });
  callAndCheck("POST", "/almanac.json", "almanac", [&](const nlohmann::json& parsed) { CHECK(parsed.at("entries").is_array()); });

  callAndCheck("GET", "/observers.json", "observers", [&](const nlohmann::json& parsed) { CHECK(parsed.at("observers").is_array()); });
  callAndCheck("POST", "/observers.json", "observers", [&](const nlohmann::json& parsed) { CHECK(parsed.at("observers").is_array()); });

  callAndCheck("GET", "/sv.json?sv=12&gnssid=2&sigid=5", "sv", [&](const nlohmann::json& parsed) {
    CHECK(parsed.at("sv").get<std::string>() == "12");
    CHECK(parsed.at("gnssid").get<std::string>() == "2");
    CHECK(parsed.at("sigid").get<std::string>() == "5");
  });
  callAndCheck("POST", "/sv.json?sv=12&gnssid=2", "sv", [&](const nlohmann::json& parsed) {
    CHECK(parsed.at("sv").get<std::string>() == "12");
    CHECK(parsed.at("gnssid").get<std::string>() == "2");
    CHECK(parsed.at("sigid").get<std::string>() == "1");
  });

  callAndCheck("GET", "/cov.json?gps=1&galileo=0&beidou=1&glonass=1", "cov", [&](const nlohmann::json& parsed) {
    CHECK(parsed.at("gps").get<std::string>() == "1");
    CHECK(parsed.at("galileo").get<std::string>() == "0");
    CHECK(parsed.at("beidou").get<std::string>() == "1");
    CHECK(parsed.at("glonass").get<std::string>() == "1");
  });
  callAndCheck("POST", "/cov.json", "cov", [&](const nlohmann::json& parsed) {
    CHECK(parsed.at("gps").get<std::string>() == "0");
    CHECK(parsed.at("galileo").get<std::string>() == "1");
    CHECK(parsed.at("beidou").get<std::string>() == "0");
    CHECK(parsed.at("glonass").get<std::string>() == "0");
  });

  callAndCheck("GET", "/sbas.json", "sbas", [&](const nlohmann::json& parsed) { CHECK(parsed.at("status").is_object()); });
  callAndCheck("POST", "/sbas.json", "sbas", [&](const nlohmann::json& parsed) { CHECK(parsed.at("status").is_object()); });

  callAndCheck("GET", "/svs.json", "svs", [&](const nlohmann::json& parsed) { CHECK(parsed.at("svs").is_object()); });
  callAndCheck("POST", "/svs.json", "svs", [&](const nlohmann::json& parsed) { CHECK(parsed.at("svs").is_object()); });

  callAndCheck("GET", "/sbstatus.json", "sbstatus", [&](const nlohmann::json& parsed) { CHECK(parsed.at("entries").is_array()); });
  callAndCheck("POST", "/sbstatus.json", "sbstatus", [&](const nlohmann::json& parsed) { CHECK(parsed.at("entries").is_array()); });

  server.stop();
  serverThread.join();
}

TEST_CASE("influx pusher formats line protocol and deduplicates") {
  InfluxPusher idb("testdb");
  idb.d_lastsent = time(0);

  SatID id{2, 12, 5};
  idb.addValue(id, "clock", {{"offset_ns", 12.5}, {"jump", int32_t(3)}, {"note", string("ok")}}, 1234.5, 7);

  REQUIRE(idb.d_buffer.size() == 1);
  const auto line = *idb.d_buffer.begin();
  CHECK(line.find("clock,sv=12,gnssid=2,sigid=5,src=7 ") == 0);
  CHECK(line.find("offset_ns=12.500000") != string::npos);
  CHECK(line.find("jump=3i") != string::npos);
  CHECK(line.find("note=\"ok\"") != string::npos);
  CHECK(line.find(" 1234500000000\n") != string::npos);

  idb.addValue(id, "clock", {{"offset_ns", 12.5}, {"jump", int32_t(3)}, {"note", string("ok")}}, 1234.5, 7);
  CHECK(idb.d_buffer.size() == 1);
  CHECK(idb.d_numdedupmsmts == 1);

  // Avoid network in destructor.
  idb.d_dbname = "null";
}

TEST_CASE("influx pusher rejects invalid values and supports mute mode") {
  InfluxPusher active("testdb");
  active.d_lastsent = time(0);
  SatID id{0, 1, 0};

  active.addValue(id, "clock", {{"offset_ns", std::numeric_limits<double>::quiet_NaN()}}, 1.0);
  CHECK(active.d_buffer.empty());

  active.addValue(id, "clock", {{"offset_ns", 1.0}}, -1.0);
  CHECK(active.d_buffer.empty());

  active.addValueObserver(9, "fix", {{"acc", 1.0}}, 2200000001.0);
  CHECK(active.d_buffer.empty());

  InfluxPusher muted("null");
  muted.d_lastsent = time(0);
  muted.addValue(id, "clock", {{"offset_ns", 1.0}}, 2.0);
  muted.addValueObserver(9, "fix", {{"acc", 1.0}}, 2.0);
  CHECK(muted.d_buffer.empty());

  active.d_dbname = "null";
}

TEST_CASE("glonass Tb maps to UTC quarter-hour slots") {
  struct tm tm{};
  tm.tm_year = 2026 - 1900;
  tm.tm_mon = 3;
  tm.tm_mday = 16;
  tm.tm_hour = 10;
  tm.tm_min = 0;
  tm.tm_sec = 0;
  const time_t reference = timegm(&tm);

  const auto mk = [](int y, int mon, int d, int h, int m, int s) {
    struct tm t{};
    t.tm_year = y - 1900;
    t.tm_mon = mon - 1;
    t.tm_mday = d;
    t.tm_hour = h;
    t.tm_min = m;
    t.tm_sec = s;
    return timegm(&t);
  };

  CHECK(getGlonassT0e(reference, 0) == mk(2026, 4, 15, 21, 0, 0));
  CHECK(getGlonassT0e(reference, 4) == mk(2026, 4, 15, 22, 0, 0));
  CHECK(getGlonassT0e(reference, 95) == mk(2026, 4, 16, 20, 45, 0));
}

TEST_CASE("glonass epoch time increases consistently") {
  GlonassMessage gm{};
  gm.n4 = 8;
  gm.NT = 100;
  gm.hour = 12;
  gm.minute = 34;
  gm.seconds = 30;
  const auto base = gm.getGloTime();

  gm.seconds = 31;
  CHECK(gm.getGloTime() == base + 1);
  gm.seconds = 30;
  gm.minute = 35;
  CHECK(gm.getGloTime() == base + 60);
  gm.minute = 34;
  gm.NT = 101;
  CHECK(gm.getGloTime() == base + 86400);
}

TEST_CASE("glonass coordinate propagation returns finite position") {
  GlonassMessage gm{};
  gm.n4 = 8;
  gm.NT = 120;
  gm.hour = 6;
  gm.minute = 0;
  gm.seconds = 0;
  gm.Tb = 24;
  gm.x = 32000000;
  gm.y = -21000000;
  gm.z = 18000000;
  gm.dx = 1200;
  gm.dy = -900;
  gm.dz = 700;
  gm.ddx = 0;
  gm.ddy = 0;
  gm.ddz = 0;

  const uint32_t glotime = gm.getGloTime();
  const uint32_t gloT0e = getGlonassT0e(glotime + 820368000, gm.Tb);
  const uint32_t ephtow = (gloT0e - 820368000) % (7 * 86400);

  Point p;
  getCoordinates(ephtow + 60, gm, &p);
  CHECK(std::isfinite(p.x));
  CHECK(std::isfinite(p.y));
  CHECK(std::isfinite(p.z));
  CHECK((fabs(p.x) + fabs(p.y) + fabs(p.z)) > 1.0);
}

TEST_CASE("beidou getT0e scaling uses 8*(MSB<<15 + LSB)") {
  BeidouMessage bm{};
  bm.t0eMSB = 3;
  bm.t0eLSB = 17;
  CHECK(bm.getT0e() == 8 * ((3u << 15) + 17u));
}

TEST_CASE("beidou atomic offset is zero trend when a1=a2=0 and Sow==T0c") {
  BeidouMessage bm{};
  // Ensure ephAge(Sow, getT0c()) == 0 so delta terms vanish.
  bm.t0c = 1;          // getT0c() == 8
  bm.sow = 8;
  bm.a0 = 123456;
  bm.a1 = 0;
  bm.a2 = 0;

  auto off = bm.getAtomicOffset();
  const double factor = ldexp(1000000000.0, -33);
  CHECK(std::abs(off.first - factor * 123456.0) < 1e-6);
  CHECK(std::abs(off.second) < 1e-12);
}

TEST_CASE("beidou UTC offset scales with a0utc and a1utc") {
  BeidouMessage bm{};
  bm.a0utc = 10; // in units of 2^-30 seconds before multiplying by factor
  bm.a1utc = 0;

  auto off = bm.getUTCOffset(12345);
  const double factor = ldexp(1000000000.0, -30);
  CHECK(std::abs(off.first - factor * 10.0) < 1e-6);
  CHECK(std::abs(off.second) < 1e-12);
}

TEST_CASE("beidou coordinate propagation returns finite position") {
  BeidouMessage bm{};

  // Minimal synthetic ephemeris values. The goal is to verify that the
  // propagation math produces finite coordinates (not to validate ICD accuracy).
  bm.sqrtA = 2701000000u; // ~5153 after ldexp(-19)
  bm.e = 86000000u;      // ~0.01 after ldexp(-33)
  bm.deltan = 0;
  bm.t0eMSB = 0;
  bm.t0eLSB = 1;          // t0e == 8 seconds

  bm.m0 = 1;
  bm.omega = 0;
  bm.omegadot = 0;
  bm.Omega0 = 0;
  bm.idot = 0;
  bm.i0 = 1;              // tiny inclination is fine for finiteness testing

  bm.cuc = 0;
  bm.cus = 0;
  bm.crc = 0;
  bm.crs = 0;
  bm.cic = 0;
  bm.cis = 0;

  Point p;
  getCoordinates(200.0, bm, &p, true);
  CHECK(std::isfinite(p.x));
  CHECK(std::isfinite(p.y));
  CHECK(std::isfinite(p.z));
  CHECK((fabs(p.x) + fabs(p.y) + fabs(p.z)) > 1.0);
}

TEST_CASE("gps utc<->week/tow conversion round-trips for integer inputs") {
  const int wn = 2000;
  const int tow = 123456;

  const time_t utc = (time_t)utcFromGPS(wn, (double)tow);
  int wn2 = -1;
  int tow2 = -1;
  getGPSDateFromUTC(utc, wn2, tow2);

  CHECK(wn2 == wn);
  CHECK(tow2 == tow);
}

TEST_CASE("gps atomic offset is af0/af1 scaled when delta=0") {
  GPSState eph{};
  eph.t0c = 10; // getT0c(eph) = t0c * 16 = 160
  const int tow = 160;

  eph.af0 = 123.0;
  eph.af1 = 456.0;
  // af2 is only used when delta != 0; keep in int8_t range to avoid warnings.
  eph.af2 = 2;

  auto off = getGPSAtomicOffset(tow, eph);
  const double factor = ldexp(1000000000.0, -31);

  // delta=0 => cur=af0, trend=ldexp(af1,-12)
  CHECK(std::abs(off.first - factor * eph.af0) < 1e-6);
  CHECK(std::abs(off.second - factor * ldexp(eph.af1, -12)) < 1e-6);
}

TEST_CASE("gps UTC offset scales with a0/a1 when delta=0") {
  GPSState eph{};
  const int wn = 10;
  eph.wn0t = 10;   // dw=0
  eph.t0t = 1000;  // delta=tow - t0t

  eph.a0 = 77;
  eph.a1 = 88; // trend uses ldexp(a1, -20)

  const int tow = 1000;
  auto off = getGPSUTCOffset(tow, wn, eph);
  const double factor = ldexp(1000000000.0, -30);

  CHECK(std::abs(off.first - factor * (double)eph.a0) < 1e-6);
  CHECK(std::abs(off.second - factor * ldexp((double)eph.a1, -20)) < 1e-6);
}

TEST_CASE("gps coordinate propagation returns finite position") {
  GPSState eph{};
  eph.t0e = 100000;
  eph.deltan = 0;

  // Use values that yield reasonable orbit parameters for finiteness testing.
  eph.sqrtA = 2701000000u; // => ldexp(sqrtA,-19) ~ 5153
  eph.e = 86000000u;       // => ldexp(e,-33) ~ 0.01

  eph.m0 = 1;
  eph.omega0 = 1;
  eph.i0 = 1;
  eph.omega = 1;
  eph.idot = 0;
  eph.omegadot = 0;

  eph.cuc = 0;
  eph.cus = 0;
  eph.crc = 0;
  eph.crs = 0;
  eph.cic = 0;
  eph.cis = 0;

  Point p;
  // Keep tow close to t0e to avoid extreme ages.
  getCoordinates((double)eph.t0e + 60.0, eph, &p, true);

  CHECK(std::isfinite(p.x));
  CHECK(std::isfinite(p.y));
  CHECK(std::isfinite(p.z));
  CHECK((fabs(p.x) + fabs(p.y) + fabs(p.z)) > 1.0);
}

TEST_CASE("sbas parse1 builds slot->PRN mapping and filters PRNs >=37") {
  SBASState st;
  const time_t now = time(0);

  std::vector<uint8_t> msg(32, 0);
  // parse1: d_slot2prn[slot]=prn+1 for bits at position 14+prn when set.
  // Set PRNs: 0,1,2 => slots 1,2,3 mapping to prn+1 => 1,2,3
  setbitu(msg.data(), 14 + 0, 1, 1);
  setbitu(msg.data(), 14 + 1, 1, 1);
  setbitu(msg.data(), 14 + 2, 1, 1);
  // Add PRN 37 => next slot would map to prn+1=38 which should be filtered to -1 for SBASNumber.
  setbitu(msg.data(), 14 + 37, 1, 1);

  st.parse1(msg, now);

  CHECK(st.getSBASNumber(1) == 1);
  CHECK(st.getSBASNumber(2) == 2);
  CHECK(st.getSBASNumber(3) == 3);
  CHECK(st.getSBASNumber(4) == -1);

  auto sid = st.getSBASSatID(4);
  CHECK(sid.gnss == 255); // filtered out
}

TEST_CASE("sbas parse2_5 + parse6 produce coherent fast corrections for mapped slots") {
  SBASState st;
  const time_t now = 1000;
  std::vector<uint8_t> msgMap(32, 0);

  // parse1 uses PRN mask bits at position 14+prn (len=1) to build slot->(prn+1).
  // Make parse1 create slot mappings for slots 1..13 (PRNs 0..12 => prn+1=1..13).
  for(int prn = 0; prn <= 12; ++prn) {
    setbitu(msgMap.data(), 14 + prn, 1, 1);
  }

  st.parse1(msgMap, now);

  // Ensure our synthesized parse1 message creates the expected mapping:
  // for PRNs 0..12 (set at positions 14+prn), parse1 creates slot2prn such that
  // slot i maps to prn=i-1 => SBAS sv=i.
  REQUIRE(st.d_slot2prn.size() == 13);
  for(int slot = 1; slot <= 13; ++slot) {
    REQUIRE(st.d_slot2prn.count(slot) == 1);
    CHECK(st.d_slot2prn[slot] == slot);
    auto sid = st.getSBASSatID(slot);
    CHECK(sid.gnss == 0);
    CHECK(sid.sv == (uint32_t)slot);
  }

  // parse2_5/parse6 read correction/udrei fields from a different SBAS frame layout,
  // so use a separate buffer to avoid overwriting the PRN mask region.
  std::vector<uint8_t> msgData(32, 0);

  // parse2_5: type = getbitu(pos=8,len=6) in range [2..5]
  setbitu(msgData.data(), 8, 6, 2);

  // parse2_5 correction raw bits at: 14 + 4 + 12*pos, len=12
  // We set raw correction = pos+1 => correction = (pos+1)*0.125
  for(int pos = 0; pos < 13; ++pos) {
    setbitu(msgData.data(), 14 + 4 + 12*pos, 12, (unsigned)(pos + 1));
    // parse2_5 udrei raw bits at: 14 + 4 + 12*13 + 4*pos, len=4
    setbitu(msgData.data(), 14 + 4 + 12*13 + 4*pos, 4, (unsigned)(pos + 1));
  }

  auto fast13 = st.parse2_5(msgData, now);
  REQUIRE(fast13.size() == 13);

  for(int pos = 0; pos < 13; ++pos) {
    const int slot = 1 + pos; // type==2 => slot = 1+pos
    CHECK(fast13[pos].id.sv == (unsigned)slot);
    CHECK(fast13[pos].udrei == pos + 1);
    CHECK(std::abs(fast13[pos].correction - (pos + 1) * 0.125) < 1e-12);
  }

  // parse6 updates udrei only.
  // parse6: fc.udrei at 14 + 8 + 4*slot, where slot iterates 0..50, but only slots that exist in d_fast matter.
  // Since our d_fast contains ids for slots 1..13, only slots 0..12 will be returned.
  for(int slot = 0; slot < 13; ++slot) {
    setbitu(msgData.data(), 14 + 8 + 4*slot, 4, (unsigned)(15 - slot)); // deterministic 0..15 values
  }

  auto fast13_updated = st.parse6(msgData, now + 10);
  REQUIRE(fast13_updated.size() == 13);

  for(int pos = 0; pos < 13; ++pos) {
    const int slot = 1 + pos;
    CHECK(fast13_updated[pos].id.sv == (unsigned)slot);
    CHECK(fast13_updated[pos].udrei == 15 - pos);
    CHECK(std::abs(fast13_updated[pos].correction - (pos + 1) * 0.125) < 1e-12);
  }
}

TEST_CASE("sbas parse7 records latency from fixed bit-field") {
  SBASState st;
  const time_t now = 1000;
  std::vector<uint8_t> msg(8, 0);
  // parse7: d_latency = getbitu(pos=14+4,len=4)
  setbitu(msg.data(), 14 + 4, 4, 7);
  st.parse7(msg, now);
  CHECK(st.d_latency == 7);
}
