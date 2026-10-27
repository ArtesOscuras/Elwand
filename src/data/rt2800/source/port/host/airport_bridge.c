// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// No macOS Wi-Fi UI integration for MT7601U: the daemon uses a utun interface. Stubs keep daemon.c unchanged.
void airport_bridge_start(void) {}
void airport_assoc_failed(void) {}
void airport_bounce_link(void) {}
int airport_data_ready(void) { return 0; }
void airport_data_active(int on) {}
void airport_publish_start(const unsigned char mac[6]) {}
