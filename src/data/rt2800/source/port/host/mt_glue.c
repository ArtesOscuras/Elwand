// SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause
// mac80211 entry points used by mt7601u that mm_core.c (written for rtw89) does not provide yet.
#include "kcompat.h"
#include <net/mac80211.h>
#include <pthread.h>
#include "mm.h"

extern void ieee80211_rx_napi(struct ieee80211_hw *hw, struct ieee80211_sta *sta, struct sk_buff *skb, struct napi_struct *napi);
extern void ieee80211_tx_status_irqsafe(struct ieee80211_hw *hw, struct sk_buff *skb);

void ieee80211_rx_list(struct ieee80211_hw *hw, struct ieee80211_sta *sta, struct sk_buff *skb, struct list_head *list)
{
	ieee80211_rx_napi(hw, sta, skb, NULL);
}

void ieee80211_tx_status_skb(struct ieee80211_hw *hw, struct sk_buff *skb) { ieee80211_tx_status_irqsafe(hw, skb); }
void ieee80211_tx_status_ext(struct ieee80211_hw *hw, struct ieee80211_tx_status *status) {}

unsigned int ieee80211_get_hdrlen_from_skb(const struct sk_buff *skb)
{
	return ieee80211_hdrlen(((const struct ieee80211_hdr *)skb->data)->frame_control);
}

void ieee80211_get_tx_rates(struct ieee80211_vif *vif, struct ieee80211_sta *sta, struct sk_buff *skb, struct ieee80211_tx_rate *dest, int max_rates)
{
	/* no rate control module: legacy 1 Mbit/s CCK for management/low rates, as chosen by the caller in info->control.rates */
	struct ieee80211_tx_info *info = IEEE80211_SKB_CB(skb);
	for (int i = 0; i < max_rates; i++) dest[i] = info->control.rates[i];
	if (max_rates > 0 && (dest[0].idx < 0 || !dest[0].count)) { dest[0].idx = 0; dest[0].count = 3; dest[0].flags = 0; }
}

void ieee80211_send_bar(struct ieee80211_vif *vif, u8 *ra, u16 tid, u16 ssn) {}
/* TX flow control: rt2x00 drops frames silently when its queue is full and tells the stack to stop with stop_queue();
 * wake_queue() comes from the TX-done path.  The sender (dp_tx_frame, called from the utun reader) waits here meanwhile,
 * which stops reading the utun and pushes back on macOS's TCP instead of losing packets. */
static pthread_mutex_t txq_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t txq_cond = PTHREAD_COND_INITIALIZER;
static unsigned txq_stopped;
unsigned long g_txq_waits, g_txq_wait_ms;
void ieee80211_stop_queue(struct ieee80211_hw *hw, int queue)
{
	pthread_mutex_lock(&txq_lock); txq_stopped |= 1u << (queue & 31); pthread_mutex_unlock(&txq_lock);
}
void ieee80211_wake_queue(struct ieee80211_hw *hw, int queue)
{
	pthread_mutex_lock(&txq_lock); txq_stopped &= ~(1u << (queue & 31)); pthread_cond_broadcast(&txq_cond); pthread_mutex_unlock(&txq_lock);
}
void mm_wait_tx_queue(void)
{
	struct timespec t0, ts;
	pthread_mutex_lock(&txq_lock);
	if (txq_stopped) {
		clock_gettime(CLOCK_REALTIME, &t0);
		ts = t0; ts.tv_nsec += 100000000L; if (ts.tv_nsec >= 1000000000L) { ts.tv_sec++; ts.tv_nsec -= 1000000000L; }	/* never wait longer than 100 ms */
		while (txq_stopped && pthread_cond_timedwait(&txq_cond, &txq_lock, &ts) == 0) ;
		clock_gettime(CLOCK_REALTIME, &ts);
		g_txq_waits++; g_txq_wait_ms += (ts.tv_sec - t0.tv_sec) * 1000 + (ts.tv_nsec - t0.tv_nsec) / 1000000;
	}
	pthread_mutex_unlock(&txq_lock);
}
void ieee80211_handle_wake_tx_queue(struct ieee80211_hw *hw, struct ieee80211_txq *txq) {}
void mt7601u_init_debugfs(void *dev) {}

/* station mode only: no AP-side beacon/protection frame generation; the interface list is the single STA vif */
void ieee80211_rts_get(struct ieee80211_hw *hw, struct ieee80211_vif *vif, const void *frame, size_t frame_len, const struct ieee80211_tx_info *frame_txctl, struct ieee80211_rts *rts) { memset(rts, 0, sizeof *rts); }
void ieee80211_ctstoself_get(struct ieee80211_hw *hw, struct ieee80211_vif *vif, const void *frame, size_t frame_len, const struct ieee80211_tx_info *frame_txctl, struct ieee80211_cts *cts) { memset(cts, 0, sizeof *cts); }
struct sk_buff *ieee80211_get_buffered_bc(struct ieee80211_hw *hw, struct ieee80211_vif *vif) { return NULL; }
void ieee80211_iterate_interfaces(struct ieee80211_hw *hw, u32 iter_flags, void (*iterator)(void *data, u8 *mac, struct ieee80211_vif *vif), void *data)
{
	if (g_mm && g_mm->vif) iterator(data, g_mm->vif->addr, g_mm->vif);
}

/* ---------------- software scan (drivers without hw_scan: hop channels and send probe requests) ---------------- */
extern int g_scan_only_chan;
#define SCAN_DWELL_MS 90

static int build_probe_req(u8 *buf, const u8 *sa, const u8 *ssid, int ssid_len, int chan, int band)
{
	static const u8 rates[] = { 0x82, 0x84, 0x8b, 0x96, 0x0c, 0x12, 0x18, 0x24 }, ext[] = { 0x30, 0x48, 0x60, 0x6c };
	u8 *p = buf;
	*p++ = 0x40; *p++ = 0; *p++ = 0; *p++ = 0;			/* frame control (probe req), duration */
	memset(p, 0xff, 6); p += 6;					/* DA */
	memcpy(p, sa, 6); p += 6;					/* SA */
	memset(p, 0xff, 6); p += 6;					/* BSSID */
	*p++ = 0; *p++ = 0;						/* seq ctrl (filled by hardware) */
	*p++ = 0; *p++ = ssid_len; memcpy(p, ssid, ssid_len); p += ssid_len;
	if (band == NL80211_BAND_5GHZ) {	/* OFDM only */
		static const u8 r5[] = { 0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c };
		*p++ = 1; *p++ = sizeof r5; memcpy(p, r5, sizeof r5); p += sizeof r5;
	} else {
		*p++ = 1; *p++ = sizeof rates; memcpy(p, rates, sizeof rates); p += sizeof rates;
		*p++ = 50; *p++ = sizeof ext; memcpy(p, ext, sizeof ext); p += sizeof ext;
	}
	*p++ = 3; *p++ = 1; *p++ = chan;				/* DS parameter set */
	return p - buf;
}

static void *sw_scan_thread(void *arg)
{
	struct mm *m = g_mm;
	struct wiphy *wiphy = m->hw.wiphy;
	u8 ssid[33]; int ssid_len = 0;
	if (arg) { ssid_len = strlen(arg); memcpy(ssid, arg, ssid_len); free(arg); }
	if (m->ops->sw_scan_start) { wiphy_lock(wiphy); m->ops->sw_scan_start(&m->hw, m->vif, m->vif->addr); wiphy_unlock(wiphy); }
	for (int band = NL80211_BAND_2GHZ; band <= NL80211_BAND_5GHZ; band++) {
	struct ieee80211_supported_band *sb = wiphy->bands[band];
	for (int i = 0; sb && i < sb->n_channels; i++) {
		struct ieee80211_channel *ch = &sb->channels[i];
		if (ch->flags & IEEE80211_CHAN_DISABLED) continue;
		if (band == NL80211_BAND_5GHZ) {	/* rt2x00 also lists HT40 centre channels (38, 42, ...): not valid 20 MHz channels, and tuning to them dropped the adapter off USB */
			int n = (ch->center_freq - 5000) / 5;
			if (!(n >= 149 ? (n - 149) % 4 == 0 : n % 4 == 0)) continue;
		}
		if (g_scan_only_chan && ieee80211_freq_khz_to_channel(ch->center_freq * 1000) != g_scan_only_chan) continue;
		wiphy_lock(wiphy);
		m->hw.conf.chandef.chan = ch;
		m->hw.conf.chandef.width = NL80211_CHAN_WIDTH_20_NOHT;
		m->hw.conf.chandef.center_freq1 = ch->center_freq;
		int cr = (m->hw.conf.power_level = m->hw.conf.chandef.chan->max_power, m->ops->config(&m->hw, -1, IEEE80211_CONF_CHANGE_CHANNEL));
		wiphy_unlock(wiphy);
		if (getenv("RT_SCANDEBUG")) fprintf(stderr, "[scan] hop band %d hw_value %d freq %d -> %d\n", band, ch->hw_value, ch->center_freq, cr);
		for (int pass = 0; pass < 2; pass++) {
			if ((ch->flags & IEEE80211_CHAN_NO_IR) || (band == NL80211_BAND_5GHZ && getenv("RT_PASSIVE5"))) { usleep(SCAN_DWELL_MS * 1000 / 2); continue; }	/* passive channel: listen only */
			struct sk_buff *skb = alloc_skb(384, GFP_KERNEL);
			if (!skb) break;
			skb_reserve(skb, 96);	/* room for the driver's TXWI/DMA headers */
			int len = build_probe_req(skb_put(skb, 128), m->vif->addr, ssid, ssid_len, ch->hw_value, band);
			skb_trim(skb, len);
			struct ieee80211_tx_info *info = IEEE80211_SKB_CB(skb);
			memset(info, 0, sizeof *info);
			info->band = band;
			info->control.rates[0].idx = (band == NL80211_BAND_2GHZ && getenv("RT_OFDM24")) ? 4 : 0; info->control.rates[0].count = 2;
			info->control.rates[1].idx = -1;
			mm_tx(skb, NULL);
			usleep(SCAN_DWELL_MS * 1000 / 2);
		}
	}
	}
	/* back to the operating channel when associated, otherwise the radio stays on the last scanned channel and the link starves */
	if (m->chanctx) {
		wiphy_lock(wiphy);
		m->hw.conf.chandef = m->chanctx->def;
		(m->hw.conf.power_level = m->hw.conf.chandef.chan->max_power, m->ops->config(&m->hw, -1, IEEE80211_CONF_CHANGE_CHANNEL));
		wiphy_unlock(wiphy);
	}
	if (m->ops->sw_scan_complete) { wiphy_lock(wiphy); m->ops->sw_scan_complete(&m->hw, m->vif); wiphy_unlock(wiphy); }
	struct cfg80211_scan_info info = { .aborted = false };
	ieee80211_scan_completed(&m->hw, &info);
	return NULL;
}

int mm_sw_scan(const u8 *ssid, int ssid_len)
{
	struct mm *m = g_mm;
	pthread_t t;
	char *copy = ssid_len ? strndup((const char *)ssid, ssid_len) : NULL;
	reinit_completion(&m->scan_done);
	m->scan_running = true;
	if (pthread_create(&t, NULL, sw_scan_thread, copy)) { m->scan_running = false; return -ENOMEM; }
	pthread_detach(t);
	return 0;
}

/* ---------------- ops adapters: rtw89-style (sta_state, link_info_changed) -> old-style (sta_add, bss_info_changed) ---------------- */
int mm_compat_sta_state(struct mm *m, struct ieee80211_sta *sta, enum ieee80211_sta_state from, enum ieee80211_sta_state to)
{
	if (m->ops->sta_state) return m->ops->sta_state(&m->hw, m->vif, sta, from, to);
	if (from == IEEE80211_STA_NOTEXIST && to == IEEE80211_STA_NONE && m->ops->sta_add) return m->ops->sta_add(&m->hw, m->vif, sta);
	if (from == IEEE80211_STA_NONE && to == IEEE80211_STA_NOTEXIST && m->ops->sta_remove) return m->ops->sta_remove(&m->hw, m->vif, sta);
	return 0;
}

void mm_compat_link_info_changed(struct mm *m, struct ieee80211_hw *hw, struct ieee80211_vif *vif, struct ieee80211_bss_conf *bc, u64 changed)
{
	if (m->ops->link_info_changed) { m->ops->link_info_changed(hw, vif, bc, changed); return; }
	if (!bc->basic_rates) bc->basic_rates = 0x15f;	/* CCK 1/2/5.5/11 + OFDM 6/12/24 */
	if (m->ops->bss_info_changed) m->ops->bss_info_changed(hw, vif, bc, changed);
}

void mm_compat_vif_cfg_changed(struct mm *m, struct ieee80211_hw *hw, struct ieee80211_vif *vif, u64 changed)
{
	if (m->ops->vif_cfg_changed) { m->ops->vif_cfg_changed(hw, vif, changed); return; }
	if (m->ops->bss_info_changed) m->ops->bss_info_changed(hw, vif, &vif->bss_conf, changed);
}
