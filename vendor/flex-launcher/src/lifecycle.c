/*
 * Copyright 2026 Steve Dehanne
 * SPDX-License-Identifier: Apache-2.0
 *
 * Part of the OPENHTPC project.
 * Original project by Steve Dehanne.
 */
#include "lifecycle.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/wait.h>

#ifndef LOGLEVEL_DEBUG
typedef enum {
    LOGLEVEL_DEBUG = 0,
    LOGLEVEL_ERROR,
    LOGLEVEL_FATAL
} LogLevel;
#endif

/* External logger prototype, compatible with debug.h / debug.c */
void output_log(LogLevel log_level, const char *format, ...);

#ifndef log_debug
#define log_debug(msg, ...) output_log(LOGLEVEL_DEBUG, msg "\n", ##__VA_ARGS__)
#endif
#ifndef log_error
#define log_error(msg, ...) output_log(LOGLEVEL_ERROR, msg "\n", ##__VA_ARGS__)
#endif

/* Default global lifecycle instance */
static TrackedLifecycle default_lifecycle = { 0 };

TrackedLifecycle *tracked_lifecycle_new(void)
{
    TrackedLifecycle *lc = (TrackedLifecycle *)calloc(1, sizeof(TrackedLifecycle));
    return lc;
}

void tracked_lifecycle_free(TrackedLifecycle *lc)
{
    free(lc);
}

TrackedLifecycle *tracked_lifecycle_default(void)
{
    return &default_lifecycle;
}

void tracked_lifecycle_init(TrackedLifecycle *lc)
{
    if (lc != NULL) {
        memset(lc, 0, sizeof(*lc));
    }
}

void tracked_lifecycle_reset(TrackedLifecycle *lc)
{
    tracked_lifecycle_init(lc);
}

bool tracked_lifecycle_is_active(const TrackedLifecycle *lc)
{
    return (lc != NULL && lc->tracked_pid > 0);
}

pid_t tracked_lifecycle_get_pid(const TrackedLifecycle *lc)
{
    return (lc != NULL) ? lc->tracked_pid : 0;
}

pid_t tracked_lifecycle_get_last_reaped_pid(const TrackedLifecycle *lc)
{
    return (lc != NULL) ? lc->last_reaped_pid : 0;
}

int tracked_lifecycle_get_last_exit_status(const TrackedLifecycle *lc)
{
    return (lc != NULL) ? lc->last_exit_status : 0;
}

int tracked_lifecycle_get_echild_log_count(const TrackedLifecycle *lc)
{
    return (lc != NULL) ? lc->echild_log_count : 0;
}

bool tracked_lifecycle_can_launch_tracked(const TrackedLifecycle *lc)
{
    /* Double activation is strictly rejected while a tracked process is active */
    return !tracked_lifecycle_is_active(lc);
}

bool tracked_lifecycle_start(TrackedLifecycle *lc, pid_t pid)
{
    if (lc == NULL || pid <= 0 || tracked_lifecycle_is_active(lc)) {
        return false;
    }
    lc->tracked_pid = pid;
    lc->application_tracked = true;
    lc->tracked_echild_logged = false;
    lc->last_reaped_pid = 0;
    lc->last_exit_status = 0;
    return true;
}

void tracked_lifecycle_clear(TrackedLifecycle *lc)
{
    if (lc != NULL) {
        lc->tracked_pid = 0;
        lc->application_tracked = false;
        lc->tracked_echild_logged = false;
    }
}

bool tracked_lifecycle_is_interaction_allowed(const TrackedLifecycle *lc)
{
    /* Interaction is forbidden whenever a tracked application is active */
    return !tracked_lifecycle_is_active(lc);
}

bool tracked_lifecycle_guard_command(const TrackedLifecycle *lc, const char *command)
{
    if (!tracked_lifecycle_is_interaction_allowed(lc)) {
        log_debug("Ignoring command '%s' while tracked playback is active (pid %d)",
                  command ? command : "", lc ? lc->tracked_pid : 0);
        return false;
    }
    return true;
}

bool tracked_lifecycle_guard_controller(const TrackedLifecycle *lc)
{
    return tracked_lifecycle_is_interaction_allowed(lc);
}

bool tracked_lifecycle_handle_controller_action(const TrackedLifecycle *lc,
                                               const char *command,
                                               void (*exec_fn)(const char *))
{
    if (!tracked_lifecycle_guard_controller(lc)) {
        log_debug("Ignoring controller action '%s' while tracked playback is active (pid %d)",
                  command ? command : "", lc ? lc->tracked_pid : 0);
        return false;
    }
    if (exec_fn != NULL && command != NULL) {
        exec_fn(command);
    }
    return true;
}

bool tracked_lifecycle_can_restore_on_focus(const TrackedLifecycle *lc)
{
    /* Focus events must NOT restore normal interactivity while tracked child is alive */
    return !tracked_lifecycle_is_active(lc);
}

bool tracked_lifecycle_can_restore_on_timeout(const TrackedLifecycle *lc)
{
    /* Launch timeout must NOT restore normal interactivity while tracked child is alive */
    return !tracked_lifecycle_is_active(lc);
}

TrackedLifecycleStatus tracked_lifecycle_handle_waitpid_result(
    TrackedLifecycle *lc,
    pid_t wait_res,
    int status,
    int err_code,
    void (*on_finish_callback)(void))
{
    if (lc == NULL || lc->tracked_pid <= 0) {
        return TRACKED_STATUS_NONE;
    }

    if (wait_res == lc->tracked_pid) {
        log_debug("Tracked application finished (pid %d)", lc->tracked_pid);
        lc->last_reaped_pid = lc->tracked_pid;
        lc->last_exit_status = status;
        lc->tracked_pid = 0;
        lc->application_tracked = false;
        lc->tracked_echild_logged = false;
        if (on_finish_callback != NULL) {
            on_finish_callback();
        }
        return TRACKED_STATUS_FINISHED;
    }
    else if (wait_res == 0) {
        /* Exact child is still running */
        return TRACKED_STATUS_RUNNING;
    }
    else if (wait_res == -1 && err_code == ECHILD) {
        /* Fail closed on ECHILD: do not call completion callback, preserve tracked state */
        if (!lc->tracked_echild_logged) {
            log_error("Tracked child ownership failure (pid %d returned ECHILD); failing closed", lc->tracked_pid);
            lc->tracked_echild_logged = true;
            lc->echild_log_count++;
        }
        return TRACKED_STATUS_ECHILD_FAILURE;
    }
    else if (wait_res == -1 && err_code != EINTR) {
        log_error("waitpid error on tracked pid %d: %s", lc->tracked_pid, strerror(err_code));
        return TRACKED_STATUS_ERROR;
    }

    return TRACKED_STATUS_RUNNING;
}

TrackedLifecycleStatus tracked_lifecycle_poll_and_update(
    TrackedLifecycle *lc,
    void (*on_finish_callback)(void))
{
    if (lc == NULL || lc->tracked_pid <= 0) {
        return TRACKED_STATUS_NONE;
    }
    int status = 0;
    pid_t res = waitpid(lc->tracked_pid, &status, WNOHANG);
    int err = (res == -1) ? errno : 0;
    return tracked_lifecycle_handle_waitpid_result(lc, res, status, err, on_finish_callback);
}

/* Default instance convenience wrappers */
bool tracked_is_active(void) { return tracked_lifecycle_is_active(&default_lifecycle); }
pid_t tracked_get_pid(void) { return tracked_lifecycle_get_pid(&default_lifecycle); }
pid_t tracked_get_last_reaped_pid(void) { return tracked_lifecycle_get_last_reaped_pid(&default_lifecycle); }
int tracked_get_last_exit_status(void) { return tracked_lifecycle_get_last_exit_status(&default_lifecycle); }
bool tracked_can_launch(void) { return tracked_lifecycle_can_launch_tracked(&default_lifecycle); }
bool tracked_start(pid_t pid) { return tracked_lifecycle_start(&default_lifecycle, pid); }
void tracked_clear(void) { tracked_lifecycle_clear(&default_lifecycle); }
bool tracked_is_interaction_allowed(void) { return tracked_lifecycle_is_interaction_allowed(&default_lifecycle); }
bool tracked_guard_command(const char *cmd) { return tracked_lifecycle_guard_command(&default_lifecycle, cmd); }
bool tracked_guard_controller(void) { return tracked_lifecycle_guard_controller(&default_lifecycle); }
bool tracked_handle_controller_action(const char *cmd, void (*exec_fn)(const char *)) {
    return tracked_lifecycle_handle_controller_action(&default_lifecycle, cmd, exec_fn);
}
bool tracked_can_restore_on_focus(void) { return tracked_lifecycle_can_restore_on_focus(&default_lifecycle); }
bool tracked_can_restore_on_timeout(void) { return tracked_lifecycle_can_restore_on_timeout(&default_lifecycle); }
TrackedLifecycleStatus tracked_update(void (*on_finish_callback)(void)) {
    return tracked_lifecycle_poll_and_update(&default_lifecycle, on_finish_callback);
}
TrackedLifecycleStatus tracked_handle_waitpid(pid_t wait_res, int status, int err_code, void (*on_finish_callback)(void)) {
    return tracked_lifecycle_handle_waitpid_result(&default_lifecycle, wait_res, status, err_code, on_finish_callback);
}
