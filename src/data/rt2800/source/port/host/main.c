// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// rtw89 userspace host for macOS.  usage: rtw89d scan | rtw89d connect <ssid> [--open]   (PSK from $RTW89_PSK or $RTW89_PSK_FILE)
#include "mm.h"
#include "mlme.h"
#include "datapath.h"
#include "net.h"
#include "daemon.h"
#include <linux/usb.h>
#include <signal.h>
#include <ctype.h>

extern void kc_runtime_init(void);
extern int kc_usb_find_and_probe(const struct usb_driver *drv);

static int tx_cb(const unsigned char *da, unsigned short ethertype, const unsigned char *payload, size_t len)
{
	if (!g_mlme.sta || g_mlme.state < MLME_ASSOCIATED) return -1;
	return dp_tx_frame(da, ethertype, payload, len, false);
}

static volatile int stop_flag;
static void on_sig(int s) { stop_flag = 1; }
static void on_disc(void) { fprintf(stderr, "[main] disconnected by AP\n"); stop_flag = 1; }

static char *read_psk(void)
{
	const char *e = getenv("RTW89_PSK");
	if (e) return strdup(e);
	const char *f = getenv("RTW89_PSK_FILE");
	if (f) {
		FILE *fp = fopen(f, "r");
		if (!fp) { perror(f); return NULL; }
		char buf[128] = {0};
		if (!fgets(buf, sizeof buf, fp)) { fclose(fp); return NULL; }
		fclose(fp);
		buf[strcspn(buf, "\r\n")] = 0;
		return strdup(buf);
	}
	return NULL;
}

static int parse_mac(const char *s, u8 out[6])
{
	unsigned v[6];
	if (sscanf(s, "%x:%x:%x:%x:%x:%x", &v[0], &v[1], &v[2], &v[3], &v[4], &v[5]) != 6) return -1;
	for (int i = 0; i < 6; i++) {
		if (v[i] > 0xff) return -1;
		out[i] = v[i];
	}
	return 0;
}

int main(int argc, char **argv)
{
	setvbuf(stdout, NULL, _IONBF, 0);
	if (argc < 2) { fprintf(stderr, "usage: %s daemon | scan [--json] | connect <ssid> [--open] | monitor <channel> [seconds] [bssid] [--pcap] [--hop] | deauth <channel> <bssid> <client> [count] [reason] | deauth-auto <channel> <bssid> [discover_secs] [count] | ping-client <channel> <bssid> <client> | csa <channel> <bssid> <new_channel> [client] [count] [switch_count] | csa-auto <channel> <bssid> <new_channel> [discover_secs] [count]\n", argv[0]); return 1; }
	if (!strcmp(argv[1], "daemon")) return daemon_main();
	{ extern int g_rx_debug; g_rx_debug = getenv("RTW89_RXDEBUG") != NULL; }
	kc_runtime_init();
	int ret = kc_usb_find_and_probe(kc_usb_driver_ptr);
	fprintf(stderr, "probe: %d\n", ret);
	if (ret) return 1;
	if (!g_mm || !g_mm->registered) { fprintf(stderr, "driver did not register (USB mode switch pending? run again)\n"); return 2; }
	bool monitor_cmd = !strcmp(argv[1], "monitor") || !strcmp(argv[1], "deauth") || !strcmp(argv[1], "deauth-auto") || !strcmp(argv[1], "ping-client") || !strcmp(argv[1], "csa") || !strcmp(argv[1], "csa-auto");
	int mon_ch = 0;
	if (monitor_cmd) {
		if (argc < 3) { fprintf(stderr, "channel required\n"); return 1; }
		mon_ch = atoi(argv[2]);
		if (mon_ch <= 0) { fprintf(stderr, "invalid channel\n"); return 1; }
	}
	ret = monitor_cmd ? mm_up_monitor(mon_ch) : mm_up();
	if (ret) { fprintf(stderr, "mm_up failed: %d\n", ret); return 3; }
	sleep(1);
	signal(SIGINT, on_sig); signal(SIGTERM, on_sig);

	if (!strcmp(argv[1], "scan")) {
		mlme_scan(NULL);
		if (argc >= 3 && !strcmp(argv[2], "--json")) mlme_dump_bss_json();
		else mlme_dump_bss();
	} else if (!strcmp(argv[1], "connect") && argc >= 3) {
		bool open = argc >= 4 && !strcmp(argv[3], "--open");
		char *psk = open ? NULL : read_psk();
		if (!open && !psk) { fprintf(stderr, "set RTW89_PSK or RTW89_PSK_FILE (or pass --open)\n"); mm_down(); return 4; }
		net_init(tx_cb, g_mm->vif->addr);
		g_mlme.on_disconnect = on_disc;
		mlme_scan(argv[2]);
		ret = mlme_connect(argv[2], psk);
		fprintf(stderr, "connect: %d\n", ret);
		if (!ret) {
			if (net_up(20, getenv("RTW89_SET_DEFAULT") != NULL) == 0) {
				fprintf(stderr, "[main] online. Ctrl-C to disconnect.\n");
				while (!stop_flag) sleep(1);
			}
			net_down();
			mlme_disconnect();
		}
	} else if (!strcmp(argv[1], "monitor") && argc >= 3) {
		int secs = 15;
		const char *bssid_s = NULL;
		bool pcap = false, hop = false;
		for (int i = 3; i < argc; i++) {
			if (!strcmp(argv[i], "--pcap")) pcap = true;
			else if (!strcmp(argv[i], "--hop")) hop = true;
			else if (strchr(argv[i], ':')) bssid_s = argv[i];
			else if (isdigit((unsigned char)argv[i][0])) secs = atoi(argv[i]);
		}
		u8 bssid[6];
		const u8 *bp = NULL;
		if (bssid_s) {
			if (parse_mac(bssid_s, bssid)) { fprintf(stderr, "invalid bssid\n"); mm_down(); return 5; }
			bp = bssid;
		}
		if (pcap) mlme_pcap_start();
		mlme_monitor_enable(bp);
		static const int hop_ch[] = {1,2,3,4,5,6,7,8,9,10,11,12,13,36,40,44,48,52,56,60,64,100,104,108,112,116,120,124,128,132,136,140,144,149,153,157,161,165};
		u64 end = secs > 0 ? kc_now_ms() + (u64)secs * 1000 : 0;
		int hi = 0;
		while (!stop_flag && (secs <= 0 || kc_now_ms() < end)) {
			if (hop) {
				mlme_set_channel(hop_ch[hi++ % (int)(sizeof(hop_ch) / sizeof(hop_ch[0]))]);
				usleep(600000);
			} else {
				sleep(1);
			}
		}
		if (pcap) mlme_pcap_stop();
		mlme_monitor_dump();
	} else if (!strcmp(argv[1], "deauth") && argc >= 5) {
		u8 bssid[6], client[6];
		if (parse_mac(argv[3], bssid) || parse_mac(argv[4], client)) { fprintf(stderr, "invalid bssid/client\n"); mm_down(); return 5; }
		int count = argc >= 6 ? atoi(argv[5]) : 16;
		int reason = argc >= 7 ? atoi(argv[6]) : 7;
		bool pcap = false, dtim = false;
		int cap_secs = 3;
		for (int i = 5; i < argc; i++) {
			if (!strcmp(argv[i], "--pcap")) pcap = true;
			else if (!strcmp(argv[i], "--dtim-sync")) dtim = true;
			else if (!strcmp(argv[i], "--capture-seconds") && i + 1 < argc) cap_secs = atoi(argv[++i]);
		}
		if (pcap) mlme_pcap_start();
		mlme_monitor_enable(bssid);
		sleep(1);
		mlme_set_dtim_sync(dtim);
		mlme_inject_deauth(bssid, client, reason, count);
		if (cap_secs > 0) sleep(cap_secs);
		if (pcap) mlme_pcap_stop();
		mlme_monitor_dump();
	} else if (!strcmp(argv[1], "deauth-auto") && argc >= 4) {
		u8 bssid[6];
		if (parse_mac(argv[3], bssid)) { fprintf(stderr, "invalid bssid\n"); mm_down(); return 5; }
		int discover = argc >= 5 ? atoi(argv[4]) : 8;
		int count = argc >= 6 ? atoi(argv[5]) : 16;
		mlme_monitor_enable(bssid);
		mlme_monitor_reset();
		fprintf(stderr, "[deauth-auto] waiting up to %d s for an active client...\n", discover);
		u8 client[6];
		unsigned long before = 0;
		for (int i = 0; i < discover * 10 && !stop_flag; i++) {
			usleep(100000);
			if (!mlme_monitor_best(client, &before)) break;
		}
		if (!before) {
			fprintf(stderr, "[deauth-auto] no associated client seen\n");
			mlme_monitor_dump();
		} else {
			fprintf(stderr, "[deauth-auto] target %02x:%02x:%02x:%02x:%02x:%02x data=%lu\n",
				client[0], client[1], client[2], client[3], client[4], client[5], before);
			mlme_inject_deauth(bssid, client, 7, count);
			sleep(5);
			unsigned long after = mlme_monitor_data_frames(client);
			u64 last = mlme_monitor_last_ms(client);
			fprintf(stderr, "[deauth-auto] data before=%lu after=%lu last=%llu ms ago\n",
				before, after, (unsigned long long)(last ? kc_now_ms() - last : 0));
			mlme_monitor_dump();
		}
	} else if (!strcmp(argv[1], "ping-client") && argc >= 5) {
		u8 bssid[6], client[6];
		if (parse_mac(argv[3], bssid) || parse_mac(argv[4], client)) { fprintf(stderr, "invalid bssid/client\n"); mm_down(); return 5; }
		mlme_monitor_enable(bssid);
		sleep(1);
		mlme_ping_client(bssid, client);
		sleep(2);
		mlme_monitor_dump();
	} else if (!strcmp(argv[1], "csa") && argc >= 5) {
		u8 bssid[6], client[6];
		if (parse_mac(argv[3], bssid)) { fprintf(stderr, "invalid bssid\n"); mm_down(); return 5; }
		int new_ch = atoi(argv[4]);
		const char *client_s = argc >= 6 ? argv[5] : "ff:ff:ff:ff:ff:ff";
		if (parse_mac(client_s, client)) { fprintf(stderr, "invalid client\n"); mm_down(); return 5; }
		int count = argc >= 7 ? atoi(argv[6]) : 16;
		int sw = argc >= 8 ? atoi(argv[7]) : 1;
		if (new_ch <= 0) { fprintf(stderr, "invalid new channel\n"); mm_down(); return 5; }
		bool action = getenv("RT_CSA_ACTION") != NULL;
		static const u8 bcast[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
		mlme_monitor_enable(bssid);
		sleep(1);
		if (action) {
			mlme_inject_csa(bssid, client, new_ch, sw, count);
		} else {
			mlme_inject_csa_beacon(bssid, atoi(argv[2]), new_ch, sw, count);
			if (memcmp(client, bcast, 6))
				mlme_inject_csa(bssid, client, new_ch, sw, count);
		}
		sleep(1);
		mlme_monitor_dump();
	} else if (!strcmp(argv[1], "csa-auto") && argc >= 5) {
		u8 bssid[6];
		if (parse_mac(argv[3], bssid)) { fprintf(stderr, "invalid bssid\n"); mm_down(); return 5; }
		int new_chan = atoi(argv[4]);
		int discover = argc >= 6 ? atoi(argv[5]) : 8;
		int count = argc >= 7 ? atoi(argv[6]) : 16;
		if (new_chan <= 0) { fprintf(stderr, "invalid new channel\n"); mm_down(); return 5; }
		mlme_monitor_enable(bssid);
		mlme_monitor_reset();
		fprintf(stderr, "[csa-auto] waiting up to %d s for an active client...\n", discover);
		u8 client[6];
		unsigned long before = 0;
		for (int i = 0; i < discover * 10 && !stop_flag; i++) {
			usleep(100000);
			if (!mlme_monitor_best(client, &before)) break;
		}
		if (!before) {
			fprintf(stderr, "[csa-auto] no associated client seen\n");
			mlme_monitor_dump();
		} else {
			fprintf(stderr, "[csa-auto] target %02x:%02x:%02x:%02x:%02x:%02x data=%lu -> channel %d\n",
				client[0], client[1], client[2], client[3], client[4], client[5], before, new_chan);
			if (getenv("RT_CSA_BEACON")) {
				sleep(1);
				mlme_inject_csa_beacon(bssid, atoi(argv[2]), new_chan, 1, count);
			} else {
				mlme_inject_csa(bssid, client, new_chan, 1, count);
			}
			mlme_set_channel(new_chan);
			mlme_monitor_enable(NULL);
			mlme_monitor_reset();
			fprintf(stderr, "[csa-auto] watching channel %d for the client...\n", new_chan);
			for (int i = 0; i < 10 && !stop_flag; i++) sleep(1);
			unsigned long seen = mlme_monitor_frames(client);
			fprintf(stderr, "[csa-auto] client frames on channel %d: %lu\n", new_chan, seen);
			mlme_monitor_dump();
		}
	}
	mm_down();
	{ extern void kc_usb_disconnect(const struct usb_driver *); extern void kc_usb_close(void);
	  kc_usb_disconnect(kc_usb_driver_ptr); kc_usb_close(); }	/* tear the driver down so the chip is left idle */
	return 0;
}
