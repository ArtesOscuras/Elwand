/* SPDX-License-Identifier: GPL-2.0 OR BSD-3-Clause */
/* Extra Linux API pieces needed by rt2x00/rt2800usb; force-included after mt_extra.h. */
#ifndef RT_EXTRA_H
#define RT_EXTRA_H
#include "mt_extra.h"
#include <errno.h>
#ifndef EPROBE_DEFER
#define EPROBE_DEFER 517
#endif
typedef int (*irq_handler_t)(int, void *);
#define alloc_ordered_workqueue(fmt, flags, ...) create_singlethread_workqueue(fmt)
#undef kzalloc_objs
#define kzalloc_objs(v, n, ...) calloc((n) ? (n) : 1, sizeof(v))
#define DMA_TO_DEVICE 1
#define DMA_FROM_DEVICE 2
#define dma_map_single(d, p, l, dir) ((dma_addr_t)(uintptr_t)(p))
#define dma_unmap_single(d, a, l, dir) ((void)0)
#define dma_mapping_error(d, a) 0
#define atomic_add_return(i, v) __atomic_add_fetch(&(v)->counter, (i), __ATOMIC_SEQ_CST)
#define skb_padto(skb, len) skb_put_padto(skb, len)
#define usb_maxpacket(dev, pipe) 512
struct usb_ctrlrequest { u8 bRequestType; u8 bRequest; __le16 wValue; __le16 wIndex; __le16 wLength; } __attribute__((packed));
static inline void usb_fill_control_urb(struct urb *urb, struct usb_device *dev, unsigned int pipe, unsigned char *setup, void *buf, int len, void (*complete)(struct urb *), void *ctx)
{
	urb->dev = dev; urb->pipe = pipe; urb->setup_packet = setup; urb->transfer_buffer = buf; urb->transfer_buffer_length = len; urb->complete = complete; urb->context = ctx;
}
static inline int skb_pad(struct sk_buff *skb, int pad) { skb_put_zero(skb, pad); skb->len -= pad; return 0; }
struct nvmem_cell;
#define nvmem_cell_get(d, n) ((struct nvmem_cell *)ERR_PTR(-ENOENT))
#define nvmem_cell_read(c, l) ((void *)ERR_PTR(-ENOENT))
#define nvmem_cell_put(c) ((void)0)
#define clk_get_sys(a, b) ((struct clk *)ERR_PTR(-ENOENT))
#define clk_get_rate(c) 0UL
#define clk_put(c) ((void)0)
#endif
