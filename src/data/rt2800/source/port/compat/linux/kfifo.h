#pragma once
/* minimal FIFO of u32 TX status words (rt2800usb fills it from a timer, txdone work drains it) */
#include <pthread.h>
#include <stdlib.h>
struct kc_kfifo { unsigned int *buf; unsigned int size, in, out; pthread_mutex_t lock; };
#define DECLARE_KFIFO_PTR(name, type) struct kc_kfifo name
static inline int kc_kfifo_alloc(struct kc_kfifo *f, unsigned int bytes)
{
	unsigned int n = 1; while (n < bytes / 4) n <<= 1;
	f->buf = calloc(n, 4); f->size = n; f->in = f->out = 0; pthread_mutex_init(&f->lock, NULL);
	return f->buf ? 0 : -12;
}
#define kfifo_alloc(f, n, g) kc_kfifo_alloc((f), (n))
#define kfifo_free(f) do { free((f)->buf); (f)->buf = NULL; } while (0)
static inline int kc_kfifo_put(struct kc_kfifo *f, unsigned int v)
{
	int r = 0; pthread_mutex_lock(&f->lock);
	if (f->in - f->out < f->size) { f->buf[f->in++ & (f->size - 1)] = v; r = 1; }
	pthread_mutex_unlock(&f->lock); return r;
}
static inline int kc_kfifo_get(struct kc_kfifo *f, unsigned int *v)
{
	int r = 0; pthread_mutex_lock(&f->lock);
	if (f->in != f->out) { *v = f->buf[f->out++ & (f->size - 1)]; r = 1; }
	pthread_mutex_unlock(&f->lock); return r;
}
#define kfifo_put(f, v) kc_kfifo_put((f), (v))
#define kfifo_get(f, p) kc_kfifo_get((f), (p))
#define kfifo_reset(f) do { (f)->in = (f)->out = 0; } while (0)
#define kfifo_is_empty(f) ((f)->in == (f)->out)
#define kfifo_len(f) ((f)->in - (f)->out)
