#pragma once
#include "kcompat.h"
/* hrtimer on top of the delayed-work thread (1 ms granularity is enough for rt2800usb's TX status polling) */
#define HRTIMER_MODE_REL 0
static inline void kc_hrtimer_fn(struct work_struct *w) { struct hrtimer *t = container_of(to_delayed_work(w), struct hrtimer, dw); if (t->function) t->function(t); }
static inline void hrtimer_update_function(struct hrtimer *t, enum hrtimer_restart (*fn)(struct hrtimer *)) { t->function = fn; INIT_DELAYED_WORK(&t->dw, kc_hrtimer_fn); }
static inline void hrtimer_start(struct hrtimer *t, ktime_t ns, int mode) { unsigned long ms = ns / 1000000; queue_delayed_work(NULL, &t->dw, ms ? ms : 1); }
static inline int hrtimer_cancel(struct hrtimer *t) { return cancel_delayed_work_sync(&t->dw); }
