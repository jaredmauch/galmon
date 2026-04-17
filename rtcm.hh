#pragma once
#include <string>
#include <stdio.h>
#include "navmon.hh"
#include <vector>
#include "galileo.hh"
#include <map>

struct RTCMFrame
{
  std::string payload;
};

class RTCMReader
{
public:
  explicit RTCMReader(int fd) : d_fp(fdopen(fd, "r")) {}
  ~RTCMReader()
  {
    if(d_fp) {
      fclose(d_fp);
      d_fp = nullptr;
    }
  }
  RTCMReader(const RTCMReader&) = delete;
  RTCMReader& operator=(const RTCMReader&) = delete;
  RTCMReader(RTCMReader&&) = delete;
  RTCMReader& operator=(RTCMReader&&) = delete;
  bool get(RTCMFrame& rf);
private:
  FILE* d_fp;
};


struct RTCMMessage
{
  void parse(const std::string& str);
  int type;
  int sow;
  int udi;
  bool mmi;
  bool reference;
  int ssrIOD, ssrProvider, ssrSolution;
  struct EphemerisDelta
  {
    SatID id;
    // in millimeters
    double radial, along, cross;   // mm
    double dradial, dalong, dcross; // mm/s
    int iod;
    int sow;
    int udi;
  };
  struct ClockDelta
  {
    SatID id;
    double dclock0; // in meters
    double dclock1;
    double dclock2;
    int sow;
    int udi;
    int iod{-1};
  };

  std::vector<EphemerisDelta> d_ephs;
  std::vector<ClockDelta> d_clocks;
  std::map<SatID, double> d_dcbs;
  GalileoMessage d_gm;
  int d_sv;
};
