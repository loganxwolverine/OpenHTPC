#include <unistd.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <time.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>
#include <SDL.h>
#include <ini.h>
#include "../launcher.h"
#include <launcher_config.h>
#include "unix.h"
#include "../util.h"
#include "../debug.h"
#include "platform.h"
#include "slideshow.h"

extern Config config;

static int desktop_handler(void *user, const char *section, const char *name, const char *value);
static void strip_field_codes(char *cmd);
static bool ends_with(const char *string, const char *phrase);
static int image_filter(const struct dirent *file);

#define UI_ACTION_TRACE_ENV "OPENHTPC_TRACE_UI_ACTION"
#define UI_ACTION_OPERATION_ENV "OPENHTPC_UI_ACTION_OPERATION_ID"
#define UI_ACTION_CHILD_PID_ENV "OPENHTPC_UI_ACTION_CHILD_PID"

static bool ui_action_trace_enabled(void)
{
    const char *value = getenv(UI_ACTION_TRACE_ENV);
    return value != NULL && strcmp(value, "1") == 0;
}

static bool ui_action_operation_id_valid(const char *operation_id)
{
    static const char prefix[] = "uiaq-";
    if (operation_id == NULL || strncmp(operation_id, prefix, sizeof(prefix) - 1) != 0)
        return false;

    const char *cursor = operation_id + sizeof(prefix) - 1;
    size_t pid_digits = 0;
    if (*cursor < '1' || *cursor > '9')
        return false;
    while (*cursor >= '0' && *cursor <= '9') {
        if (++pid_digits > 10)
            return false;
        cursor++;
    }
    if (*cursor++ != '-')
        return false;

    size_t monotonic_digits = 0;
    if (*cursor == '0') {
        monotonic_digits = 1;
        cursor++;
        if (*cursor >= '0' && *cursor <= '9')
            return false;
    } else {
        if (*cursor < '1' || *cursor > '9')
            return false;
        while (*cursor >= '0' && *cursor <= '9') {
            if (++monotonic_digits > 19)
                return false;
            cursor++;
        }
    }
    return monotonic_digits > 0 && *cursor == '\0';
}

static bool ui_action_monotonic_ns(long long *value)
{
    struct timespec ts;
    if (value == NULL || clock_gettime(CLOCK_MONOTONIC, &ts) != 0)
        return false;
    *value = ((long long) ts.tv_sec * 1000000000LL) + ts.tv_nsec;
    return true;
}

static bool ui_action_trace_path(char *path, size_t path_size)
{
    const char *home = getenv("HOME");
    if (path == NULL || path_size == 0 || home == NULL || *home == '\0')
        return false;
    int written = snprintf(
        path,
        path_size,
        "%s/.local/state/openhtpc/ui-action-timing.jsonl",
        home
    );
    return written > 0 && (size_t) written < path_size;
}

void ui_action_trace_event(const char *event, const char *operation_id, pid_t child_pid)
{
    if (!ui_action_trace_enabled() || event == NULL || operation_id == NULL || *operation_id == '\0')
        return;

    long long mono_ns;
    char target[MAX_PATH_CHARS + 1];
    char directory[MAX_PATH_CHARS + 1];
    char row[512];
    if (!ui_action_monotonic_ns(&mono_ns) || !ui_action_trace_path(target, sizeof(target)))
        return;

    int directory_written = snprintf(
        directory,
        sizeof(directory),
        "%s/.local/state/openhtpc",
        getenv("HOME")
    );
    if (directory_written <= 0 || (size_t) directory_written >= sizeof(directory))
        return;
    make_directory(directory);

    int row_size;
    if (child_pid > 0) {
        row_size = snprintf(
            row,
            sizeof(row),
            "{\"schema\":1,\"event\":\"%s\",\"mono_ns\":%lld,\"pid\":%ld,\"child_pid\":%ld,\"operation_id\":\"%s\"}\n",
            event,
            mono_ns,
            (long) getpid(),
            (long) child_pid,
            operation_id
        );
    } else {
        row_size = snprintf(
            row,
            sizeof(row),
            "{\"schema\":1,\"event\":\"%s\",\"mono_ns\":%lld,\"pid\":%ld,\"operation_id\":\"%s\"}\n",
            event,
            mono_ns,
            (long) getpid(),
            operation_id
        );
    }
    if (row_size <= 0 || (size_t) row_size >= sizeof(row))
        return;

    int fd = open(target, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0600);
    if (fd < 0)
        return;
    (void) fchmod(fd, 0600);
    (void) write(fd, row, (size_t) row_size);
    close(fd);
}

bool ui_action_trace_begin(char *operation_id, size_t operation_id_size)
{
    if (operation_id == NULL || operation_id_size == 0)
        return false;
    operation_id[0] = '\0';
    if (!ui_action_trace_enabled())
        return false;

    long long mono_ns;
    if (!ui_action_monotonic_ns(&mono_ns))
        return false;
    int written = snprintf(
        operation_id,
        operation_id_size,
        "uiaq-%ld-%lld",
        (long) getpid(),
        mono_ns
    );
    if (written <= 0 || (size_t) written >= operation_id_size) {
        operation_id[0] = '\0';
        return false;
    }
    ui_action_trace_event("flex_action_received", operation_id, 0);
    return true;
}

// A function to handle .desktop lines
static int desktop_handler(void *user, const char *section, const char *name, const char *value)
{
    Desktop *pdesktop = (Desktop*) user;
    if (!strcmp(pdesktop->section, section) && !strcmp(name, KEY_EXEC))
        pdesktop->exec = strdup(value);
    return 0;
}

// A function to determine if a file exists in the filesystem
bool file_exists(const char *path)
{
    return access(path, R_OK) ? false : true;
}

// A function to determine if a directory exists in the filesystem
bool directory_exists(const char *path)
{
    struct stat directory;
    return stat(path, &directory) == 0 && S_ISDIR(directory.st_mode) ? true : false;
}

// A function to remove field codes from .desktop file Exec line
static void strip_field_codes(char *cmd)
{
    size_t start = 0;
    for (size_t i = 0; i < strlen(cmd); i++) {
        if (cmd[i] == '%' && i > 0 && cmd[i - 1] == ' ')
            start = i;
        else if (start && i > start + 2 && cmd[i] != ' ') {
            strcpy(cmd + start, cmd + i);
            start = 0;
        }
    }
    if (start)
        cmd[start - 1] ='\0'; 
}

// A function to make a directory, including any intermediate
// directories if necessary
void make_directory(const char *directory) 
{
    char buffer[MAX_PATH_CHARS + 1];
    char *i = NULL;
    size_t length;
    snprintf(buffer, sizeof(buffer), "%s", directory);
    length = strlen(buffer);
    if (buffer[length - 1] == '/')
        buffer[length - 1] = '\0';
    for (i = buffer + 1; *i != '\0'; i++) {
        if (*i == '/') {
            *i = '\0';
            mkdir(buffer, S_IRWXU);
            *i = '/';
        }
    }
    mkdir(buffer, S_IRWXU);
}

// A function to determine if a string ends with a phrase
static bool ends_with(const char *string, const char *phrase)
{
    size_t len_string = strlen(string);
    size_t len_phrase = strlen(phrase);
    if (len_phrase > len_string)
        return false;
    char *p = (char*) string + len_string - len_phrase;
    return strcmp(p, phrase) ? false : true;
}

// A function to launch an external application
bool start_process(char *cmd, bool application, bool replace_launcher)
{
    // Check if the command is an XDG .desktop file
    char *exec = NULL;
    char *tmp = strdup(cmd);
    char *file = strtok(tmp, DELIMITER_ACTION);
    if (ends_with(file, EXT_DESKTOP)) {
        Desktop desktop;
        desktop.exec = NULL;

        // Parse the desktop action from the command (if any)
        const char* const action = strtok(NULL, DELIMITER_ACTION);
        if (action == NULL)
            copy_string(desktop.section, DESKTOP_SECTION_HEADER, sizeof(desktop.section));
        else
            snprintf(desktop.section, sizeof(desktop.section), DESKTOP_SECTION_HEADER_ACTION, action);

        // Parse the .desktop file for the Exec line value
        int error = ini_parse(file, desktop_handler, &desktop);
        if (error < 0) {
            log_error("Desktop file '%s' not found", file);
            free(tmp);
            return false;
        }
        if (desktop.exec == NULL) {
            log_debug("No Exec line found in desktop file '%s'", cmd);
            free(tmp);
            return false;
        }
        exec = desktop.exec;
        strip_field_codes(exec);
        cmd = exec;
    }
    free(tmp);

    // For OnLaunch=Quit, hold the replacement until this SDL process has
    // really exited.  Without this handoff the child can map its window while
    // the old Flex window is still alive, producing two visible launchers.
    int handoff[2] = {-1, -1};
    bool wait_for_launcher_exit = application && (replace_launcher || config.on_launch == ON_LAUNCH_QUIT);
    if (wait_for_launcher_exit && pipe(handoff) != 0) {
        log_error("Could not create launcher handoff pipe");
        free(exec);
        return false;
    }

    // Fork new system shell process
    pid_t child_pid = fork();
    switch(child_pid) {
        case -1:
            log_error("Could not fork new process for application");
            if (wait_for_launcher_exit) {
                close(handoff[0]);
                close(handoff[1]);
            }
            free(exec);
            return false;

        // Child process
        case 0:
            if (wait_for_launcher_exit) {
                char ignored;
                close(handoff[1]);
                while (read(handoff[0], &ignored, 1) > 0) {}
                close(handoff[0]);
            }
            setpgid(0, 0);
            const char *file = "/bin/sh";
            const char *args[] = {
                "sh",
                "-c", 
                cmd, 
                NULL
            };
            execvp(file, (char* const*) args);
            break;

        // Parent process
        default:
            if (wait_for_launcher_exit)
                close(handoff[0]);
            if (!application) 
                return true;
            int status;

            // Check to see if the shell successfully launched
            SDL_Delay(10);
            waitpid(child_pid, &status, WNOHANG);
            if (WIFEXITED(status) && WEXITSTATUS(status) > 126) {
                log_error("Application failed to launch");
                return false;
            }
            log_debug("Application launched successfully");
            break;
    }
    free(exec);
    return true;
}

/* Start a command asynchronously while retaining and returning the exact child
 * process ID so Flex can track its lifecycle and reap only this specific child. */
pid_t start_process_tracked(char *cmd)
{
    if (cmd == NULL)
        return -1;

    char *exec = NULL;
    char *tmp = strdup(cmd);
    char *file = strtok(tmp, DELIMITER_ACTION);
    if (file != NULL && ends_with(file, EXT_DESKTOP)) {
        Desktop desktop;
        desktop.exec = NULL;

        const char* const action = strtok(NULL, DELIMITER_ACTION);
        if (action == NULL)
            copy_string(desktop.section, DESKTOP_SECTION_HEADER, sizeof(desktop.section));
        else
            snprintf(desktop.section, sizeof(desktop.section), DESKTOP_SECTION_HEADER_ACTION, action);

        int error = ini_parse(file, desktop_handler, &desktop);
        if (error < 0) {
            log_error("Desktop file '%s' not found", file);
            free(tmp);
            return -1;
        }
        if (desktop.exec == NULL) {
            log_debug("No Exec line found in desktop file '%s'", cmd);
            free(tmp);
            return -1;
        }
        exec = desktop.exec;
        strip_field_codes(exec);
        cmd = exec;
    }
    free(tmp);

    pid_t child_pid = fork();
    switch (child_pid) {
        case -1:
            log_error("Could not fork tracked application process: %s", strerror(errno));
            free(exec);
            return -1;

        case 0:
            setpgid(0, 0);
            const char *sh_file = "/bin/sh";
            const char *sh_args[] = {
                "sh",
                "-c",
                cmd,
                NULL
            };
            execvp(sh_file, (char * const *) sh_args);
            _exit(127);

        default:
            free(exec);
            return child_pid;
    }
}

/* Run a short settings command to completion without replacing or restarting
 * Flex.  This is used only for atomic preference-save-and-return actions. */
bool run_process_sync(char *cmd, const char *operation_id)
{
    ui_action_trace_event("sync_before_fork", operation_id, 0);
    pid_t child_pid = fork();
    if (child_pid < 0) {
        log_error("Could not fork synchronous settings process");
        ui_action_trace_event("sync_fork_failed", operation_id, 0);
        return false;
    }
    if (child_pid == 0) {
        (void) unsetenv(UI_ACTION_OPERATION_ENV);
        (void) unsetenv(UI_ACTION_CHILD_PID_ENV);
        if (ui_action_trace_enabled() && ui_action_operation_id_valid(operation_id)) {
            char child_pid_text[32];
            int written = snprintf(child_pid_text, sizeof(child_pid_text), "%ld", (long) getpid());
            bool correlation_set = written > 0 && (size_t) written < sizeof(child_pid_text)
                && setenv(UI_ACTION_OPERATION_ENV, operation_id, 1) == 0
                && setenv(UI_ACTION_CHILD_PID_ENV, child_pid_text, 1) == 0;
            if (!correlation_set) {
                (void) unsetenv(UI_ACTION_OPERATION_ENV);
                (void) unsetenv(UI_ACTION_CHILD_PID_ENV);
            }
        }
        setpgid(0, 0);
        const char *args[] = {"sh", "-c", cmd, NULL};
        execvp("/bin/sh", (char * const *) args);
        _exit(127);
    }
    ui_action_trace_event("sync_child_launched", operation_id, child_pid);
    int status = 0;
    while (waitpid(child_pid, &status, 0) < 0) {
        if (errno != EINTR) {
            ui_action_trace_event("sync_wait_failed", operation_id, child_pid);
            return false;
        }
    }
    ui_action_trace_event("sync_waitpid_returned", operation_id, child_pid);
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

// A function to determine if a file is an image file
int image_filter(const struct dirent *file)
{
    size_t len_file = strlen(file->d_name);
    size_t len_extension;
    for (size_t i = 0; i < NUM_IMAGE_EXTENSIONS; i++) {
        len_extension = strlen(extensions[i]);
        if (len_file > len_extension && 
        !strcmp(file->d_name + len_file - len_extension, extensions[i]))
            return 1;
    }
    return 0;
}

// A function to scan a directory for images
void scan_slideshow_directory(Slideshow *slideshow, const char *directory)
{
    struct dirent **files;
    slideshow->num_images = scandir(directory, &files, image_filter, NULL);
    slideshow->images = malloc((size_t) slideshow->num_images * sizeof(char*));
    char file_path[MAX_PATH_CHARS + 1];
    for (int i = 0; i < slideshow->num_images; i++) {
        join_paths(file_path, sizeof(file_path), 2, directory, files[i]->d_name);
        slideshow->images[i] = strdup(file_path);
        free(files[i]);
    }
    free(files);
}

void get_region(char *buffer)
{
    char *lang = getenv("LANG");
    char *token = strtok(lang, "_");
    if (token == NULL)
        return;
    token = strtok(NULL, ".");
    if (token != NULL && strlen(token) == 2)
        copy_string(buffer, token, 3);
}

// A function to shutdown the computer
void scmd_shutdown()
{
    start_process(CMD_SHUTDOWN, false, false);
}

// A function to restart the computer
void scmd_restart()
{
    start_process(CMD_RESTART, false, false);
}

// A function to put the computer to sleep
void scmd_sleep()
{
    start_process(CMD_SLEEP, false, false);
}

// A function to print usage to the command line
void print_usage()
{
    printf("Usage: " EXECUTABLE_TITLE " [OPTIONS]\n");
    printf("  -c p, --config=p   Load config file from path p.\n");
    printf("  -d,   --debug      Enable debug messages.\n");
    printf("  -h,   --help       Show this help message.\n");
    printf("  -v,   --version    Print version information.\n");
}
