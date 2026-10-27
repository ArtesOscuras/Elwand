#ifndef MLME_H
#define MLME_H
#include "mm.h"
#define MAX_BSS 128
struct bss_entry {
	u8 bssid[6];
	u32 freq;
	int chan;
	s8 signal;
	u16 capab, beacon_int;
	u64 tsf;
	char ssid[33];
	u8 ssid_len;
	bool rsn;
	bool akm_psk, akm_sae, mfpc, mfpr, h2e;
	u8 ies[1024];
	size_t ie_len;
	unsigned long seen;
};

struct sae_frame { u16 seq, status; size_t len; u8 data[160]; };
extern struct bss_entry bss_tab[MAX_BSS];
extern int g_prefer_sae;
extern int g_rx_debug;
extern int bss_n;

enum mlme_state { MLME_IDLE, MLME_AUTH, MLME_ASSOC, MLME_ASSOCIATED, MLME_CONNECTED };

struct mlme {
	enum mlme_state state;
	bool connected, secure, deauthed;
	char ssid[33];
	u8 ssid_len;
	struct ieee80211_channel *chan;
	struct ieee80211_sta *sta;
	u32 ap_basic_rates;
	u32 width;
	struct { u8 enc, nss, bw, gi; u16 idx; unsigned long n; } rx_rate;
	/* auth / assoc exchange */
	struct completion auth_done, assoc_done, eapol_done, eapol_tx_done;
	int auth_status, auth_seq;
	int assoc_status, assoc_aid;
	u16 assoc_capab;
	u8 assoc_resp_ies[1500];
	size_t assoc_resp_ies_len;
	u8 assoc_req_rsn[64];
	size_t assoc_req_rsn_len;
	u8 *assoc_req_ies;
	size_t assoc_req_ies_len;
	bool eapol_tx_wait, eapol_tx_acked;
	/* WPA3-Personal (SAE) */
	bool sae_mode;
	u8 sae_pmk[32], sae_pmkid[16];
	struct sae_frame sae_q[4];
	int sae_qn;
	void (*on_disconnect)(void);
};
extern struct mlme g_mlme;

const u8 *ie_find(const u8 *ies, size_t len, u8 id);
const u8 *ie_find_ext(const u8 *ies, size_t len, u8 ext_id);
void mlme_dump_bss(void);
void mlme_dump_bss_json(void);
void mlme_pcap_start(void);
void mlme_pcap_stop(void);
void mlme_lock(void);
void mlme_unlock(void);
int mlme_scan(const char *ssid);
int mlme_scan_quick(const char *ssid, int chan);
int mlme_connect(const char *ssid, const char *psk);
void mlme_set_authorized(void);
void mlme_disconnect(void);
int mlme_cur_info(char *bssid, size_t n, int *chan, int *signal);
bool mlme_tx_ba_ready(int tid);
void mlme_ba_start_tx(int tid);
void mlme_ba_reset(void);
void mlme_rx_rate_str(char *buf, size_t n);
void mlme_rsn_info(const char *ssid, char *out, size_t n);
void mlme_best_known(const char **ssids, int n, int *idx);
int mlme_tx_mgmt(struct sk_buff *skb);
void mlme_monitor_enable(const u8 *bssid);
void mlme_monitor_reset(void);
int mlme_monitor_best(u8 out[6], unsigned long *data_frames);
unsigned long mlme_monitor_data_frames(const u8 *mac);
u64 mlme_monitor_last_ms(const u8 *mac);
void mlme_monitor_dump(void);
int mlme_inject_deauth(const u8 *bssid, const u8 *client, int reason, int count);
void mlme_set_dtim_sync(int on);
int mlme_ping_client(const u8 *bssid, const u8 *client);
int mlme_inject_csa(const u8 *bssid, const u8 *client, int new_chan, int switch_count, int count);
int mlme_inject_csa_beacon(const u8 *bssid, int cur_chan, int new_chan, int switch_count, int count);
int mlme_set_channel(int channel);
unsigned long mlme_monitor_frames(const u8 *mac);
#endif
