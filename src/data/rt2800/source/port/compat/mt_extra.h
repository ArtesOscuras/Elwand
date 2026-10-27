/* SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause */
/* Extra Linux API pieces needed by the upstream mt7601u driver; force-included (-include) when building it. */
#ifndef MT_EXTRA_H
#define MT_EXTRA_H
#include "kcompat.h"
#include <linux/usb.h>
#include <linux/firmware.h>

/* paged RX is emulated: a "page" is a refcounted heap block, frags are copied into a roomy linear skb */
static inline struct page *dev_alloc_pages(unsigned int order)
{
	struct page *p = calloc(1, sizeof *p);
	p->ref = 1; p->addr = calloc(1, 4096u << order);
	return p;
}
#define page_address(p) ((p)->addr)
#define get_page(p) ((p)->ref++)
static inline void put_page(struct page *p) { if (p && --p->ref <= 0) { free(p->addr); free(p); } }
#define __free_pages(p, o) put_page(p)

static inline struct sk_buff *kc_alloc_skb_roomy(unsigned int n, gfp_t g) { return (alloc_skb)(n < 4096 ? 4096 : n, g); }
#define alloc_skb(n, g) kc_alloc_skb_roomy((n), (g))
static inline void skb_add_rx_frag(struct sk_buff *skb, int i, struct page *p, int off, int size, unsigned int truesize)
{
	skb_put_data(skb, (u8 *)p->addr + off, size);
}
static inline int skb_put_padto(struct sk_buff *skb, unsigned int len)
{
	if (skb->len < len) skb_put_zero(skb, len - skb->len);
	return 0;
}
static inline int skb_cow(struct sk_buff *skb, unsigned int headroom) { return 0; }

#define USB_DEVICE(vend, prod) .match_flags = USB_DEVICE_ID_MATCH_VENDOR | USB_DEVICE_ID_MATCH_PRODUCT, .idVendor = (vend), .idProduct = (prod)
typedef int pm_message_t;
#define devm_kmalloc(d, n, g) kmalloc(n, g)
static inline int firmware_request_cache(struct device *d, const char *name) { return 0; }
extern int usb_bulk_msg(struct usb_device *dev, unsigned int pipe, void *data, int len, int *actual_length, int timeout);

/* tasklets run on the shared workqueue thread */
struct tasklet_struct { struct work_struct work; void (*cb)(struct tasklet_struct *); };
static inline void kc_tasklet_fn(struct work_struct *w) { struct tasklet_struct *t = container_of(w, struct tasklet_struct, work); t->cb(t); }
static inline void tasklet_setup(struct tasklet_struct *t, void (*cb)(struct tasklet_struct *)) { t->cb = cb; INIT_WORK(&t->work, kc_tasklet_fn); }
static inline void tasklet_schedule(struct tasklet_struct *t) { queue_work(NULL, &t->work); }
static inline void tasklet_kill(struct tasklet_struct *t) { cancel_work_sync(&t->work); }
#define from_tasklet(var, t, field) container_of(t, typeof(*var), field)
static inline void netif_receive_skb_list(struct list_head *l) {}
#define usb_poison_urb(u) usb_kill_urb(u)
#endif
