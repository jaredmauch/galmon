#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN

#include "ext/doctest.h"
#include "ephemeris.hh"
#include "navmon.hh"

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
