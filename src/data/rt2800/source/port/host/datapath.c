// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// 802.11 data frame construction (Ethernet -> QoS data + CCMP header + LLC/SNAP) and key installation towards the driver.
#include <time.h>
#include <stdlib.h>
#include "mm.h"
#include "mlme.h"
#include "datapath.h"
#include "mlme.h"

struct ieee80211_key_conf *dp_ptk;
struct ieee80211_key_conf *dp_gtk[4];

int dp_install_key(const u8 *key, int keylen, int keyidx, bool pairwise, struct ieee80211_sta *sta)
{
	struct mm *m = g_mm;
	struct ieee80211_key_conf *k = calloc(1, sizeof(*k) + keylen);
	k->cipher = WLAN_CIPHER_SUITE_CCMP;
	k->icv_len = 8;
	k->iv_len = 8;
	k->keyidx = keyidx;
	k->keylen = keylen;
	k->link_id = -1;
	k->flags = pairwise ? IEEE80211_KEY_FLAG_PAIRWISE : 0;
	atomic64_set(&k->tx_pn, 0);
	memcpy(k->key, key, keylen);
	wiphy_lock(m->hw.wiphy);
	int r = m->ops->set_key(&m->hw, SET_KEY, m->vif, pairwise ? sta : NULL, k);
	wiphy_unlock(m->hw.wiphy);
	if (r) { fprintf(stderr, "[dp] set_key (idx %d pairwise %d) failed: %d\n", keyidx, pairwise, r); free(k); return r; }
	struct mm_key *mk = calloc(1, sizeof(*mk));
	mk->conf = k;
	mk->sta = pairwise ? sta : NULL;
	list_add_tail(&mk->list, &m->keys);
	if (pairwise) dp_ptk = k; else if (keyidx >= 0 && keyidx < 4) dp_gtk[keyidx] = k;
	fprintf(stderr, "[dp] installed %s key idx %d (hw_key_idx %d flags 0x%x)\n", pairwise ? "pairwise" : "group", keyidx, k->hw_key_idx, k->flags);
	return 0;
}

void dp_remove_keys(void)
{
	struct mm *m = g_mm;
	struct mm_key *k, *n;
	wiphy_lock(m->hw.wiphy);
	list_for_each_entry_safe(k, n, &m->keys, list) {
		m->ops->set_key(&m->hw, DISABLE_KEY, m->vif, k->sta, k->conf);
		list_del(&k->list);
		free(k->conf);
		free(k);
	}
	wiphy_unlock(m->hw.wiphy);
	dp_ptk = NULL;
	memset(dp_gtk, 0, sizeof dp_gtk);
}

/* Build and transmit one data frame from <sa> to <da> (STA -> AP direction, ToDS). */
extern int kc_usb_tx_backlog(void);

/* runtime tuning knobs (daemon command `tune <name> <value>`, initial values from RT_BA / RT_AMPDU / RT_MCS / RT_BW40) */
int g_opt_ba = -1, g_opt_ampdu = -1, g_opt_mcs = -2, g_opt_bw40 = -1;
static void opt_init(void)
{
	if (g_opt_ba < 0) g_opt_ba = getenv("RT_BA") ? atoi(getenv("RT_BA")) : 1;	/* bit0 = accept RX BA (default: ~4x download speed), bit1 = start TX BA */
	if (g_opt_ampdu < 0) g_opt_ampdu = getenv("RT_AMPDU") != NULL;
	if (g_opt_mcs == -2) g_opt_mcs = getenv("RT_MCS") ? atoi(getenv("RT_MCS")) : 5;	/* -1 = legacy 6 Mbit/s; default HT MCS5 (20 MHz) with automatic fallback */
	if (g_opt_bw40 < 0) g_opt_bw40 = getenv("RT_BW40") ? atoi(getenv("RT_BW40")) : 1;	/* 40 MHz TX (the BSS is 40 MHz): download 55 -> 80, upload 23 -> 27 Mbit/s */
}
int dp_opt(int *which) { opt_init(); return *which; }

int dp_tx_frame(const u8 *da, u16 ethertype, const u8 *payload, size_t len, bool control_port)
{
	/* back-pressure: do not let the chip's TX path be flooded (the kernel path throttles through txq/ieee80211_stop_queues) */
	if (!control_port) {
		for (int i = 0; i < 400 && kc_usb_tx_backlog() > 96; i++) usleep(500);
	}
	{ extern void mm_wait_tx_queue(void); mm_wait_tx_queue(); }	/* back-pressure while the driver's TX queue is full */
	struct mm *m = g_mm;
	struct ieee80211_hw *hw = &m->hw;
	bool prot = !control_port && dp_ptk;
	size_t hdrlen = 26;
	struct sk_buff *skb = alloc_skb(hw->extra_tx_headroom + hdrlen + 8 + 8 + len + 16, GFP_KERNEL);
	if (!skb) return -ENOMEM;
	skb_reserve(skb, hw->extra_tx_headroom);
	struct ieee80211_qos_hdr *h = skb_put_zero(skb, hdrlen);
	static u16 seq;
	u16 fc = IEEE80211_FTYPE_DATA | IEEE80211_STYPE_QOS_DATA | IEEE80211_FCTL_TODS;
	if (prot) fc |= IEEE80211_FCTL_PROTECTED;
	h->frame_control = cpu_to_le16(fc);
	memcpy(h->addr1, g_mlme.sta->addr, 6);
	memcpy(h->addr2, m->vif->addr, 6);
	memcpy(h->addr3, da, 6);
	h->seq_ctrl = cpu_to_le16((seq++ & 0xfff) << 4);
	h->qos_ctrl = cpu_to_le16(0);			/* TID 0, normal ack */
	/* like mac80211: only leave IV room when the driver asks for it; otherwise (mt7601u, rt2x00) the hardware inserts IV and MIC itself */
	if (prot && (dp_ptk->flags & (IEEE80211_KEY_FLAG_GENERATE_IV | IEEE80211_KEY_FLAG_PUT_IV_SPACE))) {
		u64 pn = atomic64_inc_return(&dp_ptk->tx_pn);
		u8 *c = skb_put(skb, 8);
		c[0] = pn; c[1] = pn >> 8; c[2] = 0; c[3] = 0x20 | (dp_ptk->keyidx << 6);
		c[4] = pn >> 16; c[5] = pn >> 24; c[6] = pn >> 32; c[7] = pn >> 40;
	}
	u8 *llc = skb_put(skb, 8);
	memcpy(llc, rfc1042_header, 6);
	llc[6] = ethertype >> 8; llc[7] = ethertype & 0xff;
	skb_put_data(skb, payload, len);

	struct ieee80211_tx_info *info = IEEE80211_SKB_CB(skb);
	memset(info, 0, sizeof(*info));
	info->band = g_mlme.chan->band;
	info->control.vif = m->vif;
	if (prot) info->control.hw_key = dp_ptk;
	/* no rate control: a fixed rate, legacy 6 Mbit/s unless an HT MCS was selected with `tune mcs N` (EAPOL keeps the lowest rate) */
	info->control.rates[0].idx = 0; info->control.rates[0].count = 4; info->control.rates[1].idx = -1;
	/* minimal rate control: if more than 8% of the last 128 data frames got no ACK, fall back to legacy 6 Mbit/s for 5 s, then try again */
	static int rc_fallback; static time_t rc_resume; static unsigned rc_n; static unsigned long rc_a0, rc_n0;
	if (!control_port && g_opt_mcs >= 0 && ++rc_n >= 128) {
		extern unsigned long g_tx_acked, g_tx_noack;
		unsigned long da = g_tx_acked - rc_a0, dn = g_tx_noack - rc_n0;
		rc_n = 0; rc_a0 = g_tx_acked; rc_n0 = g_tx_noack;
		if (!rc_fallback && da + dn >= 64 && dn * 100 > (da + dn) * 8) { rc_fallback = 1; rc_resume = time(NULL) + 5; fprintf(stderr, "[rate] %lu of %lu frames unacked: falling back to 6 Mbit/s\n", dn, da + dn); }
	}
	if (rc_fallback && time(NULL) >= rc_resume) rc_fallback = 0;
	if (!control_port && g_opt_mcs >= 0 && g_opt_mcs <= 15 && !rc_fallback) {
		info->control.rates[0].idx = g_opt_mcs;
		info->control.rates[0].flags = IEEE80211_TX_RC_MCS | (g_opt_bw40 && g_mlme.width >= NL80211_CHAN_WIDTH_40 ? IEEE80211_TX_RC_40_MHZ_WIDTH : 0)	/* 40 MHz frames only when the AP's BSS is 40 MHz wide: a 20 MHz AP (2.4 GHz) ignores them */;
	}
	/* A-MPDU off: with the BA session up, unicast data sent as A-MPDU never got a reply on rt2800 (DHCP before the session did) */
	opt_init();
	if (!control_port && mlme_tx_ba_ready(0) && g_opt_ampdu) info->flags |= IEEE80211_TX_CTL_AMPDU;
	if (control_port) {
		info->flags |= IEEE80211_TX_CTL_REQ_TX_STATUS | IEEE80211_TX_CTL_USE_MINRATE;
		info->control.flags |= IEEE80211_TX_CTRL_PORT_CTRL_PROTO;
	}
	{ extern int g_rx_debug; if (g_rx_debug) { fprintf(stderr, "[dp] TX data prot=%d cp=%d len %u hw_key=%d:", prot, control_port, skb->len, prot ? dp_ptk->hw_key_idx : -1); for (unsigned i = 0; i < skb->len && i < 48; i++) fprintf(stderr, " %02x", skb->data[i]); fprintf(stderr, "\n"); } }
	skb->protocol = cpu_to_be16(ethertype);
	skb_set_queue_mapping(skb, IEEE80211_AC_BE);
	info->hw_queue = IEEE80211_AC_BE;
	skb->priority = 0;
	return mm_tx(skb, g_mlme.sta);
}

/* IGTK (BIP-CMAC-128) for protected management frames (802.11w, mandatory with WPA3) */
int dp_install_igtk(const u8 *key, int keyidx)
{
	struct mm *m = g_mm;
	struct ieee80211_key_conf *k = calloc(1, sizeof(*k) + 16);
	k->cipher = WLAN_CIPHER_SUITE_AES_CMAC;
	k->icv_len = 8;
	k->iv_len = 0;
	k->keyidx = keyidx;
	k->keylen = 16;
	k->link_id = -1;
	k->flags = 0;
	atomic64_set(&k->tx_pn, 0);
	memcpy(k->key, key, 16);
	wiphy_lock(m->hw.wiphy);
	int r = m->ops->set_key(&m->hw, SET_KEY, m->vif, NULL, k);
	wiphy_unlock(m->hw.wiphy);
	if (r) { fprintf(stderr, "[dp] set_key (IGTK idx %d) failed: %d\n", keyidx, r); free(k); return r; }
	struct mm_key *mk = calloc(1, sizeof(*mk));
	mk->conf = k;
	list_add_tail(&mk->list, &m->keys);
	fprintf(stderr, "[dp] installed IGTK idx %d\n", keyidx);
	return 0;
}
