"""Bounded, hermetic native tests for OPENHTPC HOME local-network badge.

Copyright 2026 Steve Dehanne
SPDX-License-Identifier: Apache-2.0

Part of the OPENHTPC project.
Original project by Steve Dehanne.

Compile the real probe implementation from vendor/flex-launcher/src/launcher.c
with a synthetic getifaddrs source and synthetic default-route selection.
No access to the host's networking stack, Internet, Fedora settings or UI.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "vendor/flex-launcher/src/launcher.c"


class HomeNetworkBadgeTests(unittest.TestCase):
    def test_c_probe_with_synthetic_network_topologies(self):
        if shutil.which("cc") is None:
            self.skipTest("native C compiler unavailable")
        source = SOURCE.read_text(encoding="utf-8")
        enum_start = source.index("typedef enum {\n    HOME_NETWORK_UNKNOWN")
        enum_end = source.index("} HomeNetworkStatus;", enum_start) + len("} HomeNetworkStatus;")
        probe_start = source.index("static bool home_is_virtual_interface(const char *name)\n{")
        probe_end = source.index("static void refresh_home_network_indicator(", probe_start)
        real_code = source[probe_start:probe_end]
        enum_code = source[enum_start:enum_end]
        harness = r"""
#define _DEFAULT_SOURCE
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <netinet/in.h>

""" + enum_code + r"""

static struct ifaddrs rows[8];
static struct sockaddr_in ips4[8];
static struct sockaddr_in6 ips6[8];
static int count = 0;
static bool simulate_failure = false;
static char preferred_route[64] = "";

static int fake_getifaddrs(struct ifaddrs **out) {
    if (simulate_failure) return -1;
    *out = count > 0 ? &rows[0] : NULL;
    return 0;
}
static void fake_freeifaddrs(struct ifaddrs *items) { (void)items; }
static void home_default_route_interface(char *out, size_t n) {
    snprintf(out, n, "%s", preferred_route);
}
#define getifaddrs fake_getifaddrs
#define freeifaddrs fake_freeifaddrs
""" + real_code + r"""

static void reset(void) {
    memset(rows, 0, sizeof(rows));
    memset(ips4, 0, sizeof(ips4));
    memset(ips6, 0, sizeof(ips6));
    count = 0;
    simulate_failure = false;
    preferred_route[0] = '\0';
}
static void add(const char *name, unsigned flags, int family, const char *addr) {
    if (count >= 8) abort();
    int i = count++;
    rows[i].ifa_name = (char *)name;
    rows[i].ifa_flags = flags;
    if (family == AF_INET) {
        ips4[i].sin_family = AF_INET;
        if (inet_pton(AF_INET, addr, &ips4[i].sin_addr) != 1) abort();
        rows[i].ifa_addr = (struct sockaddr *)&ips4[i];
    } else if (family == AF_INET6) {
        ips6[i].sin6_family = AF_INET6;
        if (inet_pton(AF_INET6, addr, &ips6[i].sin6_addr) != 1) abort();
        rows[i].ifa_addr = (struct sockaddr *)&ips6[i];
    }
    if (i > 0) rows[i-1].ifa_next = &rows[i];
}
static void check(int expected, const char *ip) {
    char result[48] = "not-cleared";
    int status = home_network_probe(result, sizeof(result));
    if (status != expected || strcmp(result, ip) != 0) {
        fprintf(stderr, "Expected %d / %s but got %d / %s\n", expected, ip, status, result);
        exit(2);
    }
}
int main(void) {
    reset(); simulate_failure = true;
    check(HOME_NETWORK_UNKNOWN, "");

    reset(); add("enp0s31f6", IFF_UP, AF_INET, "192.168.1.59");
    check(HOME_NETWORK_DISCONNECTED, "");

    reset(); add("enp0s31f6", IFF_UP | IFF_RUNNING, 0, "");
    check(HOME_NETWORK_UNKNOWN, "");

    reset(); add("enp0s31f6", IFF_UP | IFF_RUNNING, AF_INET, "192.168.1.59");
    check(HOME_NETWORK_CONNECTED, "192.168.1.59");

    reset(); add("lo", IFF_UP | IFF_RUNNING | IFF_LOOPBACK, AF_INET, "127.0.0.1");
    add("enp0s31f6", IFF_UP | IFF_RUNNING, AF_INET, "192.168.1.59");
    check(HOME_NETWORK_CONNECTED, "192.168.1.59");

    reset(); add("veth7", IFF_UP | IFF_RUNNING, AF_INET, "172.17.0.1");
    check(HOME_NETWORK_DISCONNECTED, "");

    reset(); add("enp0s31f6", IFF_UP | IFF_RUNNING, AF_INET, "169.254.2.3");
    check(HOME_NETWORK_UNKNOWN, "");

    reset(); add("wlp0s20f3", IFF_UP | IFF_RUNNING, AF_INET6, "fd12:3456::2");
    check(HOME_NETWORK_CONNECTED, "fd12:3456::2");

    reset(); add("wlp0s20f3", IFF_UP | IFF_RUNNING, AF_INET6, "fe80::2");
    check(HOME_NETWORK_UNKNOWN, "");

    reset(); add("enp0s31f6", IFF_UP | IFF_RUNNING, AF_INET, "192.168.1.99");
    add("wlp0s20f3", IFF_UP | IFF_RUNNING, AF_INET, "10.0.0.40");
    snprintf(preferred_route, sizeof(preferred_route), "%s", "wlp0s20f3");
    check(HOME_NETWORK_CONNECTED, "10.0.0.40");

    reset(); add("enp0s31f6", IFF_UP | IFF_RUNNING, AF_INET6, "fd12::1");
    add("wlp0s20f3", IFF_UP | IFF_RUNNING, AF_INET, "10.0.0.50");
    check(HOME_NETWORK_CONNECTED, "10.0.0.50");

    puts("11 native HOME network probe cases PASS");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="openhtpc-home-network-") as td:
            path = pathlib.Path(td)
            (path / "test_network.c").write_text(harness, encoding="utf-8")
            compile_run = subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 str(path / "test_network.c"), "-o", str(path / "test_network")],
                capture_output=True, text=True,
            )
            self.assertEqual(compile_run.returncode, 0, compile_run.stderr)
            run = subprocess.run([str(path / "test_network")], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("11 native HOME network probe cases PASS", run.stdout)

    def test_default_route_metric_selection_with_synthetic_kernel_table(self):
        """Compile the real read-only route parser against synthetic /proc/net/route."""
        if shutil.which("cc") is None:
            self.skipTest("native C compiler unavailable")
        source = SOURCE.read_text(encoding="utf-8")
        begin = source.index("/* Exclude container/tunnel interfaces")
        end = source.index("static HomeNetworkStatus home_network_probe(", begin)
        real_code = source[begin:end]
        harness = r"""
#define _DEFAULT_SOURCE
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static const char *routes;
static FILE *route_fopen(const char *path, const char *mode) {
    if (strcmp(path, "/proc/net/route") || strcmp(mode, "r")) abort();
    FILE *stream = tmpfile();
    if (stream == NULL) abort();
    if (routes != NULL && fputs(routes, stream) < 0) abort();
    rewind(stream);
    return stream;
}
#define fopen route_fopen
""" + real_code + r"""
static void expect_interface(const char *expected) {
    char result[64] = "must-be-cleared";
    home_default_route_interface(result, sizeof(result));
    if (strcmp(result, expected)) {
        fprintf(stderr, "Expected route %s but got %s\n", expected, result);
        exit(3);
    }
}
#define HEADER "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
int main(void) {
    routes = HEADER;
    expect_interface("");

    routes = HEADER
        "enp1s0 00000000 0101A8C0 0003 0 0 200 00000000 0 0 0\n"
        "wlp2s0 00000000 0101A8C0 0003 0 0 30 00000000 0 0 0\n";
    expect_interface("wlp2s0");

    routes = HEADER
        "wg0 00000000 0101A8C0 0003 0 0 1 00000000 0 0 0\n"
        "enp1s0 00000000 0101A8C0 0003 0 0 100 00000000 0 0 0\n";
    expect_interface("enp1s0");

    routes = HEADER
        "wlp2s0 00000000 0101A8C0 0003 0 0 100 00000000 0 0 0\n"
        "enp1s0 00000000 0101A8C0 0003 0 0 100 00000000 0 0 0\n";
    expect_interface("enp1s0");

    routes = HEADER
        "wlp2s0 00000000 0101A8C0 0000 0 0 1 00000000 0 0 0\n"
        "enp1s0 00000000 0101A8C0 0003 0 0 100 00000000 0 0 0\n";
    expect_interface("enp1s0");

    routes = HEADER
        "wlp2s0 00000000 0101A8C0 0003 0 0 1 0000FFFF 0 0 0\n"
        "enp1s0 00000000 0101A8C0 0003 0 0 100 00000000 0 0 0\n";
    expect_interface("enp1s0");

    routes = HEADER "enp1s0 00000000 0101A8C0 0003\n";
    expect_interface("");

    puts("7 native default-route parser cases PASS");
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="openhtpc-home-route-") as td:
            path = pathlib.Path(td)
            (path / "test_route.c").write_text(harness, encoding="utf-8")
            compiled = subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 str(path / "test_route.c"), "-o", str(path / "test_route")],
                capture_output=True, text=True,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            completed = subprocess.run(
                [str(path / "test_route")], capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("7 native default-route parser cases PASS", completed.stdout)

    def test_home_only_noninteractive_rendering_contract(self):
        s = SOURCE.read_text(encoding="utf-8")
        self.assertIn("if (!(state.application_running || state.application_launching) && is_home_menu())\n"
                      "            refresh_home_network_indicator();", s)
        body = s[s.index("static void draw_home_network_indicator(void)\n{"):
                 s.index("static void draw_activity_overlay(void)\n{")]
        self.assertIn("if (!is_home_menu() || !home_network_probed) return;", body)
        self.assertIn("if (activity_visible && activity_texture != NULL)", body)
        self.assertIn("SDL_RenderCopy(renderer, home_network_texture, NULL, &text);", body)
        self.assertLess(s.index("draw_home_network_indicator();\n        draw_activity_overlay();"),
                        s.index("        // Draw screensaver"))
        self.assertIn("SDL_DestroyTexture(home_network_texture)", s)


if __name__ == "__main__":
    unittest.main()
