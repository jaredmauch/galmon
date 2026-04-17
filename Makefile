#
GCCSTD = -std=gnu++23
CFLAGS = -O3 -Wall -ggdb -pedantic

CXXFLAGS:= $(GCCSTD) $(CFLAGS) -MMD -MP -fno-omit-frame-pointer -Iext/CLI11 \
	 -Iext/powerblog/ext/simplesocket -Iext/powerblog/ext/ \
	 -I/usr/local/opt/openssl/include/  \
	 -Iext/sgp4/libsgp4/ \
	 -I/usr/local/include

# CXXFLAGS += -Wno-delete-non-virtual-dtor

# If unset, create a variable for the path or binary to use as "install" for debuild.
INSTALL ?= install
# If unset, create a variable with the path used by "make install"
prefix ?= /usr/local/ubxtool
# If unset, create a variable for a path underneath $prefix that stores html files
htdocs ?= /share/package

ifneq (,$(wildcard ubxsec.c))
	EXTRADEP = ubxsec.o
else ifneq (,$(wildcard ubxsec.o))
	EXTRADEP = ubxsec.o
endif

CHEAT_ARG := $(shell ./update-git-hash-if-necessary)

PROGRAMS = navparse ubxtool navnexus navcat navrecv navdump testrunner navdisplay tlecatch reporter sp3feed \
	galmonmon rinreport rinjoin rtcmtool gndate septool navmerge

all: navmon.pb.cc $(PROGRAMS)

-include Makefile.local

-include *.d

navmon.pb.h: navmon.proto
	protoc --cpp_out=./ navmon.proto

navmon.pb.cc: navmon.proto
	protoc --cpp_out=./ navmon.proto


SIMPLESOCKETS=ext/powerblog/ext/simplesocket/swrappers.o ext/powerblog/ext/simplesocket/sclasses.o  ext/powerblog/ext/simplesocket/comboaddress.o 


clean:
	rm -f *~ *.o *.d ext/*/*.o ext/*/*.d $(PROGRAMS) navmon.pb.h navmon.pb.cc $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) $(SIMPLESOCKETS)
	rm -f ext/sgp4/libsgp4/*.d ext/powerblog/ext/simplesocket/*.d
	rm -f *.gcov *.gcda *.gcno

help2man:
	$(INSTALL) -m 755 -d $(DESTDIR)$(prefix)/share/man/man1
	@set -e; \
	HELP2MAN_DESCRIPTION="Open-source GNSS Monitoring Project"; \
	for binaryfile in $(PROGRAMS); do \
		manbase="$(DESTDIR)$(prefix)/share/man/man1/$${binaryfile}.1"; \
		if ! help2man -N -n "$$HELP2MAN_DESCRIPTION" "./$${binaryfile}" > "$$manbase"; then \
			rm -f "$$manbase" "$$manbase.gz"; \
			echo "help2man failed for $${binaryfile}; ensure --help and --version work" >&2; \
			exit 1; \
		fi; \
		gzip -f "$$manbase"; \
	done

install: $(PROGRAMS) help2man
	$(INSTALL) -m 755 -d $(DESTDIR)$(prefix)/bin
	$(foreach binaryfile,$(PROGRAMS),$(INSTALL) -s -m 755 -D ./$(binaryfile) $(DESTDIR)$(prefix)/bin/$(binaryfile);)
	@echo "using cp instead of install because recursive directories of ascii"
	mkdir -p $(DESTDIR)$(prefix)$(htdocs)/galmon
	cp -a html $(DESTDIR)$(prefix)$(htdocs)/galmon/

download-debian-package:
	apt-key adv --fetch-keys https://ota.bike/public-package-signing-keys/86E7F51C04FBAAB0.asc
	echo "deb https://ota.bike/debian/ buster main" > /etc/apt/sources.list.d/galmon.list
	apt-get update && apt-get install -y galmon

download-raspbian-package:
	apt-key adv --fetch-keys https://ota.bike/public-package-signing-keys/86E7F51C04FBAAB0.asc
	echo "deb https://ota.bike/raspbian/ buster main" > /etc/apt/sources.list.d/galmon.list
	apt-get update && apt-get install -y galmon

decrypt: decrypt.o bits.o 
	$(CXX) $(GCCSTD) $^ -o $@  -lfmt

navparse: navparse.o $(SIMPLESOCKETS) minicurl.o ubx.o bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o navmon.o coverage.o osen.o trkmeas.o influxpush.o ${EXTRADEP} githash.o sbas.o rtcm.o galileo.o
	$(CXX) $(GCCSTD) $^ -o $@ -pthread -L/usr/local/lib -L/usr/local/opt/openssl/lib/ -lcpp-httplib -lssl -lcrypto -lz -lcurl -lprotobuf -lfmt

reporter: reporter.o  $(SIMPLESOCKETS) minicurl.o ubx.o bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o navmon.o coverage.o osen.o githash.o influxpush.o 
	$(CXX) $(GCCSTD) $^ -o $@ -pthread -L/usr/local/lib -lprotobuf -lcurl -lfmt

sp3feed: sp3feed.o  $(SIMPLESOCKETS) minicurl.o ubx.o bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o navmon.o coverage.o osen.o influxpush.o githash.o sp3.o
	$(CXX) $(GCCSTD) $^ -o $@ -pthread -L/usr/local/lib -lprotobuf -lcurl -lfmt


tracker: tracker.o  $(SIMPLESOCKETS) minicurl.o ubx.o bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o navmon.o coverage.o osen.o githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -pthread -L/usr/local/lib -lprotobuf -lcurl -lfmt


galmonmon: galmonmon.o  $(SIMPLESOCKETS) minicurl.o ubx.o bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o navmon.o coverage.o osen.o githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -pthread -L/usr/local/lib -lprotobuf -lcurl -lfmt


# rs.o fixhunter.o
navdump: navdump.o  bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o navmon.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) tle.o sp3.o osen.o trkmeas.o githash.o rinex.o sbas.o rtcm.o galileo.o  ${EXTRADEP}
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread  -lprotobuf -lz  -lfmt
# -lfec

navdisplay: navdisplay.o  bits.o navmon.pb.o gps.o ephemeris.o beidou.o glonass.o ephemeris.o navmon.o osen.o githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread  -lprotobuf -Wl,--as-needed -lncurses -lfmt


navnexus: navnexus.o   $(SIMPLESOCKETS) bits.o navmon.pb.o storage.o githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread -lprotobuf -lfmt

navcat: navcat.o   $(SIMPLESOCKETS) ubx.o bits.o navmon.pb.o storage.o navmon.o githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread -lprotobuf -lfmt


navrecv: navrecv.o  $(SIMPLESOCKETS) navmon.pb.o storage.o githash.o zstdwrap.o navmon.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread -lprotobuf -lzstd -lfmt 

navmerge: navmerge.o  $(SIMPLESOCKETS) navmon.pb.o storage.o githash.o zstdwrap.o navmon.o nmmsender.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread -lprotobuf -lzstd -lfmt 


tlecatch: tlecatch.o $(patsubst %.cc,%.o,$(wildcard ext/sgp4/libsgp4/*.cc)) githash.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -pthread -lprotobuf  

rinreport: rinreport.o rinex.o githash.o navmon.o   ephemeris.o osen.o
	$(CXX) $(GCCSTD) $^ -o $@ -lz -pthread -lfmt

rinjoin: rinjoin.o rinex.o githash.o navmon.o   ephemeris.o osen.o
	$(CXX) $(GCCSTD) $^ -o $@ -lz -pthread -lfmt


rtcmtool: rtcmtool.o navmon.pb.o githash.o   bits.o nmmsender.o $(SIMPLESOCKETS)  navmon.o rtcm.o zstdwrap.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -lz -pthread -lprotobuf -lzstd -lfmt


ubxtool: navmon.pb.o ubxtool.o ubx.o bits.o  galileo.o  gps.o beidou.o navmon.o ephemeris.o $(SIMPLESOCKETS) osen.o githash.o nmmsender.o zstdwrap.o 
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -lprotobuf -pthread -lzstd -lfmt 

septool: navmon.pb.o septool.o bits.o  galileo.o  gps.o beidou.o navmon.o ephemeris.o $(SIMPLESOCKETS) osen.o githash.o nmmsender.o zstdwrap.o 
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -lprotobuf -pthread -lzstd -lfmt	


testrunner: navmon.pb.o testrunner.o ubx.o bits.o  galileo.o  gps.o beidou.o glonass.o sbas.o ephemeris.o sp3.o osen.o navmon.o rinex.o githash.o influxpush.o minicurl.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -lprotobuf -lz  -pthread -lfmt -lcpp-httplib -lcurl

gndate: gndate.o githash.o  navmon.o
	$(CXX) $(GCCSTD) $^ -o $@ -L/usr/local/lib -lfmt

check: testrunner ubxtool navparse
	./testrunner
	python3 ./tools/ubxtool_safety_harness.py --iterations 10
	python3 ./tools/navparse_navdump_fixture_harness.py
	python3 ./tools/navparse_http_harness.py
	python3 ./tools/rtcmtool_septool_fixture_harness.py
	python3 ./tools/rinreport_rinjoin_fixture_harness.py
	python3 ./tools/nav_pipeline_fixture_harness.py
	python3 ./tools/sp3feed_fixture_harness.py

check-valgrind: testrunner ubxtool navparse navdump rtcmtool septool rinreport rinjoin
	@command -v valgrind >/dev/null 2>&1 || { echo "valgrind is required for check-valgrind"; exit 1; }
	valgrind --quiet --leak-check=full --show-leak-kinds=all --errors-for-leak-kinds=definite,possible,indirect --error-exitcode=99 ./testrunner
	python3 ./tools/apps_smoke_harness.py --valgrind
	python3 ./tools/ubxtool_safety_harness.py --iterations 10 --valgrind
	python3 ./tools/navparse_navdump_fixture_harness.py --valgrind
	python3 ./tools/rtcmtool_septool_fixture_harness.py --valgrind
	python3 ./tools/rinreport_rinjoin_fixture_harness.py --valgrind
	python3 ./tools/sp3feed_fixture_harness.py

ubxtool-safety-check: ubxtool
	python3 ./tools/ubxtool_safety_harness.py

ubxtool-safety-valgrind-check: ubxtool
	python3 ./tools/ubxtool_safety_harness.py --iterations 50 --valgrind

apps-smoke-check: $(PROGRAMS)
	python3 ./tools/apps_smoke_harness.py

apps-valgrind-check: $(PROGRAMS)
	@command -v valgrind >/dev/null 2>&1 || { echo "valgrind is required for apps-valgrind-check"; exit 1; }
	python3 ./tools/apps_smoke_harness.py --valgrind

navparse-navdump-fixture-check: navmon.pb.cc navparse navdump
	python3 ./tools/navparse_navdump_fixture_harness.py

navparse-http-check: navparse
	python3 ./tools/navparse_http_harness.py

rtcmtool-septool-fixture-check: navmon.pb.cc rtcmtool septool
	python3 ./tools/rtcmtool_septool_fixture_harness.py

rinreport-rinjoin-fixture-check: rinreport rinjoin
	python3 ./tools/rinreport_rinjoin_fixture_harness.py

nav-pipeline-fixture-check: navrecv navmerge navcat navnexus
	python3 ./tools/nav_pipeline_fixture_harness.py

sp3feed-fixture-check: sp3feed
	python3 ./tools/sp3feed_fixture_harness.py

coverage:
	$(MAKE) clean
	$(MAKE) GCCSTD="$(GCCSTD) --coverage" CFLAGS='-O0 -Wall -ggdb -pedantic' testrunner ubxtool
	./testrunner
	python3 ./tools/ubxtool_safety_harness.py --iterations 10
	python3 ./tools/coverage_report.py
