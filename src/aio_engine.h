// aio_engine.h - Native completion queue engine for pynng asynchronous I/O
//
// Thread-safe MPSC completion queue engine for nng asynchronous operations (nng_aio).
// Allows nng background worker threads to notify completed operations in pure C
// without acquiring Python's GIL or invoking Python runtime callbacks,
// eliminating GIL contention and PyPy foreign-thread context switch overhead.

#ifndef PYNNG_AIO_ENGINE_H
#define PYNNG_AIO_ENGINE_H

#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>

#include <nng/nng.h>
#if NNG_MAJOR_VERSION < 2
  #include <nng/supplemental/util/platform.h>
#endif

#if defined(_WIN32)
  #include <windows.h>
  #include <io.h>
#else
  #include <unistd.h>
  #include <fcntl.h>
  #include <pthread.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Constant wake-up byte passed to pipe write() to wake the asyncio event loop */
static const char _pynng_wake_byte = 1;

typedef struct pynng_aio_entry {
    void *aio;
    _Atomic(uintptr_t) slot_id;
    void *queue;
    _Atomic(int) state; /* 0 = IDLE, 1 = QUEUED, 2 = FREED */
} pynng_aio_entry_t;

typedef struct pynng_mpsc_queue {
    pynng_aio_entry_t **entries;
    size_t capacity;
    size_t head;
    size_t tail;
    size_t count;
    int closed;
    _Atomic(int) write_fd;
    _Atomic(size_t) refcount;
#if defined(_WIN32)
    CRITICAL_SECTION cs;
#else
    pthread_mutex_t lock;
#endif
} pynng_mpsc_queue_t;

/* Each entry holds one reference on its queue and the owner holds one, so the
   queue outlives MPSCAIOEngine when cyclic GC finalizes it before the
   AIOHelper/DeviceAIO objects whose entries use it. */
static void _pynng_mpsc_queue_retain(pynng_mpsc_queue_t *q) {
    atomic_fetch_add_explicit(&q->refcount, 1, memory_order_relaxed);
}

/* Must be called without the queue lock held: the last release destroys it. */
static void _pynng_mpsc_queue_release(pynng_mpsc_queue_t *q, size_t n) {
    if (n == 0) return;
    if (atomic_fetch_sub_explicit(&q->refcount, n, memory_order_acq_rel) == n) {
#if defined(_WIN32)
        DeleteCriticalSection(&q->cs);
#else
        pthread_mutex_destroy(&q->lock);
#endif
        free(q->entries);
        free(q);
    }
}

pynng_mpsc_queue_t *pynng_mpsc_queue_new(int write_fd);
void pynng_mpsc_queue_close(pynng_mpsc_queue_t *q);
void pynng_mpsc_queue_free(pynng_mpsc_queue_t *q);
pynng_aio_entry_t *pynng_aio_entry_new(void *aio, uintptr_t slot_id, pynng_mpsc_queue_t *q);
void pynng_aio_entry_set_slot_id(pynng_aio_entry_t *e, uintptr_t slot_id);
int pynng_aio_entry_is_idle(pynng_aio_entry_t *e);
void pynng_aio_entry_free(pynng_aio_entry_t *e);
void pynng_native_aio_complete(void *arg);
int pynng_mpsc_drain_batch(pynng_mpsc_queue_t *q, uintptr_t *out_slot_ids, int max_entries);

pynng_mpsc_queue_t *pynng_mpsc_queue_new(int write_fd) {
    pynng_mpsc_queue_t *q = (pynng_mpsc_queue_t *)malloc(sizeof(pynng_mpsc_queue_t));
    if (q) {
        size_t initial_cap = 256;
        q->entries = (pynng_aio_entry_t **)malloc(initial_cap * sizeof(pynng_aio_entry_t *));
        if (!q->entries) {
            free(q);
            return NULL;
        }
        q->capacity = initial_cap;
        q->head = 0;
        q->tail = 0;
        q->count = 0;
        q->closed = 0;
        atomic_init(&q->write_fd, write_fd);
        atomic_init(&q->refcount, 1);
#if defined(_WIN32)
        InitializeCriticalSection(&q->cs);
#else
        pthread_mutex_init(&q->lock, NULL);
#endif
    }
    return q;
}

/* ZERO-GIL MPSC PUSH - Thread-safe, non-blocking on uncontended mutex */
void pynng_native_aio_complete(void *arg) {
    pynng_aio_entry_t *entry = (pynng_aio_entry_t *)arg;
    if (!entry) return;
    pynng_mpsc_queue_t *q = (pynng_mpsc_queue_t *)entry->queue;
    if (!q) return;

#if defined(_WIN32)
    EnterCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->lock);
#endif

    /* Atomically transition IDLE (0) -> QUEUED (1).
       If already QUEUED (1) or FREED (2), do not push a second time. */
    int expected = 0;
    if (q->closed || !atomic_compare_exchange_strong_explicit(
            &entry->state, &expected, 1,
            memory_order_acq_rel, memory_order_acquire)) {
#if defined(_WIN32)
        LeaveCriticalSection(&q->cs);
#else
        pthread_mutex_unlock(&q->lock);
#endif
        return;
    }

    if (q->count == q->capacity) {
        size_t new_cap = q->capacity ? q->capacity * 2 : 256;
        pynng_aio_entry_t **new_entries = (pynng_aio_entry_t **)malloc(new_cap * sizeof(pynng_aio_entry_t *));
        if (new_entries) {
            for (size_t i = 0; i < q->count; i++) {
                new_entries[i] = q->entries[(q->tail + i) % q->capacity];
            }
            free(q->entries);
            q->entries = new_entries;
            q->tail = 0;
            q->head = q->count;
            q->capacity = new_cap;
        }
    }

    if (q->count < q->capacity) {
        q->entries[q->head] = entry;
        q->head = (q->head + 1) % q->capacity;
        q->count++;
    }

    /* Written under the lock: pynng_mpsc_queue_close() takes the lock, so once
       it returns the owner can close the fd and no write can reach a reused
       descriptor. The fd is non-blocking. */
    int wfd = atomic_load_explicit(&q->write_fd, memory_order_acquire);
    if (wfd >= 0) {
#if defined(_WIN32)
        (void)_write(wfd, &_pynng_wake_byte, 1);
#else
        (void)write(wfd, &_pynng_wake_byte, 1);
#endif
    }

#if defined(_WIN32)
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_unlock(&q->lock);
#endif
}

void pynng_mpsc_queue_close(pynng_mpsc_queue_t *q) {
    if (!q) return;
    size_t freed = 0;

#if defined(_WIN32)
    EnterCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->lock);
#endif

    q->closed = 1;
    atomic_store_explicit(&q->write_fd, -1, memory_order_release);

    while (q->count > 0) {
        pynng_aio_entry_t *entry = q->entries[q->tail];
        q->tail = (q->tail + 1) % q->capacity;
        q->count--;
        int prev_state = atomic_exchange_explicit(&entry->state, 0, memory_order_acq_rel);
        if (prev_state == 2) {
            free(entry);
            freed++;
        }
    }

#if defined(_WIN32)
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_unlock(&q->lock);
#endif

    _pynng_mpsc_queue_release(q, freed);
}

void pynng_mpsc_queue_free(pynng_mpsc_queue_t *q) {
    if (!q) return;
    pynng_mpsc_queue_close(q);
    _pynng_mpsc_queue_release(q, 1);
}

int pynng_mpsc_drain_batch(pynng_mpsc_queue_t *q, uintptr_t *out_slot_ids, int max_entries) {
    if (!q || !out_slot_ids || max_entries <= 0) return 0;

#if defined(_WIN32)
    EnterCriticalSection(&q->cs);
#else
    pthread_mutex_lock(&q->lock);
#endif

    int count = 0;
    size_t freed = 0;
    while (q->count > 0 && count < max_entries) {
        pynng_aio_entry_t *entry = q->entries[q->tail];
        q->tail = (q->tail + 1) % q->capacity;
        q->count--;

        uintptr_t slot_id = atomic_load_explicit(&entry->slot_id, memory_order_acquire);
        int prev_state = atomic_exchange_explicit(&entry->state, 0, memory_order_acq_rel);
        if (prev_state == 2) {
            free(entry);
            freed++;
        } else if (slot_id != 0) {
            out_slot_ids[count++] = slot_id;
        }
    }

#if defined(_WIN32)
    LeaveCriticalSection(&q->cs);
#else
    pthread_mutex_unlock(&q->lock);
#endif

    _pynng_mpsc_queue_release(q, freed);
    return count;
}

pynng_aio_entry_t *pynng_aio_entry_new(void *aio, uintptr_t slot_id, pynng_mpsc_queue_t *q) {
    pynng_aio_entry_t *e = (pynng_aio_entry_t *)malloc(sizeof(pynng_aio_entry_t));
    if (e) {
        e->aio = aio;
        atomic_init(&e->slot_id, slot_id);
        if (q) _pynng_mpsc_queue_retain(q);
        e->queue = q;
        atomic_init(&e->state, 0);
    }
    return e;
}

void pynng_aio_entry_set_slot_id(pynng_aio_entry_t *e, uintptr_t slot_id) {
    if (e) {
        atomic_store_explicit(&e->slot_id, slot_id, memory_order_release);
    }
}

int pynng_aio_entry_is_idle(pynng_aio_entry_t *e) {
    if (!e) return 0;
    return atomic_load_explicit(&e->state, memory_order_acquire) == 0;
}

void pynng_aio_entry_free(pynng_aio_entry_t *e) {
    if (!e) return;
    atomic_store_explicit(&e->slot_id, 0, memory_order_release);
    pynng_mpsc_queue_t *q = (pynng_mpsc_queue_t *)e->queue;
    if (q) {
#if defined(_WIN32)
        EnterCriticalSection(&q->cs);
#else
        pthread_mutex_lock(&q->lock);
#endif

        /* A QUEUED entry is freed by whoever unlinks it from the queue. */
        int prev_state = atomic_exchange_explicit(&e->state, 2, memory_order_acq_rel);

#if defined(_WIN32)
        LeaveCriticalSection(&q->cs);
#else
        pthread_mutex_unlock(&q->lock);
#endif

        if (prev_state == 0) {
            free(e);
            _pynng_mpsc_queue_release(q, 1);
        }
    } else {
        free(e);
    }
}

/* Synchronous receive: one nng_aio whose completion is signalled in C, so a
   completion does not take the GIL. Python waits in short slices with
   pynng_sync_recv_wait() so that it can run signal handlers between them. */
typedef struct pynng_sync_recv {
    nng_aio *aio;
    nng_mtx *mtx;
    nng_cv *cv;
    int done;
} pynng_sync_recv_t;

int pynng_sync_recv_alloc(pynng_sync_recv_t **out);
nng_aio *pynng_sync_recv_aio(pynng_sync_recv_t *r);
int pynng_sync_recv_wait(pynng_sync_recv_t *r, int slice_ms);
void pynng_sync_recv_free(pynng_sync_recv_t *r);

static void _pynng_sync_recv_complete(void *arg) {
    pynng_sync_recv_t *r = (pynng_sync_recv_t *)arg;
    nng_mtx_lock(r->mtx);
    r->done = 1;
    nng_cv_wake(r->cv);
    nng_mtx_unlock(r->mtx);
}

void pynng_sync_recv_free(pynng_sync_recv_t *r) {
    if (!r) return;
    /* nng_aio_free() waits for a running callback to return, and the
       callback still holds the mutex after it sets done. */
    if (r->aio) nng_aio_free(r->aio);
    if (r->cv) nng_cv_free(r->cv);
    if (r->mtx) nng_mtx_free(r->mtx);
    free(r);
}

int pynng_sync_recv_alloc(pynng_sync_recv_t **out) {
    int rv;
    pynng_sync_recv_t *r = (pynng_sync_recv_t *)calloc(1, sizeof(*r));
    *out = NULL;
    if (!r) return NNG_ENOMEM;
    if ((rv = nng_mtx_alloc(&r->mtx)) != 0 ||
        (rv = nng_cv_alloc(&r->cv, r->mtx)) != 0 ||
        (rv = nng_aio_alloc(&r->aio, _pynng_sync_recv_complete, r)) != 0) {
        pynng_sync_recv_free(r);
        return rv;
    }
    *out = r;
    return 0;
}

nng_aio *pynng_sync_recv_aio(pynng_sync_recv_t *r) {
    return r->aio;
}

/* Returns 1 once the aio has completed, 0 if slice_ms passed first. */
int pynng_sync_recv_wait(pynng_sync_recv_t *r, int slice_ms) {
    nng_time deadline = nng_clock() + (nng_time)slice_ms;
    int done;
    nng_mtx_lock(r->mtx);
    while (!r->done) {
        if (nng_cv_until(r->cv, deadline) == NNG_ETIMEDOUT) break;
    }
    done = r->done;
    nng_mtx_unlock(r->mtx);
    return done;
}

#ifdef __cplusplus
}
#endif

#endif /* PYNNG_AIO_ENGINE_H */
