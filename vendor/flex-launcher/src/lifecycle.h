/*
 * Copyright 2026 Steve Dehanne
 * SPDX-License-Identifier: Apache-2.0
 *
 * Part of the OPENHTPC project.
 * Original project by Steve Dehanne.
 */
#ifndef FLEX_LIFECYCLE_H
#define FLEX_LIFECYCLE_H

#include <stdbool.h>
#include <sys/types.h>

/* Tracked lifecycle state result */
typedef enum {
    TRACKED_STATUS_NONE = 0,       /* No tracked application is currently active */
    TRACKED_STATUS_RUNNING,        /* Tracked application is alive and running */
    TRACKED_STATUS_FINISHED,       /* Tracked application finished and was reaped */
    TRACKED_STATUS_ECHILD_FAILURE, /* waitpid returned -1 / ECHILD; failing closed */
    TRACKED_STATUS_ERROR           /* Unexpected waitpid error */
} TrackedLifecycleStatus;

/* Lifecycle state structure */
typedef struct {
    pid_t tracked_pid;
    bool application_tracked;
    bool tracked_echild_logged;
    pid_t last_reaped_pid;
    int last_exit_status;
    int echild_log_count;
} TrackedLifecycle;

/* Instance lifecycle management */
TrackedLifecycle *tracked_lifecycle_new(void);
void tracked_lifecycle_free(TrackedLifecycle *lc);
void tracked_lifecycle_init(TrackedLifecycle *lc);
void tracked_lifecycle_reset(TrackedLifecycle *lc);

/* Global default lifecycle accessor */
TrackedLifecycle *tracked_lifecycle_default(void);

/* Tracked PID ownership & status (Single Source of Truth) */
bool tracked_lifecycle_is_active(const TrackedLifecycle *lc);
pid_t tracked_lifecycle_get_pid(const TrackedLifecycle *lc);
pid_t tracked_lifecycle_get_last_reaped_pid(const TrackedLifecycle *lc);
int tracked_lifecycle_get_last_exit_status(const TrackedLifecycle *lc);
int tracked_lifecycle_get_echild_log_count(const TrackedLifecycle *lc);

/* State transitions */
bool tracked_lifecycle_can_launch_tracked(const TrackedLifecycle *lc);
bool tracked_lifecycle_start(TrackedLifecycle *lc, pid_t pid);
void tracked_lifecycle_clear(TrackedLifecycle *lc);

/* Tracked interaction guards */
bool tracked_lifecycle_is_interaction_allowed(const TrackedLifecycle *lc);
bool tracked_lifecycle_guard_command(const TrackedLifecycle *lc, const char *command);
bool tracked_lifecycle_guard_controller(const TrackedLifecycle *lc);

/* Controller action dispatch seam:
 * Consumed by poll_gamepad() for real controller actions */
bool tracked_lifecycle_handle_controller_action(const TrackedLifecycle *lc,
                                               const char *command,
                                               void (*exec_fn)(const char *));

/* Focus and timeout restoration guards */
bool tracked_lifecycle_can_restore_on_focus(const TrackedLifecycle *lc);
bool tracked_lifecycle_can_restore_on_timeout(const TrackedLifecycle *lc);

/* WNOHANG polling and reap handling */
TrackedLifecycleStatus tracked_lifecycle_handle_waitpid_result(
    TrackedLifecycle *lc,
    pid_t wait_res,
    int status,
    int err_code,
    void (*on_finish_callback)(void)
);

TrackedLifecycleStatus tracked_lifecycle_poll_and_update(
    TrackedLifecycle *lc,
    void (*on_finish_callback)(void)
);

/* Default instance convenience wrappers for launcher.c */
bool tracked_is_active(void);
pid_t tracked_get_pid(void);
pid_t tracked_get_last_reaped_pid(void);
int tracked_get_last_exit_status(void);
bool tracked_can_launch(void);
bool tracked_start(pid_t pid);
void tracked_clear(void);
bool tracked_is_interaction_allowed(void);
bool tracked_guard_command(const char *cmd);
bool tracked_guard_controller(void);
bool tracked_handle_controller_action(const char *cmd, void (*exec_fn)(const char *));
bool tracked_can_restore_on_focus(void);
bool tracked_can_restore_on_timeout(void);
TrackedLifecycleStatus tracked_update(void (*on_finish_callback)(void));
TrackedLifecycleStatus tracked_handle_waitpid(pid_t wait_res, int status, int err_code, void (*on_finish_callback)(void));

#endif /* FLEX_LIFECYCLE_H */
