#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN

#include "ext/doctest.h"
#include "ephemeris.hh"
#include "navmon.hh"
#include <atomic>
#include <chrono>
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
