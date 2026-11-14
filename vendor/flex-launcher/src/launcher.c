#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <time.h>
#include <math.h>
#include <SDL.h>
#include <SDL_syswm.h>
#include <SDL_image.h>
#include <SDL_ttf.h>
#include <SDL_thread.h>
#include "launcher.h"
#include <launcher_config.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include "image.h"
#include "util.h"
#include "debug.h"
#include "clock.h"
#include "media_wall.h"
#ifdef OPENHTPC_LAB_QA_CAPTURE
static unsigned int lab_qa_loop = 0;
#endif

/* HOME network indicator: local interface inspection only, never Internet probing. */
#ifdef __linux__
#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#endif
#include "platform/platform.h"
#include <time.h>

static void pre_launch(void);
static void post_launch(void);
static void init_sdl(void);
static void init_sdl_image(void);
static void create_window(void);
static void init_sdl_ttf(void);
static int load_menu(Menu *menu, bool set_back_menu, bool reset_position);
static int load_menu_by_name(const char *menu_name, bool set_back_menu, bool reset_position);
static void publish_media_page(const char *menu_name);
static void update_slideshow(void);
static void resume_slideshow(void);
static void update_screensaver(void);
static void update_clock(bool block);
static void init_slideshow(void);
static void init_screensaver(void);
static void calculate_button_geometry(Entry *entry, int buttons);
static void render_buttons(Menu *menu);
static void free_menu_detail_textures(Menu *menu);
static void move_left(void);
static void move_right(void);
static void media_wall_move(int horizontal, int vertical);
static bool is_media_wall(const Menu *menu);
static bool prepare_media_wall(Menu *menu);
static void draw_media_wall(void);
static void free_media_wall(Menu *menu);
static void load_submenu(const char *submenu);
static void load_back_menu(Menu *menu);
static void draw_screen(void);
static void handle_keypress(SDL_Keysym *key);
static void execute_command(const char *command);
static void refresh_live_optical_state(void);
static void refresh_live_activity_state(void);
static void draw_activity_overlay(void);
static void draw_resume_modal(void);
static void close_resume_modal(void);
static void run_resume_modal_action(const char *token);
static void refresh_home_network_indicator(void);
static void draw_home_network_indicator(void);
static void refresh_disc_sheet_background(void);
static void reload_menu_section(Menu *menu);
static void reload_media_menu_sections(void);
static void refresh_current_menu_background_and_entries(void);
static void poll_gamepad(void);
static void init_gamepad(Gamepad **gamepad, int device_index);
static void connect_gamepad(int device_index, bool open, bool raise_error);
static void disconnect_gamepad(int id, bool disconnect, bool remove);
static void open_controller(Gamepad *gamepad, bool raise_error);
static void cleanup(void);
static bool is_media_sidebar(void);
static bool is_movie_detail(const Menu *menu);
static bool is_media_list(void);
static unsigned int menu_page_size(const Menu *menu);

// Initialize default settings
Config config = {
    .default_menu                     = NULL,
    .background_image                 = NULL,
    .slideshow_directory              = NULL,
    .title_font_path                  = NULL,
    .title_fallback_font_path         = NULL,
    .vsync                            = true,
    .fps_limit                        = -1,
    .application_timeout              = DEFAULT_APPLICATION_TIMEOUT * 1000,
    .titles_enabled                   = DEFAULT_TITLES_ENABLED,
    .title_font_size                  = DEFAULT_FONT_SIZE,
    .title_font_color.r               = DEFAULT_TITLE_FONT_COLOR_R,
    .title_font_color.g               = DEFAULT_TITLE_FONT_COLOR_G,
    .title_font_color.b               = DEFAULT_TITLE_FONT_COLOR_B,
    .title_font_color.a               = DEFAULT_TITLE_FONT_COLOR_A,
    .title_shadows                    = DEFAULT_TITLE_SHADOWS,
    .title_shadow_color.r             = DEFAULT_TITLE_SHADOW_COLOR_R,
    .title_shadow_color.g             = DEFAULT_TITLE_SHADOW_COLOR_G,
    .title_shadow_color.b             = DEFAULT_TITLE_SHADOW_COLOR_B,
    .title_shadow_color.a             = DEFAULT_TITLE_SHADOW_COLOR_A,
    .background_mode                  = BACKGROUND_COLOR,
    .background_color.r               = DEFAULT_BACKGROUND_COLOR_R,
    .background_color.g               = DEFAULT_BACKGROUND_COLOR_G,
    .background_color.b               = DEFAULT_BACKGROUND_COLOR_B,
    .chroma_key_color.r               = DEFAULT_CHROMA_KEY_COLOR_R,
    .chroma_key_color.g               = DEFAULT_CHROMA_KEY_COLOR_G,
    .chroma_key_color.b               = DEFAULT_CHROMA_KEY_COLOR_B,
    .chroma_key_color.a               = DEFAULT_CHROMA_KEY_COLOR_A,
    .background_color.a               = 0xFF,
    .background_overlay               = DEFAULT_BACKGROUND_OVERLAY,
    .background_overlay_color.r       = DEFAULT_BACKGROUND_OVERLAY_COLOR_R,
    .background_overlay_color.g       = DEFAULT_BACKGROUND_OVERLAY_COLOR_G,
    .background_overlay_color.b       = DEFAULT_BACKGROUND_OVERLAY_COLOR_B,
    .background_overlay_color.a       = DEFAULT_BACKGROUND_OVERLAY_COLOR_A,
    .background_overlay_opacity[0]    = '\0',
    .highlight                        = true,
    .icon_size                        = DEFAULT_ICON_SIZE,
    .highlight_fill_color.r           = DEFAULT_HIGHLIGHT_FILL_COLOR_R,
    .highlight_fill_color.g           = DEFAULT_HIGHLIGHT_FILL_COLOR_G,
    .highlight_fill_color.b           = DEFAULT_HIGHLIGHT_FILL_COLOR_B,
    .highlight_fill_color.a           = DEFAULT_HIGHLIGHT_FILL_COLOR_A,
    .highlight_outline_color.r        = DEFAULT_HIGHLIGHT_OUTLINE_COLOR_R,
    .highlight_outline_color.g        = DEFAULT_HIGHLIGHT_OUTLINE_COLOR_G,
    .highlight_outline_color.b        = DEFAULT_HIGHLIGHT_OUTLINE_COLOR_B,
    .highlight_outline_color.a        = DEFAULT_HIGHLIGHT_OUTLINE_COLOR_A,
    .highlight_outline_size           = DEFAULT_HIGHLIGHT_OUTLINE_SIZE,
    .highlight_rx                     = DEFAULT_HIGHLIGHT_CORNER_RADIUS,
    .title_padding                    = -1,
    .max_buttons                      = DEFAULT_MAX_BUTTONS,
    .icon_spacing                     = -1,
    .highlight_vpadding               = -1,
    .highlight_hpadding               = -1,
    .title_opacity[0]                 = '\0',
    .highlight_fill_opacity[0]        = '\0',
    .highlight_outline_opacity[0]     = '\0',
    .vcenter[0]             = '\0',
    .icon_spacing_str[0]              = '\0',
    .scroll_indicators                = DEFAULT_SCROLL_INDICATORS,
    .scroll_indicator_fill_color.r    = DEFAULT_SCROLL_INDICATOR_FILL_COLOR_R,
    .scroll_indicator_fill_color.g    = DEFAULT_SCROLL_INDICATOR_FILL_COLOR_G,
    .scroll_indicator_fill_color.b    = DEFAULT_SCROLL_INDICATOR_FILL_COLOR_B,
    .scroll_indicator_fill_color.a    = DEFAULT_SCROLL_INDICATOR_FILL_COLOR_A,
    .scroll_indicator_outline_size    = DEFAULT_SCROLL_INDICATOR_OUTLINE_SIZE,
    .scroll_indicator_outline_color.r = DEFAULT_SCROLL_INDICATOR_OUTLINE_COLOR_R,
    .scroll_indicator_outline_color.g = DEFAULT_SCROLL_INDICATOR_OUTLINE_COLOR_G,
    .scroll_indicator_outline_color.b = DEFAULT_SCROLL_INDICATOR_OUTLINE_COLOR_B,
    .scroll_indicator_outline_color.a = DEFAULT_SCROLL_INDICATOR_OUTLINE_COLOR_A,
    .scroll_indicator_opacity[0]      = '\0',
    .title_oversize_mode              = OVERSIZE_TRUNCATE,
    .wrap_entries                     = DEFAULT_WRAP_ENTRIES,
    .reset_on_back                    = DEFAULT_RESET_ON_BACK,
    .mouse_select                     = DEFAULT_MOUSE_SELECT,
    .inhibit_os_screensaver           = DEFAULT_INHIBIT_OS_SCREENSAVER,
    .startup_cmd                      = NULL,
    .quit_cmd                         = NULL,
    .live_optical_state               = NULL,
    .live_activity_state              = NULL,
    .screensaver_enabled              = false,
    .screensaver_idle_time            = DEFAULT_SCREENSAVER_IDLE_TIME*1000,
    .screensaver_intensity_str[0]     = '\0',
    .screensaver_pause_slideshow      = DEFAULT_SCREENSAVER_PAUSE_SLIDESHOW,
    .gamepad_enabled                  = DEFAULT_GAMEPAD_ENABLED,
    .gamepad_device                   = DEFAULT_GAMEPAD_DEVICE,
    .gamepad_mappings_file            = NULL,
    .on_launch                        = ON_LAUNCH_BLANK,
    .debug                            = false,
    .exe_path                         = NULL,
    .first_menu                       = NULL,
    .num_menus                        = 0,
    .clock_enabled                    = DEFAULT_CLOCK_ENABLED,
    .clock_show_date                  = DEFAULT_CLOCK_SHOW_DATE,
    .clock_alignment                  = DEFAULT_CLOCK_ALIGNMENT,
    .clock_font_path                  = NULL,
    .clock_margin_str[0]              = '\0',
    .clock_margin                     = -1,
    .clock_font_color.r               = DEFAULT_CLOCK_FONT_COLOR_R,
    .clock_font_color.g               = DEFAULT_CLOCK_FONT_COLOR_G,
    .clock_font_color.b               = DEFAULT_CLOCK_FONT_COLOR_B,
    .clock_font_color.a               = DEFAULT_CLOCK_FONT_COLOR_A,
    .clock_shadows                    = DEFAULT_CLOCK_SHADOWS,
    .clock_shadow_color.r             = DEFAULT_CLOCK_SHADOW_COLOR_R,
    .clock_shadow_color.g             = DEFAULT_CLOCK_SHADOW_COLOR_G,
    .clock_shadow_color.b             = DEFAULT_CLOCK_SHADOW_COLOR_B,
    .clock_shadow_color.a             = DEFAULT_CLOCK_SHADOW_COLOR_A,
    .clock_opacity[0]                 = '\0',
    .clock_font_size                  = DEFAULT_CLOCK_FONT_SIZE,
    .clock_time_format                = DEFAULT_CLOCK_TIME_FORMAT,
    .clock_date_format                = DEFAULT_CLOCK_DATE_FORMAT,
    .clock_include_weekday            = DEFAULT_CLOCK_INCLUDE_WEEKDAY,
    .slideshow_image_duration         = DEFAULT_SLIDESHOW_IMAGE_DURATION,
    .slideshow_transition_time        = DEFAULT_SLIDESHOW_TRANSITION_TIME
};

// Initialize default states
State state = { false };

// Global variables
SDL_Window *window                    = NULL;
SDL_Renderer *renderer                = NULL;
SDL_Texture *background_texture       = NULL;
SDL_Texture *background_overlay       = NULL;
Menu *default_menu                    = NULL;
Menu *current_menu                    = NULL;
Entry *current_entry                  = NULL;
Highlight *highlight                  = NULL;
Scroll *scroll                        = NULL;
Slideshow *slideshow                  = NULL;
Screensaver *screensaver              = NULL;
FILE *log_file                        = NULL;
Gamepad *gamepads                     = NULL;
GamepadControl *gamepad_controls      = NULL;
static bool gamepad_return_requires_b_release = false;
static bool resume_modal_active = false;
static int resume_modal_selected = 0;
static char resume_modal_token[38] = {0};
static SDL_Texture *resume_modal_labels[5] = {NULL};
static int resume_modal_label_width[5] = {0};
static int resume_modal_label_height[5] = {0};
Hotkey *hotkeys                       = NULL;
Clock *clk                            = NULL;
TTF_Font *clock_font                  = NULL;
SDL_Thread *Slideshowhread            = NULL;
SDL_Thread *clock_thread              = NULL;
SDL_Event event;
SDL_SysWMinfo wm_info;
SDL_DisplayMode display_mode;
TextInfo title_info;
SDL_Texture *activity_texture          = NULL;
SDL_Rect activity_text_rect            = {0};
bool activity_visible                  = false;

/* HOME-only, passive and noninteractive network status. No Fedora mutation. */
typedef enum {
    HOME_NETWORK_UNKNOWN = 0,
    HOME_NETWORK_DISCONNECTED,
    HOME_NETWORK_CONNECTED
} HomeNetworkStatus;
static HomeNetworkStatus home_network_status = HOME_NETWORK_UNKNOWN;
static char home_network_address[48] = "";
static SDL_Texture *home_network_texture = NULL;
static SDL_Rect home_network_text_rect = {0};
static bool home_network_probed = false;
static Uint32 home_network_last_probe = 0;
#define HOME_NETWORK_POLL_MS 5000U
int activity_level                     = 0;
Ticks ticks;
Geometry geo;
Uint32 refresh_period;
Uint32 delay_period;
Uint32 repeat_period;


// A function to initialize SDL
static void init_sdl()
{    
    // Set flags, hints
    Uint32 sdl_flags = SDL_INIT_VIDEO;
#ifdef __unix__
    SDL_SetHint(SDL_HINT_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR, "0");
#endif
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "1");
    SDL_SetHint(SDL_HINT_VIDEO_ALLOW_SCREENSAVER, config.inhibit_os_screensaver ? "0" : "1");
    if (config.gamepad_enabled)
        sdl_flags |= SDL_INIT_GAMECONTROLLER;

    // Initialize SDL
    if (SDL_Init(sdl_flags) < 0)
        log_fatal("Could not initialize SDL\n%s", SDL_GetError());

    SDL_GetDesktopDisplayMode(0, &display_mode);
#ifdef OPENHTPC_LAB_QA_CAPTURE
    if (getenv("OPENHTPC_LAB_QA_SOFTWARE") != NULL) {
        bool qa_4k = getenv("OPENHTPC_LAB_QA_4K") != NULL;
        display_mode.w = qa_4k ? 3840 : 1920;
        display_mode.h = qa_4k ? 2160 : 1080;
        display_mode.refresh_rate = 60;
    }
#endif
    geo.screen_width = display_mode.w;
    geo.screen_height = display_mode.h;
    refresh_period = 1000 / (Uint32) display_mode.refresh_rate;
    geo.screen_margin = (int) (SCREEN_MARGIN * (float) geo.screen_height);
}

// A function to create the window and renderer
static void create_window()
{
    Uint32 window_flags = SDL_WINDOW_FULLSCREEN_DESKTOP |
                          SDL_WINDOW_BORDERLESS | SDL_WINDOW_ALWAYS_ON_TOP;
    int win_w = 0, win_h = 0;
#ifdef OPENHTPC_LAB_QA_CAPTURE
    if (getenv("OPENHTPC_LAB_QA_SOFTWARE") != NULL) {
        window_flags = SDL_WINDOW_HIDDEN;
        win_w = geo.screen_width;
        win_h = geo.screen_height;
    }
#endif
    window = SDL_CreateWindow(PROJECT_NAME,
                 SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED,
                 win_w, win_h, window_flags);
    if (window == NULL)
        log_fatal("Could not create SDL Window\n%s", SDL_GetError());
    SDL_ShowCursor(SDL_DISABLE);

    // Create HW accelerated renderer, get screen resolution for geometry calculations
    Uint32 renderer_flags = SDL_RENDERER_ACCELERATED;
#ifdef OPENHTPC_LAB_QA_CAPTURE
    if (getenv("OPENHTPC_LAB_QA_SOFTWARE") != NULL) {
        renderer_flags = SDL_RENDERER_SOFTWARE;
    }
#endif
    if (!config.vsync) {
        if (config.fps_limit > MIN_FPS_LIMIT && config.fps_limit <= display_mode.refresh_rate)
            refresh_period = 1000 / (Uint32) config.fps_limit;
        else
            config.vsync = true;
    }
    if (config.vsync) {
        refresh_period = 1000 / (Uint32) display_mode.refresh_rate;
        renderer_flags |= SDL_RENDERER_PRESENTVSYNC;
    }
    if (config.gamepad_enabled) {
        delay_period = GAMEPAD_REPEAT_DELAY / refresh_period;
        repeat_period = GAMEPAD_REPEAT_INTERVAL / refresh_period;
        if (!repeat_period)
            repeat_period = 1;
    }
    if (slideshow != NULL)
        slideshow->transition_change_rate = 255.0f / ((float) config.slideshow_transition_time / (float) refresh_period);

    renderer = SDL_CreateRenderer(window, -1, renderer_flags);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (renderer == NULL)
        log_fatal("Could not initialize renderer\n%s", SDL_GetError());

    // Set background color
    set_draw_color();

#ifdef _WIN32
    SDL_VERSION(&wm_info.version);
    SDL_GetWindowWMInfo(window, &wm_info);
    if (config.background_mode == BACKGROUND_TRANSPARENT)
        make_window_transparent();
#endif
}

// A function to initialize the SDL_image library
static void init_sdl_image()
{
    int img_flags = IMG_INIT_PNG | IMG_INIT_JPG | IMG_INIT_WEBP;
    if (!(IMG_Init(img_flags) & img_flags))
        log_fatal("Could not initialize SDL_image\n%s", IMG_GetError());
}

// A function to set the color of the renderer
void set_draw_color()
{
    SDL_Color *color = NULL;
    if (config.background_mode == BACKGROUND_COLOR)
        color = &config.background_color;
    else if (config.background_mode == BACKGROUND_TRANSPARENT)
        color = &config.chroma_key_color;

    if (color == NULL)
        SDL_SetRenderDrawColor(renderer, 0xFF, 0xFF, 0xFF, 0xFF);
    else
        SDL_SetRenderDrawColor(renderer,
            color->r,
            color->g,
            color->b,
            color->a
        );
}

// A function to initialize SDL's TTF subsystem
static void init_sdl_ttf()
{
    if (TTF_Init() == -1)
        log_fatal("Could not initialize SDL_ttf\n%s", TTF_GetError());
    
    title_info = (TextInfo) { 
        .font_size = (int) config.title_font_size,
        .shadow = config.title_shadows,
        .font_path = &config.title_font_path,
        .fallback_font_path = &config.title_fallback_font_path,
        .max_width = config.icon_size,
        .oversize_mode = config.title_oversize_mode,
        .color = &config.title_font_color
    };
    if (config.title_shadows) {
        title_info.shadow_color = &config.title_shadow_color;
        calculate_shadow_alpha(title_info);
    }
    else
        title_info.shadow_color = NULL;

    int error = load_font(&title_info, FILENAME_DEFAULT_FONT);
    if (error)
        log_fatal("Could not load title font");
    geo.font_height = config.titles_enabled ? TTF_FontHeight(title_info.font) : 0;
}

// A function to close subsystems and free memory before quitting
static void cleanup()
{
    // Wait until all threads have completed
    SDL_WaitThread(Slideshowhread, NULL);
    SDL_WaitThread(clock_thread, NULL);
    
    if (home_network_texture != NULL) {
        SDL_DestroyTexture(home_network_texture);
        home_network_texture = NULL;
    }

    // Destroy renderer-owned live activity texture before the renderer.
    if (activity_texture != NULL) {
        SDL_DestroyTexture(activity_texture);
        activity_texture = NULL;
    }

    for (Menu *m = config.first_menu; m != NULL; m = m->next)
        if (m->media_wall_initialized) free_media_wall(m);

    close_resume_modal();

    // Destroy renderer and window
    if (renderer != NULL) {
        SDL_DestroyRenderer(renderer);
        renderer = NULL;
    }
    if (window != NULL) {
        SDL_DestroyWindow(window);
        window = NULL;
    }

    // Quit subsystems
    SDL_Quit();
    IMG_Quit();
    TTF_Quit();
    quit_svg();
    if (config.background_mode == BACKGROUND_SLIDESHOW)
        quit_slideshow();

    // Close log file if open
    if (log_file != NULL)
        fclose(log_file);

    // Free dynamically allocated memory
    free(config.default_menu);
    free(config.background_image);
    free(config.title_font_path);
    free(config.title_fallback_font_path);
    free(config.exe_path);
    free(config.slideshow_directory);
    free(config.clock_font_path);
    free(config.gamepad_mappings_file);
    free(config.startup_cmd);
    free(config.quit_cmd);
    free(config.live_activity_state);
    free(highlight);
    free(scroll);
    free(screensaver);
    free(clk);

    // Free menu and entry linked lists
    Entry *entry = NULL;
    Entry *tmp_entry = NULL;
    Menu *menu = config.first_menu;
    Menu *tmp_menu = NULL;
    for (size_t i = 0; i < config.num_menus; i++) {
        free_menu_detail(menu);
        free(menu->name);
        entry = menu->first_entry;
        for(size_t j = 0; j < menu->num_entries; j++) {
            free(entry->title);
            free(entry->icon_path);
            free(entry->icon_selected_path);
            free(entry->cmd);
            tmp_entry = entry;
            entry = entry->next;
            free(tmp_entry);
        }
        tmp_menu = menu;
        menu = menu->next;
        free(tmp_menu);
    }

    // Free hotkey linked list
    Hotkey *tmp_hotkey = NULL;
    for(Hotkey *i = hotkeys; i != NULL; i = i->next) {
        free(tmp_hotkey);
        free(i->cmd);
        tmp_hotkey = i;
    }
    free(tmp_hotkey);

    // Free gamepad control linked list
    GamepadControl *tmp_gamepad = NULL;
    for (GamepadControl *i = gamepad_controls; i != NULL; i = i->next) {
        free(tmp_gamepad);
        free(i->cmd);
        tmp_gamepad = i;
    }
    free(tmp_gamepad);

    if (config.gamepad_enabled)
        disconnect_gamepad(-1, false, true);
}

// =========================================================
// OPENHTPC_MEDIA_SIDEBAR_V011
// =========================================================

static bool is_media_sidebar(void)
{
    return (
        current_menu != NULL
        &&
        current_menu->name != NULL
        &&
        strcmp(
            current_menu->name,
            "MediaSidebar"
        ) == 0
    );
}

static bool is_movie_detail(const Menu *menu)
{
    if (menu == NULL) return false;
    if (menu->layout == LAYOUT_MOVIE_DETAIL) return true;
    if (menu->name != NULL && strncmp(menu->name, "MEDIA_D", 7) == 0) return true;
    return false;
}

static bool is_media_list(void)
{
    return current_menu != NULL && current_menu->name != NULL &&
        strncmp(current_menu->name, "MEDIA", 5) == 0 &&
        !is_movie_detail(current_menu);
}

static bool is_media_wall(const Menu *menu)
{
    return menu != NULL && menu->layout == LAYOUT_MEDIA_WALL;
}

static bool __attribute__((unused)) is_system_dashboard(void)
{
    /* Legacy Phase A reference: is_system_dashboard() (geo.screen_width * 96). Replaced by is_system_subpage. */
    return false;
}

static bool is_menu_system_subpage(const Menu *menu)
{
    if (menu == NULL || menu->name == NULL)
        return false;
    const char *name = menu->name;
    return (strcmp(name, "SYSTEM_OVERVIEW") == 0 ||
            strcmp(name, "SYSTEM_CODECS") == 0 ||
            strcmp(name, "SYSTEM_DISPLAY") == 0 ||
            strcmp(name, "SYSTEM_AUDIO") == 0 ||
            strcmp(name, "AUDIO_OUTPUT_TARGET") == 0 ||
            strcmp(name, "AUDIO_OUTPUT_MODE") == 0 ||
            strcmp(name, "SYSTEM_MEDIA_OPTICAL") == 0 ||
            strcmp(name, "SYSTEM_EXTENSIONS") == 0 ||
            strcmp(name, "SYSTEM_METADATA") == 0 ||
            strcmp(name, "SYSTEM_TMDB") == 0 ||
            strcmp(name, "SYSTEM_PROCESSING") == 0 ||
            strcmp(name, "SYSTEM_PLAYBACK") == 0 ||
            strcmp(name, "PLAYBACK_VIDEO") == 0 ||
            strcmp(name, "PLAYBACK_AUDIO") == 0 ||
            strcmp(name, "PLAYBACK_SUBTITLES") == 0 ||
            strcmp(name, "DVD_VIDEO_MODE") == 0 ||
            strcmp(name, "SYSTEM_DIAGNOSTICS") == 0 ||
            strcmp(name, "SYSTEM_TECHNICAL") == 0 ||
            strcmp(name, "SYSTEM_ABOUT") == 0);
}

static bool is_system_subpage(void)
{
    return is_menu_system_subpage(current_menu);
}

static bool is_system_root(void)
{
    return (
        current_menu != NULL &&
        current_menu->name != NULL &&
        strcmp(current_menu->name, "SYSTEME") == 0
    );
}

static unsigned int menu_page_size(const Menu *menu)
{
    /* SYSTEME is a trusted Core-generated vertical rail.  Its compact
     * geometry is designed to keep every category, including RETOUR, on one
     * page without changing the density of MEDIA or any other menu. */
    if (menu != NULL && menu->name != NULL && strcmp(menu->name, "SYSTEME") == 0)
        return menu->num_entries;
    return config.max_buttons;
}

static bool is_menu_disc_sheet(const Menu *menu)
{
    return menu != NULL && menu->name != NULL && strcmp(menu->name, "DISQUE") == 0;
}

static bool is_disc_sheet(void)
{
    return current_menu != NULL && current_menu->name != NULL && strcmp(current_menu->name, "DISQUE") == 0;
}

static bool is_menu_disc_ambiguous(const Menu *menu)
{
    if (!is_menu_disc_sheet(menu) || menu == NULL) return false;
    for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
        if (e->cmd != NULL && strstr(e->cmd, "openhtpc-bind-disc") != NULL) {
            return true;
        }
    }
    return false;
}

static bool is_disc_ambiguous(void)
{
    return is_menu_disc_ambiguous(current_menu);
}

static bool is_menu_disc_action_sheet(const Menu *menu)
{
    return is_menu_disc_sheet(menu) && !is_menu_disc_ambiguous(menu);
}

static bool is_disc_action_sheet(void)
{
    return is_menu_disc_action_sheet(current_menu);
}


// =========================================================
// OPENHTPC HOME BUTTON CARDS V01
// =========================================================

static bool is_home_menu(void)
{
    return (
        current_menu != NULL
        &&
        current_menu->name != NULL
        &&
        (
            strcmp(current_menu->name, "OPENHTPC") == 0
            || strcmp(current_menu->name, "Accueil") == 0
        )
    );
}


static void fill_rounded_rect(
    SDL_Renderer *target,
    const SDL_Rect *rect,
    int radius,
    SDL_Color color
)
{
    if (rect == NULL || rect->w <= 0 || rect->h <= 0)
        return;

    int r = radius;
    if (r > rect->w / 2) r = rect->w / 2;
    if (r > rect->h / 2) r = rect->h / 2;
    if (r < 1) r = 1;

    SDL_SetRenderDrawBlendMode(target, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(target, color.r, color.g, color.b, color.a);

    SDL_Rect middle = {
        rect->x + r,
        rect->y,
        rect->w - 2 * r,
        rect->h
    };
    SDL_Rect center = {
        rect->x,
        rect->y + r,
        rect->w,
        rect->h - 2 * r
    };
    SDL_RenderFillRect(target, &middle);
    SDL_RenderFillRect(target, &center);

    for (int y = 0; y < r; y++) {
        int dy = r - y;
        int dx = (int) sqrt((double) (r * r - dy * dy));
        SDL_RenderDrawLine(
            target,
            rect->x + r - dx,
            rect->y + y,
            rect->x + rect->w - r + dx - 1,
            rect->y + y
        );
        SDL_RenderDrawLine(
            target,
            rect->x + r - dx,
            rect->y + rect->h - y - 1,
            rect->x + rect->w - r + dx - 1,
            rect->y + rect->h - y - 1
        );
    }
}

#define MEDIA_WALL_TEXTURE_LIMIT 20U
enum {HEAD_OPEN, HEAD_HTPC, HEAD_FILMS, HEAD_SERIES, HEAD_DISQUE,
      HEAD_DOSSIERS, HEAD_STATUS, HEAD_CLOCK, HEAD_DATE,
      HEAD_ELEMENT_COUNT};
static unsigned long media_wall_texture_clock = 0;

static Entry *media_wall_entry(Menu *menu, MediaWallRow row, size_t position)
{
    size_t index = media_wall_manifest_index(&menu->media_wall, row, position);
    if (index == SIZE_MAX || index >= menu->num_entries)
        return NULL;
    return menu->media_wall_entries[index];
}

static bool media_wall_resolve_technical(const Entry *selected,
                                         MediaWallTechnical *technical)
{
    if (selected == NULL || selected->cmd == NULL || technical == NULL)
        return false;
    const char *prefix = ":submenu ";
    if (strncmp(selected->cmd, prefix, strlen(prefix)) != 0)
        return false;
    const char *name = selected->cmd + strlen(prefix);
    if (strncmp(name, "MEDIA_D", 7) != 0 || strlen(name) > 50 ||
        strchr(name, ' ') != NULL)
        return false;
    Menu *detail = get_menu(name);
    if (detail == NULL || detail->layout != LAYOUT_MOVIE_DETAIL)
        return false;
    bool has_technical = media_wall_parse_core_metadata(
        detail->detail_metadata, technical);
    technical->source_format = media_wall_parse_source_format(
        detail->detail_source_colorimetry);
    return has_technical ||
           technical->source_format != MEDIA_WALL_FORMAT_UNKNOWN;
}

static void update_media_wall_footer(Menu *menu)
{
    if (menu->media_wall_footer_title != NULL) {
        SDL_DestroyTexture(menu->media_wall_footer_title);
        menu->media_wall_footer_title = NULL;
    }
    if (menu->media_wall_footer_meta != NULL) {
        SDL_DestroyTexture(menu->media_wall_footer_meta);
        menu->media_wall_footer_meta = NULL;
    }
    for (size_t i = 0; i < 4; i++) {
        if (menu->media_wall_badge_text[i] != NULL) {
            SDL_DestroyTexture(menu->media_wall_badge_text[i]);
            menu->media_wall_badge_text[i] = NULL;
        }
    }
    Entry *selected = media_wall_entry(menu, menu->media_wall.row,
        menu->media_wall.selected[menu->media_wall.row]);
    if (selected == NULL)
        return;
    current_entry = selected;
    TextInfo info = title_info;
    if (menu->media_wall_font != NULL) {
        info.font = menu->media_wall_font;
        info.font_size = menu->media_wall_font_size;
    }
    info.max_width = (geo.screen_width * 23) / 100;
    info.oversize_mode = OVERSIZE_SHRINK;
    int h = 0;
    char clean_title[1024];
    unsigned int year = 0;
    bool has_year = media_wall_title_and_year(selected->title,
                                              clean_title, sizeof(clean_title),
                                              &year);
    MediaWallTechnical technical = {0};
    bool has_technical = media_wall_resolve_technical(selected, &technical);
    menu->media_wall_badge_source_format = technical.source_format;
    menu->media_wall_footer_title = render_text_texture(
        has_year ? clean_title : selected->title, &info,
        &menu->media_wall_footer_title_rect, &h);
    menu->media_wall_footer_title_rect.x = (geo.screen_width * 6) / 100;
    menu->media_wall_footer_title_rect.y = (geo.screen_height * 915) / 1000;
    if (has_year) {
        char meta[96];
        if (has_technical && technical.duration[0] != '\0')
            snprintf(meta, sizeof(meta), "%u  ·  %s", year, technical.duration);
        else
            snprintf(meta, sizeof(meta), "%u  ·  FILM", year);
        SDL_Color secondary = {0x8C, 0x9A, 0xB5, 255};
        TextInfo meta_info = info;
        if (menu->media_wall_meta_font != NULL) {
            meta_info.font = menu->media_wall_meta_font;
            meta_info.font_size = (geo.screen_height * 18) / 1080;
            if (meta_info.font_size < 18)
                meta_info.font_size = 18;
        }
        meta_info.color = &secondary;
        meta_info.max_width = geo.screen_width * 24 / 100;
        menu->media_wall_footer_meta = render_text_texture(
            meta, &meta_info, &menu->media_wall_footer_meta_rect, &h);
        menu->media_wall_footer_meta_rect.x = (geo.screen_width * 6) / 100;
        menu->media_wall_footer_meta_rect.y = (geo.screen_height * 950) / 1000;
    }
    if (has_technical) {
        const char *source_label = media_wall_source_format_label(
            technical.source_format);
        const char *badges[] = {
            technical.resolution, technical.video_codec, technical.audio,
            source_label != NULL ? source_label : ""
        };
        TextInfo badge_info = info;
        badge_info.color = &(SDL_Color){0xD9, 0xE7, 0xFF, 255};
        if (menu->media_wall_meta_font != NULL) {
            badge_info.font = menu->media_wall_meta_font;
            badge_info.font_size = geo.screen_height / 60;
        }
        badge_info.max_width = geo.screen_width * 15 / 100;
        badge_info.oversize_mode = OVERSIZE_SHRINK;
        int pad_x = geo.screen_height * 13 / 1080;
        int pad_y = geo.screen_height * 8 / 1080;
        int gap_x = geo.screen_width * 8 / 1000;
        int x = geo.screen_width * 30 / 100;
        for (size_t i = 0; i < 4; i++) {
            if (badges[i][0] == '\0')
                continue;
            int text_h = 0;
            SDL_Rect text_rect = {0};
            SDL_Texture *texture = render_text_texture(badges[i], &badge_info,
                                                       &text_rect, &text_h);
            if (texture == NULL)
                continue;
            int card_w = text_rect.w + pad_x * 2;
            if (x + card_w > geo.screen_width * 72 / 100) {
                SDL_DestroyTexture(texture);
                break;
            }
            menu->media_wall_badge_text[i] = texture;
            menu->media_wall_badge_rect[i] = (SDL_Rect){
                x, geo.screen_height * 925 / 1000 - pad_y,
                card_w, text_rect.h + 2 * pad_y
            };
            menu->media_wall_badge_text_rect[i] = (SDL_Rect){
                x + pad_x, geo.screen_height * 925 / 1000, text_rect.w, text_rect.h
            };
            x += card_w + gap_x;
        }
    }
}

static void update_media_wall_footer_help(Menu *menu)
{
    if (menu->media_wall_footer_help != NULL) {
        SDL_DestroyTexture(menu->media_wall_footer_help);
        menu->media_wall_footer_help = NULL;
    }
    TextInfo info = title_info;
    if (menu->media_wall_font != NULL) {
        info.font = menu->media_wall_font;
        info.font_size = menu->media_wall_font_size;
    }
    info.max_width = geo.screen_width * 54 / 100;
    info.oversize_mode = OVERSIZE_SHRINK;
    int h = 0;
    const char *help = menu->media_wall.tab_focused
        ? "A  OUVRIR    BAS  AFFICHES    B  RETOUR"
        : "HAUT  ONGLETS    A  FICHE    B  RETOUR";
    menu->media_wall_footer_help = render_text_texture(help, &info,
        &menu->media_wall_footer_help_rect, &h);
    menu->media_wall_footer_help_rect.x = geo.screen_width -
        geo.screen_width * 6 / 100 - menu->media_wall_footer_help_rect.w;
    menu->media_wall_footer_help_rect.y = geo.screen_height * 92 / 100;
}

static bool prepare_media_wall(Menu *menu)
{
    if (menu == NULL || menu->num_entries == 0)
        return false;
    if (menu->media_wall_initialized)
        return true;

    menu->media_wall_entries = calloc(menu->num_entries,
                                       sizeof(*menu->media_wall_entries));
    const char **titles = calloc(menu->num_entries, sizeof(*titles));
    if (menu->media_wall_entries == NULL || titles == NULL) {
        free(menu->media_wall_entries);
        menu->media_wall_entries = NULL;
        free(titles);
        return false;
    }
    size_t i = 0;
    for (Entry *entry = menu->first_entry; entry != NULL && i < menu->num_entries;
         entry = entry->next, i++) {
        menu->media_wall_entries[i] = entry;
        titles[i] = entry->title;
    }

    MediaWallGeometry wall;
    if (!media_wall_geometry(geo.screen_width, geo.screen_height, &wall)) {
        free(titles);
        return false;
    }
    bool ok = media_wall_init(&menu->media_wall, titles, menu->num_entries,
                              wall.viewport);
    free(titles);
    if (!ok)
        return false;

    /* Use screen-relative typography for TV viewing; config FontSize=24
     * from headless fixture is otherwise unreadable on a 4K television. */
    int wall_font_size = geo.screen_height / 44;
    if (wall_font_size < 24) wall_font_size = 24;
    if (wall_font_size > 64) wall_font_size = 64;
    const char *wall_font_path = config.title_font_path;
    if (wall_font_path != NULL) {
        menu->media_wall_font = TTF_OpenFont(wall_font_path, wall_font_size);
        if (menu->media_wall_font != NULL)
            menu->media_wall_font_size = wall_font_size;
        int meta_font_size = geo.screen_height / 60;
        if (meta_font_size < 18) meta_font_size = 18;
        if (meta_font_size > 42) meta_font_size = 42;
        menu->media_wall_meta_font = TTF_OpenFont(wall_font_path,
                                                   meta_font_size);
    }
    TextInfo label_info = title_info;
    if (menu->media_wall_font != NULL) {
        label_info.font = menu->media_wall_font;
        label_info.font_size = menu->media_wall_font_size;
    }
    label_info.max_width = (geo.screen_width * 50) / 100;
    label_info.oversize_mode = OVERSIZE_SHRINK;
    int h = 0;
    menu->media_wall_recent_label = render_text_texture("Récemment ajoutés",
        &label_info, &menu->media_wall_recent_label_rect, &h);
    menu->media_wall_recent_label_rect.x = (geo.screen_width * 6) / 100;
    menu->media_wall_recent_label_rect.y = wall.recent_label_y;
    menu->media_wall_all_label = render_text_texture("Tous les films A-Z",
        &label_info, &menu->media_wall_all_label_rect, &h);
    menu->media_wall_all_label_rect.x = (geo.screen_width * 6) / 100;
    menu->media_wall_all_label_rect.y = wall.all_label_y;
    update_media_wall_footer_help(menu);
    /* Maquette Médiathèque V2: header and a quiet status strip.
     * Only the REAL number of works in the current view is displayed.
     * We never reproduce mock-up catalogue counters or fake PLAY actions. */
    SDL_Color white = {0xE8, 0xEE, 0xF8, 255};
    SDL_Color blue = {0x3D, 0x8B, 0xFF, 255};
    SDL_Color muted = {0x8C, 0x9A, 0xB5, 255};
    TextInfo header = label_info;
    header.color = &white;
    int scale_y = geo.screen_height;
    menu->media_wall_header[HEAD_OPEN] = render_text_texture("OPEN", &header,
        &menu->media_wall_header_rect[HEAD_OPEN], &h);
    menu->media_wall_header_rect[HEAD_OPEN].x = geo.screen_width * 4 / 100;
    menu->media_wall_header_rect[HEAD_OPEN].y = 39 * scale_y / 1080;
    header.color = &blue;
    menu->media_wall_header[HEAD_HTPC] = render_text_texture("HTPC", &header,
        &menu->media_wall_header_rect[HEAD_HTPC], &h);
    menu->media_wall_header_rect[HEAD_HTPC].x =
        menu->media_wall_header_rect[HEAD_OPEN].x +
        menu->media_wall_header_rect[HEAD_OPEN].w;
    menu->media_wall_header_rect[HEAD_HTPC].y = 39 * scale_y / 1080;
    header.color = &white;
    menu->media_wall_header[HEAD_FILMS] = render_text_texture("FILMS", &header,
        &menu->media_wall_header_rect[HEAD_FILMS], &h);
    menu->media_wall_header_rect[HEAD_FILMS].x = geo.screen_width * 14 / 100;
    menu->media_wall_header_rect[HEAD_FILMS].y = 44 * scale_y / 1080;
    header.color = &(SDL_Color){0x62, 0x6F, 0x86, 255};
    menu->media_wall_header[HEAD_SERIES] = render_text_texture("SÉRIES", &header,
        &menu->media_wall_header_rect[HEAD_SERIES], &h);
    menu->media_wall_header_rect[HEAD_SERIES].x = geo.screen_width * 22 / 100;
    menu->media_wall_header_rect[HEAD_SERIES].y = 44 * scale_y / 1080;
    header.color = &muted;
    menu->media_wall_header[HEAD_DISQUE] = render_text_texture("DISQUE", &header,
        &menu->media_wall_header_rect[HEAD_DISQUE], &h);
    menu->media_wall_header_rect[HEAD_DISQUE].x = geo.screen_width * 31 / 100;
    menu->media_wall_header_rect[HEAD_DISQUE].y = 44 * scale_y / 1080;
    menu->media_wall_header[HEAD_DOSSIERS] = render_text_texture("DOSSIERS", &header,
        &menu->media_wall_header_rect[HEAD_DOSSIERS], &h);
    menu->media_wall_header_rect[HEAD_DOSSIERS].x = geo.screen_width * 40 / 100;
    menu->media_wall_header_rect[HEAD_DOSSIERS].y = 44 * scale_y / 1080;
    char summary[128];
    snprintf(summary, sizeof(summary), "MÉDIATHÈQUE   ·   %u films identifiés",
             menu->num_entries);
    header.color = &white;
    menu->media_wall_header[HEAD_STATUS] = render_text_texture(summary, &header,
        &menu->media_wall_header_rect[HEAD_STATUS], &h);
    menu->media_wall_header_rect[HEAD_STATUS].x = geo.screen_width * 6 / 100;
    menu->media_wall_header_rect[HEAD_STATUS].y = 134 * scale_y / 1080;
    menu->media_wall_clock_key = -1;
    menu->media_wall_focus_started = SDL_GetTicks();
    menu->media_wall_initialized = true;
    update_media_wall_footer(menu);
    return true;
}

static void free_media_wall(Menu *menu)
{
    if (menu == NULL)
        return;
    media_wall_destroy(&menu->media_wall);
    free(menu->media_wall_entries);
    menu->media_wall_entries = NULL;
    SDL_Texture **textures[] = {
        &menu->media_wall_recent_label, &menu->media_wall_all_label,
        &menu->media_wall_footer_title, &menu->media_wall_footer_meta,
        &menu->media_wall_footer_help,
        &menu->media_wall_badge_text[0], &menu->media_wall_badge_text[1],
        &menu->media_wall_badge_text[2],
        &menu->media_wall_badge_text[3]
    };
    for (size_t i = 0; i < sizeof(textures) / sizeof(textures[0]); i++) {
        if (*textures[i] != NULL) {
            SDL_DestroyTexture(*textures[i]);
            *textures[i] = NULL;
        }
    }
    if (menu->media_wall_font != NULL) {
        TTF_CloseFont(menu->media_wall_font);
        menu->media_wall_font = NULL;
    }
    if (menu->media_wall_meta_font != NULL) {
        TTF_CloseFont(menu->media_wall_meta_font);
        menu->media_wall_meta_font = NULL;
    }
    menu->media_wall_font_size = 0;
    for (size_t i = 0; i < HEAD_ELEMENT_COUNT; i++) {
        if (menu->media_wall_header[i] != NULL) {
            SDL_DestroyTexture(menu->media_wall_header[i]);
            menu->media_wall_header[i] = NULL;
        }
    }
    menu->media_wall_initialized = false;
}

static bool media_wall_position_visible(const Menu *menu, size_t manifest_index)
{
    for (int row = 0; row < MEDIA_WALL_ROWS; row++) {
        size_t start = menu->media_wall.scroll[row];
        size_t count = media_wall_row_count(&menu->media_wall, (MediaWallRow) row);
        size_t end = start + menu->media_wall.viewport;
        if (end > count) end = count;
        for (size_t pos = start; pos < end; pos++) {
            if (media_wall_manifest_index(&menu->media_wall,
                    (MediaWallRow) row, pos) == manifest_index)
                return true;
        }
    }
    return false;
}

static void media_wall_bound_cache(Menu *menu)
{
    size_t loaded = 0;
    for (size_t i = 0; i < menu->num_entries; i++)
        if (menu->media_wall_entries[i]->icon != NULL) loaded++;
    while (loaded > MEDIA_WALL_TEXTURE_LIMIT) {
        Entry *oldest = NULL;
        size_t oldest_index = 0;
        for (size_t i = 0; i < menu->num_entries; i++) {
            Entry *entry = menu->media_wall_entries[i];
            if (entry->icon != NULL && !media_wall_position_visible(menu, i) &&
                (oldest == NULL || entry->texture_use < oldest->texture_use)) {
                oldest = entry;
                oldest_index = i;
            }
        }
        (void) oldest_index;
        if (oldest == NULL) break;
        SDL_DestroyTexture(oldest->icon);
        oldest->icon = NULL;
        loaded--;
    }
}

static void draw_media_wall_row(Menu *menu, MediaWallRow row, int y)
{
    size_t start = menu->media_wall.scroll[row];
    size_t count = media_wall_row_count(&menu->media_wall, row);
    size_t visible = count - start;
    if (visible > menu->media_wall.viewport) visible = menu->media_wall.viewport;
    MediaWallGeometry wall;
    if (!media_wall_geometry(geo.screen_width, geo.screen_height, &wall))
        return;
    int poster_h = wall.poster_h;
    int poster_w = wall.poster_w;
    int gap = wall.gap;
    int total_w = (int) visible * poster_w + ((int) visible - 1) * gap;
    int x0 = (geo.screen_width - total_w) / 2;

    /* Two passes guarantee that the focused poster is composited last. */
    for (int focus_pass = 0; focus_pass < 2; focus_pass++) {
        for (size_t slot = 0; slot < visible; slot++) {
            size_t position = start + slot;
            Entry *entry = media_wall_entry(menu, row, position);
            if (entry == NULL) continue;
            bool selected = !menu->media_wall.tab_focused &&
                            menu->media_wall.row == row &&
                            menu->media_wall.selected[row] == position;
            if ((selected ? 1 : 0) != focus_pass) continue;
            if (entry->icon == NULL)
                entry->icon = load_texture_from_file(entry->icon_path);
            entry->texture_use = ++media_wall_texture_clock;

            SDL_Rect poster = { x0 + (int) slot * (poster_w + gap), y,
                                poster_w, poster_h };
            if (selected) {
                /* SDL-native 180 ms ease-out focus. The grid never reflows.
                 * The poster's bottom edge remains anchored while it rises. */
                unsigned int progress = media_wall_focus_progress(
                    SDL_GetTicks() - menu->media_wall_focus_started);
#ifdef OPENHTPC_LAB_QA_CAPTURE
                if (getenv("OPENHTPC_LAB_QA_SCENARIO") != NULL &&
                    (lab_qa_loop == 35 || lab_qa_loop == 36 ||
                     lab_qa_loop == 40 || lab_qa_loop == 45 ||
                     lab_qa_loop == 60)) {
                    fprintf(stderr, "LAB_QA_FOCUS step=%u progress=%u row=%d slot=%zu\n",
                            lab_qa_loop, progress, (int) row, slot);
                }
#endif
                int grow_w = (int) (((int64_t) poster.w * 14 * progress) / 100000);
                int grow_h = (int) (((int64_t) poster.h * 14 * progress) / 100000);
                int lift = (int) (((int64_t) geo.screen_height * 16 * progress) /
                                  1080000);
                poster.x -= grow_w / 2;
                poster.y -= grow_h + lift;
                poster.w += grow_w;
                poster.h += grow_h;
                SDL_Rect shadow = {poster.x - 8, poster.y + 9,
                                   poster.w + 16, poster.h + 17};
                fill_rounded_rect(renderer, &shadow, 12,
                                  (SDL_Color){0, 0, 0, 155});
                SDL_BlendMode previous_blend;
                SDL_GetRenderDrawBlendMode(renderer, &previous_blend);
                SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
                /* Soft blue glow, then the crisp 3px #3D8BFF border. */
                for (int radius = 12; radius >= 3; radius -= 3) {
                    int strength = (36 - radius) * (int) progress / 1000;
                    SDL_SetRenderDrawColor(renderer, 0x3D, 0x8B, 0xFF,
                                           (Uint8) strength);
                    SDL_Rect glow = {poster.x - radius, poster.y - radius,
                        poster.w + 2 * radius, poster.h + 2 * radius};
                    SDL_RenderDrawRect(renderer, &glow);
                }
                SDL_SetRenderDrawColor(renderer, 0x3D, 0x8B, 0xFF, 255);
                for (int border = 1; border <= 3; border++) {
                    SDL_Rect outline = {poster.x - border, poster.y - border,
                        poster.w + 2 * border, poster.h + 2 * border};
                    SDL_RenderDrawRect(renderer, &outline);
                }
                SDL_SetRenderDrawBlendMode(renderer, previous_blend);
            }
            if (entry->icon != NULL) {
                int shade = selected ? 255 :
                    (menu->media_wall.row == row ? 140 : 180);
                SDL_SetTextureColorMod(entry->icon, shade, shade, shade);
                SDL_SetTextureAlphaMod(entry->icon, 255);
                int tex_w = 0, tex_h = 0;
                MediaWallCrop crop;
                if (SDL_QueryTexture(entry->icon, NULL, NULL,
                                     &tex_w, &tex_h) == 0 &&
                    media_wall_cover_crop(tex_w, tex_h, poster.w, poster.h, &crop)) {
                    SDL_Rect src = {crop.x, crop.y, crop.w, crop.h};
                    SDL_RenderCopy(renderer, entry->icon, &src, &poster);
                } else {
                    SDL_RenderCopy(renderer, entry->icon, NULL, &poster);
                }
                SDL_SetTextureColorMod(entry->icon, 255, 255, 255);
                SDL_SetTextureAlphaMod(entry->icon, 255);
            } else {
                fill_rounded_rect(renderer, &poster, 8, (SDL_Color){28, 34, 46, 255});
            }
        }
    }
}

/* French date/time, refreshed only when the minute changes. */
static void update_media_wall_clock(Menu *menu)
{
    time_t timestamp = time(NULL);
    struct tm local;
    if (localtime_r(&timestamp, &local) == NULL)
        return;
    int key = ((local.tm_year * 366 + local.tm_yday) * 24 +
               local.tm_hour) * 60 + local.tm_min;
    if (menu->media_wall_clock_key == key)
        return;
    menu->media_wall_clock_key = key;
    const char *days[] = {"dim.", "lun.", "mar.", "mer.",
                          "jeu.", "ven.", "sam."};
    const char *months[] = {"janv.", "févr.", "mars", "avr.",
                            "mai", "juin", "juil.", "août",
                            "sept.", "oct.", "nov.", "déc."};
    char clock[16], date[40];
    snprintf(clock, sizeof(clock), "%02d:%02d", local.tm_hour, local.tm_min);
    snprintf(date, sizeof(date), "%s %d %s", days[local.tm_wday],
             local.tm_mday, months[local.tm_mon]);
    TextInfo info = title_info;
    if (menu->media_wall_font != NULL) {
        info.font = menu->media_wall_font;
        info.font_size = menu->media_wall_font_size;
    }
    info.max_width = geo.screen_width / 4;
    SDL_Color white = {0xE8, 0xEE, 0xF8, 255};
    SDL_Color muted = {0x8C, 0x9A, 0xB5, 255};
    info.color = &white;
    for (int i = HEAD_CLOCK; i <= HEAD_DATE; i++) {
        if (menu->media_wall_header[i] != NULL) {
            SDL_DestroyTexture(menu->media_wall_header[i]);
            menu->media_wall_header[i] = NULL;
        }
    }
    int h = 0;
    menu->media_wall_header[HEAD_CLOCK] = render_text_texture(clock, &info,
        &menu->media_wall_header_rect[HEAD_CLOCK], &h);
    menu->media_wall_header_rect[HEAD_CLOCK].x = geo.screen_width * 96 / 100 -
        menu->media_wall_header_rect[HEAD_CLOCK].w;
    menu->media_wall_header_rect[HEAD_CLOCK].y = geo.screen_height * 35 / 1080;
    info.color = &muted;
    menu->media_wall_header[HEAD_DATE] = render_text_texture(date, &info,
        &menu->media_wall_header_rect[HEAD_DATE], &h);
    menu->media_wall_header_rect[HEAD_DATE].x = geo.screen_width * 96 / 100 -
        menu->media_wall_header_rect[HEAD_DATE].w;
    menu->media_wall_header_rect[HEAD_DATE].y = geo.screen_height * 71 / 1080;
}

static void draw_media_wall(void)
{
    Menu *menu = current_menu;
    if (!prepare_media_wall(menu))
        return;
    MediaWallGeometry wall;
    if (!media_wall_geometry(geo.screen_width, geo.screen_height, &wall))
        return;
    SDL_Rect night = {0, 0, geo.screen_width, geo.screen_height};
    SDL_SetRenderDrawColor(renderer, 7, 11, 22, 255);
    SDL_RenderFillRect(renderer, &night);

    /* FILMS is the currently active section; controller Up transfers
     * focus into the masthead. A triggers only an existing registered menu.
     * SERIES is intentionally dimmed and never focusable. */
    for (int tab = MEDIA_WALL_TAB_FILMS; tab <= MEDIA_WALL_TAB_DOSSIERS; tab++) {
        if (tab == MEDIA_WALL_TAB_SERIES)
            continue;
        int index = HEAD_FILMS + tab;
        SDL_Rect text_rect = menu->media_wall_header_rect[index];
        SDL_Rect target = {
            text_rect.x - geo.screen_width / 110,
            text_rect.y - geo.screen_height / 105,
            text_rect.w + geo.screen_width / 55,
            text_rect.h + geo.screen_height / 55
        };
        bool active = tab == MEDIA_WALL_TAB_FILMS;
        bool focused = menu->media_wall.tab_focused &&
                       menu->media_wall.tab == (MediaWallTab) tab;
        if (active || focused) {
            fill_rounded_rect(renderer, &target, geo.screen_height / 130,
                (SDL_Color){15, 24, 48, 245});
            SDL_SetRenderDrawColor(renderer, 0x3D, 0x8B, 0xFF, 255);
            if (focused) {
                for (int edge = 0; edge < 3; edge++) {
                    SDL_Rect outline = {target.x - edge, target.y - edge,
                        target.w + 2 * edge, target.h + 2 * edge};
                    SDL_RenderDrawRect(renderer, &outline);
                }
            } else
                SDL_RenderDrawRect(renderer, &target);
        }
    }

    SDL_Rect status = {geo.screen_width * 4 / 100, wall.status_y,
                       geo.screen_width * 92 / 100, wall.status_h};
    fill_rounded_rect(renderer, &status, geo.screen_height / 120,
                      (SDL_Color){15, 24, 48, 255});
    SDL_SetRenderDrawColor(renderer, 28, 42, 74, 255);
    SDL_RenderDrawRect(renderer, &status);

    update_media_wall_clock(menu);
    for (size_t i = 0; i < HEAD_ELEMENT_COUNT; i++) {
        if (menu->media_wall_header[i] != NULL)
            SDL_RenderCopy(renderer, menu->media_wall_header[i], NULL,
                           &menu->media_wall_header_rect[i]);
    }
    if (menu->media_wall_recent_label != NULL)
        SDL_RenderCopy(renderer, menu->media_wall_recent_label, NULL,
                       &menu->media_wall_recent_label_rect);
    if (menu->media_wall_all_label != NULL)
        SDL_RenderCopy(renderer, menu->media_wall_all_label, NULL,
                       &menu->media_wall_all_label_rect);
    draw_media_wall_row(menu, MEDIA_WALL_RECENT, wall.recent_poster_y);
    draw_media_wall_row(menu, MEDIA_WALL_ALL, wall.all_poster_y);
    SDL_Rect footer = {0, wall.footer_y, geo.screen_width, wall.footer_h};
    SDL_SetRenderDrawColor(renderer, 8, 15, 28, 245);
    SDL_RenderFillRect(renderer, &footer);
    SDL_SetRenderDrawColor(renderer, 28, 42, 74, 255);
    SDL_RenderDrawLine(renderer, 0, wall.footer_y,
                       geo.screen_width, wall.footer_y);
    if (menu->media_wall_footer_title != NULL)
        SDL_RenderCopy(renderer, menu->media_wall_footer_title, NULL,
                       &menu->media_wall_footer_title_rect);
    if (menu->media_wall_footer_meta != NULL)
        SDL_RenderCopy(renderer, menu->media_wall_footer_meta, NULL,
                       &menu->media_wall_footer_meta_rect);
    for (size_t i = 0; i < 4; i++) {
        if (menu->media_wall_badge_text[i] == NULL)
            continue;
        SDL_Rect badge = menu->media_wall_badge_rect[i];
        SDL_Color fill = {17, 30, 51, 240};
        SDL_Color border = {57, 82, 121, 255};
        if (i == 3) {
            /* Format of file source: no claims about output/tone mapping. */
            switch (menu->media_wall_badge_source_format) {
                case MEDIA_WALL_FORMAT_DOLBY_VISION:
                    fill = (SDL_Color){52, 28, 80, 245};
                    border = (SDL_Color){172, 112, 233, 255};
                    break;
                case MEDIA_WALL_FORMAT_HDR10_PLUS:
                case MEDIA_WALL_FORMAT_HDR10:
                    fill = (SDL_Color){70, 48, 18, 245};
                    border = (SDL_Color){225, 171, 70, 255};
                    break;
                case MEDIA_WALL_FORMAT_HLG:
                    fill = (SDL_Color){20, 65, 57, 245};
                    border = (SDL_Color){80, 186, 164, 255};
                    break;
                default: break;
            }
        }
        fill_rounded_rect(renderer, &badge, geo.screen_height / 170, fill);
        SDL_SetRenderDrawColor(renderer, border.r, border.g, border.b, border.a);
        SDL_RenderDrawRect(renderer, &badge);
        SDL_RenderCopy(renderer, menu->media_wall_badge_text[i], NULL,
                       &menu->media_wall_badge_text_rect[i]);
    }
    if (menu->media_wall_footer_help != NULL)
        SDL_RenderCopy(renderer, menu->media_wall_footer_help, NULL,
                       &menu->media_wall_footer_help_rect);
    media_wall_bound_cache(menu);
}

/* Header navigation is a view of the existing CORE menus, not a new
 * media engine. Never create / invent an absent route or playback action. */
static void media_wall_activate_tab(void)
{
    if (!is_media_wall(current_menu) || !prepare_media_wall(current_menu) ||
        !current_menu->media_wall.tab_focused)
        return;
    MediaWallTab tab = current_menu->media_wall.tab;
    if (tab == MEDIA_WALL_TAB_FILMS) {
        (void) media_wall_move_vertical(&current_menu->media_wall, 1);
        current_menu->media_wall_focus_started = SDL_GetTicks();
        update_media_wall_footer(current_menu);
        update_media_wall_footer_help(current_menu);
        return;
    }
    const char *target = media_wall_tab_target(tab);
    if (target == NULL || get_menu(target) == NULL) {
        log_debug("MediaWall tab without CORE destination: %d", (int) tab);
        return;
    }
    load_submenu(target);
}

static void media_wall_move(int horizontal, int vertical)
{
    if (!is_media_wall(current_menu) || !prepare_media_wall(current_menu))
        return;
    bool was_tab_focused = current_menu->media_wall.tab_focused;
    bool changed = false;
    if (horizontal != 0)
        changed = media_wall_move_horizontal(&current_menu->media_wall, horizontal);
    if (vertical != 0)
        changed = media_wall_move_vertical(&current_menu->media_wall, vertical) || changed;
    if (changed) {
        current_menu->media_wall_focus_started = SDL_GetTicks();
        update_media_wall_footer(current_menu);
        if (was_tab_focused != current_menu->media_wall.tab_focused)
            update_media_wall_footer_help(current_menu);
    }
}



static void draw_home_card(const SDL_Rect *icon_rect, bool selected)
{
    SDL_Rect card = {
        icon_rect->x - 20,
        icon_rect->y - 20,
        icon_rect->w + 40,
        icon_rect->h + 40
    };

    SDL_Rect shadow_far = {
        card.x - 10,
        card.y - 5,
        card.w + 20,
        card.h + 25
    };
    SDL_Rect shadow_near = {
        card.x - 5,
        card.y,
        card.w + 10,
        card.h + 15
    };

    fill_rounded_rect(renderer, &shadow_far, 34,
        (SDL_Color) {0, 0, 0, 58});
    fill_rounded_rect(renderer, &shadow_near, 30,
        (SDL_Color) {0, 0, 0, 92});

    if (selected) {
        SDL_Rect glow = {
            card.x - 7,
            card.y - 7,
            card.w + 14,
            card.h + 14
        };
        fill_rounded_rect(renderer, &glow, 32,
            (SDL_Color) {255, 255, 255, 42});
    }

    fill_rounded_rect(renderer, &card, 27,
        selected
            ? (SDL_Color) {255, 255, 255, 205}
            : (SDL_Color) {255, 255, 255, 45});

    SDL_Rect inner = {
        card.x + 2,
        card.y + 2,
        card.w - 4,
        card.h - 4
    };
    fill_rounded_rect(renderer, &inner, 25,
        selected
            ? (SDL_Color) {4, 5, 8, 205}
            : (SDL_Color) {4, 5, 8, 168});
}

// A function to handle key presses from keyboard
static void handle_keypress(SDL_Keysym *key)
{
    if (!tracked_is_interaction_allowed())
        return;

    /* Keyboard navigation normally mutates current_entry directly.
     * Route it to the native modal first to block hidden navigation. */
    if (resume_modal_active) {
        switch (key->sym) {
            case SDLK_UP:
            case SDLK_LEFT:
                execute_command(":up");
                break;
            case SDLK_DOWN:
            case SDLK_RIGHT:
                execute_command(":down");
                break;
            case SDLK_RETURN:
            case SDLK_KP_ENTER:
                execute_command(":select");
                break;
            case SDLK_ESCAPE:
            case SDLK_BACKSPACE:
                execute_command(":back");
                break;
            default:
                break;
        }
        return;
    }


    if (config.debug)
        log_debug("Key %s (#%X) detected", SDL_GetKeyName(key->sym), key->sym);

    // Check default keys
    if (is_media_wall(current_menu) && key->sym == SDLK_UP)
        media_wall_move(0, -1);
    else if (is_media_wall(current_menu) && key->sym == SDLK_DOWN)
        media_wall_move(0, 1);
    else if (is_media_wall(current_menu) && key->sym == SDLK_LEFT)
        media_wall_move(-1, 0);
    else if (is_media_wall(current_menu) && key->sym == SDLK_RIGHT)
        media_wall_move(1, 0);
    else if ((is_media_sidebar() || is_media_list() || is_system_root() || is_disc_ambiguous()) && key->sym == SDLK_UP) {
        if (current_entry != NULL) current_entry->context_selected = false;
        move_left();
    }
    else if ((is_media_sidebar() || is_media_list() || is_system_root() || is_disc_ambiguous()) && key->sym == SDLK_DOWN) {
        if (current_entry != NULL) current_entry->context_selected = false;
        move_right();
    }
    else if (is_media_list() && key->sym == SDLK_RIGHT) {
        if (current_entry != NULL && current_entry->context_cmd != NULL && !current_entry->context_selected) {
            current_entry->context_selected = true;
        }
    }
    else if (is_media_list() && key->sym == SDLK_LEFT) {
        if (current_entry != NULL && current_entry->context_selected) {
            current_entry->context_selected = false;
        }
    }
    else if (key->sym == SDLK_LEFT)
        move_left();
    else if (key->sym == SDLK_RIGHT)
        move_right();
    else if (is_media_wall(current_menu) && key->sym == SDLK_RETURN &&
             current_menu->media_wall.tab_focused) {
        media_wall_activate_tab();
    }
    else if (key->sym == SDLK_RETURN) {
        log_debug("Selected Entry:\n"
            "Title: %s\n"
            "Icon Path: %s\n"
            "Command: %s", 
            current_entry->title, 
            current_entry->icon_path, 
            (current_entry->context_selected && current_entry->context_cmd != NULL)
                ? current_entry->context_cmd
                : current_entry->cmd
        );
        
        if (current_entry->context_selected && current_entry->context_cmd != NULL)
            execute_command(current_entry->context_cmd);
        else
            execute_command(current_entry->cmd);
    }
    else if (key->sym == SDLK_BACKSPACE) {
        bool handled = false;
        for (Hotkey *i = hotkeys; i != NULL; i = i->next) {
            if (key->sym == i->keycode) {
                execute_command(i->cmd);
                handled = true;
                break;
            }
        }
        if (!handled && current_menu->back != NULL)
            load_back_menu(current_menu);
    }

    //Check hotkeys
    else {
        for (Hotkey *i = hotkeys; i != NULL; i = i->next) {
            if (key->sym == i->keycode) {
                execute_command(i->cmd);
                break;
            }
        }
    }
}

// A function to quit the slideshow mode in case of error or program exit
void quit_slideshow()
{
    // Free allocated image paths
    for (int i = 0; i < slideshow->num_images; i++)
        free(slideshow->images[i]);
    free(slideshow->images);
    free(slideshow->order);
    free(slideshow);
}

// A function to initialize the slideshow background mode
static void init_slideshow()
{
    if (!directory_exists(config.slideshow_directory)) {
        log_error("Slideshow directory '%s' does not exist, "
            "Switching to color background mode",
            config.slideshow_directory
        );
        config.background_mode = BACKGROUND_COLOR;
        set_draw_color();
        return;
    }
    // Allocate and initialize slideshow struct
    slideshow = malloc(sizeof(Slideshow));
    *slideshow = (Slideshow) {
        .i = -1,
        .num_images = 0,
        .transition_surface = NULL,
        .transition_texture = NULL,
        .transition_alpha = 0.f,
        .transition_change_rate = 0.f,
        .images = NULL,
        .order = NULL
    };

    // Find background images from directory
    scan_slideshow_directory(slideshow, config.slideshow_directory);
    
    // Handle errors
    if (!slideshow->num_images) {
        log_error("No images found in slideshow directory '%s', "
            "Changing background mode to color", 
            config.slideshow_directory
        );
        config.background_mode = BACKGROUND_COLOR;
        quit_slideshow();
    } 
    else if (slideshow->num_images == 1) {
        log_error("Only one image found in slideshow directory %s"
            "Changing background mode to single image", 
            config.slideshow_directory
        );
        free(config.background_image);
        config.background_image = strdup(slideshow->images[0]);
        config.background_mode = BACKGROUND_IMAGE;
        quit_slideshow();
    }

    // Generate array of random numbers for image order, load first image
    else {
        slideshow->order = malloc(sizeof(int) * (size_t) slideshow->num_images);
        random_array(slideshow->order, slideshow->num_images);
        if (config.debug)
            debug_slideshow(slideshow);
    }
}

// A function to initialize the screensaver feature
static void init_screensaver()
{
    // Allocate memory for structure
    screensaver = malloc(sizeof(Screensaver));
    
    // Convert intensity string to float
    char intensity[PERCENT_MAX_CHARS];
    if (config.screensaver_intensity_str[0] != '\0')
        copy_string(intensity, config.screensaver_intensity_str, sizeof(intensity));
    else
        copy_string(intensity, DEFAULT_SCREENSAVER_INTENSITY, sizeof(intensity));
    size_t length = strlen(intensity);
    intensity[length - 1] = '\0';
    float percent = (float) atof(intensity);

    // Calculate alpha end value
    screensaver->alpha_end_value = 255.0f * percent / 100.0f;
    if (screensaver->alpha_end_value < 1.0f) {
        log_error("Invalid screensaver intensity value, disabling feature");
        config.screensaver_enabled = false;
        free(screensaver);
        screensaver = NULL;
        return;
    }
    else if (screensaver->alpha_end_value >= 255.0f)
        screensaver->alpha_end_value = 255.0f;

    screensaver->transition_change_rate = screensaver->alpha_end_value / ((float) SCREENSAVER_TRANSITION_TIME / (float) refresh_period);
    
    // Render texture
    SDL_Surface *surface = NULL;
    surface = SDL_CreateRGBSurfaceWithFormat(0, 
                  geo.screen_width, 
                  geo.screen_height, 
                  32,
                  SDL_PIXELFORMAT_ARGB8888
              );
    Uint32 color = SDL_MapRGBA(surface->format, 0, 0, 0, 0xFF);
    SDL_FillRect(surface, NULL, color);
    screensaver->texture = load_texture(surface);
    screensaver->alpha = 0.0f;
    SDL_SetTextureAlphaMod(screensaver->texture, 0.0f);
}

// A function to resume the slideshow after a launched application returns
static void resume_slideshow()
{
    ticks.slideshow_load = ticks.main;
}

// A function to load a menu
static int load_menu(Menu *menu, bool set_back_menu, bool reset_position)
{
    if (menu == NULL)
        return 1;

    unsigned int buttons;
    Menu *previous_menu = current_menu;

    current_menu = menu;
    log_debug("Loading menu '%s'", current_menu->name);

    // Return error if the menu doesn't contain entires
    if (current_menu->num_entries == 0) {
        log_error("No valid entries found for Menu '%s'", current_menu->name);
        current_menu = previous_menu;
        return 1;
    }

    if (is_system_subpage() || (current_menu->name != NULL && !strcmp(current_menu->name, "SYSTEME"))) {
        if (current_menu->background_texture != NULL) {
            SDL_DestroyTexture(current_menu->background_texture);
            current_menu->background_texture = NULL;
        }
    }

    // Render the menu if not already rendered
    if (current_menu->rendered == false)
        render_buttons(current_menu);
    if (current_menu->background_path != NULL && current_menu->background_texture == NULL)
        current_menu->background_texture = load_texture_from_file(current_menu->background_path);

    // Set menu properties
    if (set_back_menu)
        current_menu->back = previous_menu;

    if (reset_position) {
        if (is_media_wall(current_menu) && current_menu->media_wall_initialized) {
            current_menu->media_wall.row = MEDIA_WALL_RECENT;
            current_menu->media_wall.selected[MEDIA_WALL_RECENT] = 0;
            current_menu->media_wall.selected[MEDIA_WALL_ALL] = 0;
            current_menu->media_wall.scroll[MEDIA_WALL_RECENT] = 0;
            current_menu->media_wall.scroll[MEDIA_WALL_ALL] = 0;
            update_media_wall_footer(current_menu);
        }
        current_entry = current_menu->first_entry;
        current_menu->root_entry = current_entry;
        current_menu->highlight_position = 0;
        current_menu->page = 0;
    }
    else {
        /* A live state refresh can revisit the initial menu before any
         * navigation has populated last_selected_entry.  The old code left
         * current_entry NULL and immediately dereferenced it below. */
        current_entry = current_menu->last_selected_entry;
        if (current_entry == NULL)
            current_entry = current_menu->first_entry;
        if (current_menu->root_entry == NULL)
            current_menu->root_entry = current_menu->first_entry;
        unsigned int pos = 0;
        for (Entry *e = current_menu->root_entry; e != NULL && e != current_entry; e = e->next) {
            pos++;
        }
        if (pos < current_menu->num_entries) {
            current_menu->highlight_position = pos;
        } else {
            current_entry = current_menu->first_entry;
            current_menu->root_entry = current_entry;
            current_menu->highlight_position = 0;
            current_menu->page = 0;
        }
    }

    if (is_media_wall(current_menu)) {
        current_entry = media_wall_entry(current_menu, current_menu->media_wall.row,
            current_menu->media_wall.selected[current_menu->media_wall.row]);
        current_menu->last_selected_entry = current_entry;
        geo.num_buttons = 0;
        publish_media_page(current_menu->name);
        return current_entry == NULL;
    }

    unsigned int page_size = menu_page_size(current_menu);
    buttons = current_menu->num_entries - (current_menu->page)*page_size;
    if (buttons > page_size)
        buttons = page_size;
    
    // Recalculate the screen geometry
    calculate_button_geometry(current_menu->root_entry, (int) buttons);
    if (current_entry != NULL)
        current_entry->context_selected = false;
    if (config.highlight) {
        highlight->rect.x = current_entry->icon_rect.x - config.highlight_hpadding;
        highlight->rect.y = current_entry->icon_rect.y - config.highlight_vpadding;
        /* Page-local geometry: MEDIA may stretch this rect while drawing,
         * but every model transition restores the canonical button size. */
        highlight->rect.w = config.icon_size + 2 * config.highlight_hpadding;
        highlight->rect.h = config.icon_size + config.title_padding + geo.font_height + 2 * config.highlight_vpadding;
    }
    publish_media_page(current_menu->name);
    return 0;
}

/* Publish the page actually loaded by this authoritative Flex process.
 * Candidate config regeneration must never change this marker. */
static void publish_media_page(const char *menu_name)
{
    const char *home = getenv("OPENHTPC_HOME");
    if (home == NULL || home[0] == '\0')
        home = getenv("HOME");
    if (home == NULL || home[0] == '\0')
        return;
    char target[MAX_PATH_CHARS + 1];
    char temporary[MAX_PATH_CHARS + 32];
    snprintf(target, sizeof(target), "%s/.local/state/openhtpc/media-actions/current-page", home);
    snprintf(temporary, sizeof(temporary), "%s.tmp.%ld", target, (long)getpid());
    FILE *stream = fopen(temporary, "w");
    if (stream == NULL)
        return;
    if (menu_name != NULL && strncmp(menu_name, "MEDIA", 5) == 0)
        fprintf(stream, "%s\n", menu_name);
    else
        fputc('\n', stream);
    fflush(stream);
    fsync(fileno(stream));
    fclose(stream);
    chmod(temporary, S_IRUSR | S_IWUSR);
    if (rename(temporary, target) != 0)
        unlink(temporary);
}

// A function to load a menu by its name
static int load_menu_by_name(const char *menu_name, bool set_back_menu, bool reset_position)
{
    Menu *menu = get_menu(menu_name);
    if (menu == NULL && config.config_file_path != NULL && menu_name != NULL) {
        Menu *last = config.first_menu;
        while (last != NULL && last->next != NULL) last = last->next;
        Menu *new_menu = create_menu(menu_name, &config.num_menus);
        if (last != NULL) last->next = new_menu;
        else config.first_menu = new_menu;
        reload_menu_section(new_menu);
        menu = new_menu;
    }
    return load_menu(menu, set_back_menu, reset_position);
}

// A function to calculate the layout of the buttons
static void calculate_button_geometry(Entry *entry, int buttons)
{
    geo.num_buttons = buttons;

    if (is_disc_ambiguous()) {
        int num_dock = 0;
        for (Entry *e = entry; e != NULL; e = e->next) {
            if (e->cmd == NULL || strstr(e->cmd, "openhtpc-bind-disc") == NULL)
                num_dock++;
        }
        int cand_idx = 0;
        int dock_idx = 0;
        int card_h = (geo.screen_height * 115) / 1000;
        int cand_gap = (geo.screen_height * 18) / 1000;
        int start_x = (geo.screen_width * 305) / 1000;
        int start_y = (geo.screen_height * 34) / 100;
        int icon_w = (card_h * 2) / 3;
        int icon_h = card_h - (geo.screen_height * 18) / 1000;

        int dock_gap = (geo.screen_width * 15) / 1000;
        int dock_w = (geo.screen_width * 21) / 100;
        int total_dock = (num_dock > 0) ? (num_dock * dock_w + (num_dock - 1) * dock_gap) : 0;
        int dock_margin = (geo.screen_width - total_dock) / 2;

        for (int i = 0; i < buttons && entry != NULL; i++) {
            if (entry->cmd != NULL && strstr(entry->cmd, "openhtpc-bind-disc") != NULL) {
                int card_y = start_y + cand_idx * (card_h + cand_gap);
                entry->icon_rect.x = start_x + (geo.screen_width * 12) / 1000;
                entry->icon_rect.y = card_y + (card_h - icon_h) / 2;
                entry->icon_rect.w = icon_w;
                entry->icon_rect.h = icon_h;
                entry->text_rect.x = entry->icon_rect.x + icon_w + (geo.screen_width * 18) / 1000;
                entry->text_rect.y = card_y + (card_h - entry->text_rect.h) / 2;
                cand_idx++;
            } else {
                entry->icon_rect.x = dock_margin + dock_idx * (dock_w + dock_gap);
                entry->icon_rect.y = (geo.screen_height * 88) / 100;
                entry->icon_rect.w = dock_w;
                entry->icon_rect.h = (geo.screen_height * 8) / 100;
                entry->text_rect.x = entry->icon_rect.x + (dock_w - entry->text_rect.w) / 2;
                entry->text_rect.y = entry->icon_rect.y + (entry->icon_rect.h - entry->text_rect.h) / 2;
                dock_idx++;
            }
            entry = entry->next;
        }
        return;
    }

    if (is_disc_sheet() || is_system_subpage() || is_movie_detail(current_menu)) {
        int gap = (geo.screen_width * 15) / 1000;
        int max_w = (buttons <= 2) ? (geo.screen_width * 36) / 100 : (buttons <= 3) ? (geo.screen_width * 28) / 100 : (geo.screen_width * 22) / 100;
        int avail_w = (geo.screen_width * 88) / 100;
        int width = (avail_w - (buttons - 1) * gap) / (buttons > 0 ? buttons : 1);
        if (width > max_w) width = max_w;
        int total = buttons * width + (buttons - 1) * gap;
        geo.x_margin = (geo.screen_width - total) / 2;
        geo.x_advance = width + gap;
        for (int i = 0; i < buttons && entry != NULL; i++) {
            entry->icon_rect.x = geo.x_margin + i * geo.x_advance;
            entry->icon_rect.y = (geo.screen_height * 88) / 100;
            entry->icon_rect.w = width;
            entry->icon_rect.h = (geo.screen_height * 8) / 100;
            if (is_system_subpage()) {
                int icon_size = (geo.screen_height * 4) / 100;
                int safety_margin = (geo.screen_height * 1) / 100;
                int stack_height = icon_size + safety_margin + entry->text_rect.h;
                int stack_y = entry->icon_rect.y + (entry->icon_rect.h - stack_height) / 2;
                entry->text_rect.x = entry->icon_rect.x + (width - entry->text_rect.w) / 2;
                entry->text_rect.y = stack_y + icon_size + safety_margin;
            } else if (is_disc_action_sheet() || is_movie_detail(current_menu)) {
                if (entry->icon != NULL) {
                    int icon_size = (geo.screen_height * 34) / 1000;
                    int icon_gap = (geo.screen_width * 6) / 1000;
                    int total_w = icon_size + icon_gap + entry->text_rect.w;
                    int start_x = entry->icon_rect.x + (width - total_w) / 2;
                    if (start_x < entry->icon_rect.x + (geo.screen_width * 1) / 100)
                        start_x = entry->icon_rect.x + (geo.screen_width * 1) / 100;
                    entry->text_rect.x = start_x + icon_size + icon_gap;
                    entry->text_rect.y = entry->icon_rect.y + (entry->icon_rect.h - entry->text_rect.h) / 2;
                } else {
                    entry->text_rect.x = entry->icon_rect.x + (width - entry->text_rect.w) / 2;
                    entry->text_rect.y = entry->icon_rect.y + (entry->icon_rect.h - entry->text_rect.h) / 2;
                }
            } else {
                entry->text_rect.x = entry->icon_rect.x + (width - entry->text_rect.w) / 2;
                entry->text_rect.y = entry->icon_rect.y + (entry->icon_rect.h - entry->text_rect.h) / 2;
            }
            entry = entry->next;
        }
        return;
    }

    if (is_system_root()) {
        int row_height = (geo.screen_height * 64) / 1000;
        int gap = (geo.screen_height * 7) / 1000;
        int icon_size = (geo.screen_height * 46) / 1000;
        int text_height = (geo.screen_height * 32) / 1000;
        int start_y = (geo.screen_height * 10) / 100;
        geo.x_margin = (geo.screen_width * 6) / 100;
        geo.x_advance = 0;
        for (int i = 0; i < buttons && entry != NULL; i++) {
            entry->icon_rect.x = geo.x_margin + (geo.screen_width * 12) / 1000;
            entry->icon_rect.y = start_y + i * (row_height + gap) + (row_height - icon_size) / 2;
            entry->icon_rect.w = icon_size;
            entry->icon_rect.h = icon_size;
            if (entry->text_rect.h > text_height && entry->text_rect.h > 0) {
                entry->text_rect.w = entry->text_rect.w * text_height / entry->text_rect.h;
                entry->text_rect.h = text_height;
            }
            entry->text_rect.x = entry->icon_rect.x + icon_size + (geo.screen_width * 14) / 1000;
            entry->text_rect.y = start_y + i * (row_height + gap) + (row_height - entry->text_rect.h) / 2;
            entry = entry->next;
        }
        return;
    }

    if (is_media_list()) {
        int row_height = (geo.screen_height * 9) / 100;
        int gap = (geo.screen_height * 3) / 200;
        int icon_size = (geo.screen_height * 13) / 200;
        int total = buttons * row_height + (buttons - 1) * gap;
        int start_y = (geo.screen_height - total) / 2;
        geo.x_margin = (geo.screen_width * 9) / 100;
        geo.x_advance = 0;
        for (int i = 0; i < buttons && entry != NULL; i++) {
            entry->icon_rect.x = geo.x_margin;
            entry->icon_rect.y = start_y + i * (row_height + gap) + (row_height - icon_size) / 2;
            entry->icon_rect.w = icon_size;
            entry->icon_rect.h = icon_size;
            entry->text_rect.x = entry->icon_rect.x + icon_size + (geo.screen_width * 4) / 100;
            entry->text_rect.y = start_y + i * (row_height + gap) + (row_height - entry->text_rect.h) / 2;

            if (entry->context_cmd != NULL && entry->context_texture != NULL) {
                int pad_h = (geo.screen_width * 14) / 1000;
                int pill_w = entry->context_rect.w + pad_h * 2;
                int pill_h = (row_height * 68) / 100;
                int pill_x = (geo.screen_width * 92) / 100 - pill_w;
                int pill_y = start_y + i * (row_height + gap) + (row_height - pill_h) / 2;
                entry->context_rect.x = pill_x + pad_h;
                entry->context_rect.y = pill_y + (pill_h - entry->context_rect.h) / 2;
            }
            entry = entry->next;
        }
        return;
    }

    // -----------------------------------------------------
    // OpenHTPC MediaSidebar
    // -----------------------------------------------------

    if (is_media_sidebar()) {

        /*
         * Zone de commande à droite :
         * environ 17 % de la largeur de l'écran.
         */

        int sidebar_width =
            (geo.screen_width * 17) / 100;

        int center_x =
            geo.screen_width
            -
            sidebar_width / 2;


        /*
         * IconSize reste piloté par config.ini.
         *
         * Pour le MediaSidebar nous utiliserons ensuite
         * une valeur TV-friendly beaucoup plus petite que
         * les anciennes grosses tuiles.
         */

        int icon_size =
            config.icon_size;


        int title_height = 0;

        if (config.titles_enabled) {

            title_height =
                geo.font_height
                +
                config.title_padding;
        }


        int gap =
            (geo.screen_height * 2) / 100;


        int step =
            icon_size
            +
            title_height
            +
            gap;


        int total_height =
            step * buttons
            -
            gap;


        int start_y =
            (
                geo.screen_height
                -
                total_height
            )
            /
            2;


        /*
         * Les fonctions historiques move_left/right()
         * utilisent x_advance pour déplacer le highlight.
         *
         * En mode vertical, le highlight sera réaligné
         * directement sur current_entry à chaque frame.
         */

        geo.x_margin =
            center_x
            -
            icon_size / 2;

        geo.x_advance = 0;


        for (
            int i = 0;
            i < geo.num_buttons;
            i++
        ) {

            entry->icon_rect.x =
                geo.x_margin;

            entry->icon_rect.y =
                start_y
                +
                i * step;

            entry->icon_rect.w =
                icon_size;

            entry->icon_rect.h =
                icon_size;


            entry->text_rect.x =
                center_x
                -
                entry->text_rect.w / 2;


            entry->text_rect.y =
                entry->icon_rect.y
                +
                icon_size
                +
                entry->title_offset
                +
                config.title_padding;


            entry = entry->next;
        }


        return;
    }


    // -----------------------------------------------------
    // Flex Launcher original
    // -----------------------------------------------------

    geo.x_margin =
        (
            geo.screen_width
            -
            config.icon_size * buttons
            -
            buttons * config.icon_spacing
            +
            config.icon_spacing
        )
        /
        2;


    geo.x_advance =
        config.icon_size
        +
        config.icon_spacing;


    // Assign values to entries

    for (
        int i = 0;
        i < geo.num_buttons;
        i++
    ) {

        entry->icon_rect.x =
            geo.x_margin
            +
            i * geo.x_advance;

        entry->icon_rect.y =
            geo.y_margin;

        entry->icon_rect.w =
            config.icon_size;

        entry->icon_rect.h =
            config.icon_size;


        entry->text_rect.x =
            entry->icon_rect.x
            +
            (
                entry->icon_rect.w
                -
                entry->text_rect.w
            )
            /
            2;


        entry->text_rect.y =
            entry->icon_rect.y
            +
            config.icon_size
            +
            entry->title_offset
            +
            config.title_padding;


        entry = entry->next;
    }
}


// A function to render all buttons (icon and text) for a menu
static void render_buttons(Menu *menu)
{
    Entry *entry;
    int h;

    if (is_media_wall(menu)) {
        menu->rendered = prepare_media_wall(menu);
        return;
    }

    if (is_movie_detail(menu)) {
        assemble_menu_synopsis(menu);
        free_menu_detail_textures(menu);

        int box_x = (geo.screen_width * 6) / 100;
        int box_y = (geo.screen_height * 9) / 100;
        int box_w = (geo.screen_width * 26) / 100;
        int box_h = (geo.screen_height * 75) / 100;

        if (menu->detail_poster_path != NULL && menu->detail_poster_texture == NULL) {
            menu->detail_poster_texture = load_texture_from_file(menu->detail_poster_path);
        }

        if (menu->detail_poster_texture != NULL) {
            int tex_w = 0, tex_h = 0;
            if (SDL_QueryTexture(menu->detail_poster_texture, NULL, NULL, &tex_w, &tex_h) == 0 &&
                tex_w > 0 && tex_h > 0) {
                double src_ratio = (double) tex_w / (double) tex_h;
                double box_ratio = (double) box_w / (double) box_h;
                int fit_w, fit_h;
                if (src_ratio > box_ratio) {
                    fit_w = box_w;
                    fit_h = (int)(box_w / src_ratio);
                } else {
                    fit_h = box_h;
                    fit_w = (int)(box_h * src_ratio);
                }
                menu->detail_poster_rect.x = box_x + (box_w - fit_w) / 2;
                menu->detail_poster_rect.y = box_y + (box_h - fit_h) / 2;
                menu->detail_poster_rect.w = fit_w;
                menu->detail_poster_rect.h = fit_h;
            } else {
                menu->detail_poster_rect = (SDL_Rect){ box_x, box_y, box_w, box_h };
            }
        } else {
            menu->detail_poster_rect = (SDL_Rect){ box_x, box_y, box_w, box_h };
        }

        int text_x = box_x + box_w + (geo.screen_width * 4) / 100;
        int text_max_w = (geo.screen_width * 94) / 100 - text_x;
        int cur_y = box_y + (geo.screen_height * 15) / 1000;
        int dock_top_y = (geo.screen_height * 86) / 100;

        const char *font_path = (config.title_font_path != NULL) ? config.title_font_path : NULL;
        /* UX-F1: the HOME title font is deliberately large (e.g. 72pt on
         * 1080p TVs), but cannot be reused as the movie-detail body font.
         * A 72pt body clips fact-card rows and pushes synopsis below the
         * action dock. Size detail text by output height instead:
         * 26pt base / 35pt title at 1080p, 52pt / 70pt at 2160p.
         * Preserve the configured font FAMILY and CJK fallback. */
        int base_pt = (geo.screen_height * 26 + 540) / 1080;
        if (base_pt < 16)
            base_pt = 16;

        // 1. Title
        if (menu->detail_title != NULL && menu->detail_title[0] != '\0') {
            int title_pt = (int)(base_pt * 1.35);
            TTF_Font *title_font = NULL;
            if (font_path != NULL) title_font = TTF_OpenFont(font_path, title_pt);
            if (title_font == NULL) title_font = title_info.font;

            menu->detail_title_texture = render_text_wrapped(
                menu->detail_title,
                title_font,
                config.title_fallback_font_path,
                title_pt,
                (SDL_Color){255, 255, 255, 255},
                text_max_w,
                (geo.screen_height * 18) / 100,
                &menu->detail_title_rect
            );
            menu->detail_title_rect.x = text_x;
            menu->detail_title_rect.y = cur_y;
            cur_y += menu->detail_title_rect.h + (geo.screen_height * 12) / 1000;

            if (title_font != title_info.font) TTF_CloseFont(title_font);
        }

        // 2. Original Title
        if (menu->detail_original_title != NULL && menu->detail_original_title[0] != '\0') {
            int orig_pt = (int)(base_pt * 0.85);
            if (orig_pt < 12) orig_pt = 12;
            TTF_Font *orig_font = NULL;
            if (font_path != NULL) orig_font = TTF_OpenFont(font_path, orig_pt);
            if (orig_font == NULL) orig_font = title_info.font;

            /* CORE original titles may contain Korean/Japanese/Han script.
             * Use a locally installed CJK fallback when configuration has
             * not explicitly provided one; never download font assets. */
            const char *original_fallback = config.title_fallback_font_path;
#ifdef __linux__
            if (original_fallback == NULL || original_fallback[0] == '\0')
                original_fallback =
                    "/usr/share/fonts/google-noto-sans-cjk-vf-fonts/NotoSansCJK-VF.ttc";
#endif
            menu->detail_original_title_texture = render_text_wrapped(
                menu->detail_original_title,
                orig_font,
                original_fallback,
                orig_pt,
                (SDL_Color){160, 160, 160, 255},
                text_max_w,
                (geo.screen_height * 6) / 100,
                &menu->detail_original_title_rect
            );
            menu->detail_original_title_rect.x = text_x;
            menu->detail_original_title_rect.y = cur_y;
            cur_y += menu->detail_original_title_rect.h + (geo.screen_height * 10) / 1000;

            if (orig_font != title_info.font) TTF_CloseFont(orig_font);
        }

        // 3. Metadata
        if (menu->detail_metadata != NULL && menu->detail_metadata[0] != '\0') {
            int meta_pt = (int)(base_pt * 0.9);
            if (meta_pt < 12) meta_pt = 12;
            TTF_Font *meta_font = NULL;
            if (font_path != NULL) meta_font = TTF_OpenFont(font_path, meta_pt);
            if (meta_font == NULL) meta_font = title_info.font;

            menu->detail_metadata_texture = render_text_wrapped(
                menu->detail_metadata,
                meta_font,
                config.title_fallback_font_path,
                meta_pt,
                (SDL_Color){190, 200, 210, 255},
                text_max_w,
                (geo.screen_height * 8) / 100,
                &menu->detail_metadata_rect
            );
            menu->detail_metadata_rect.x = text_x;
            menu->detail_metadata_rect.y = cur_y;
            cur_y += menu->detail_metadata_rect.h + (geo.screen_height * 20) / 1000;

            if (meta_font != title_info.font) TTF_CloseFont(meta_font);
        }

        // 4. Structured movie facts, taken verbatim from CORE Fact1..Fact6.
        // Keep the synopsis and the action dock visible; missing data gets
        // no invented placeholder. The last two facts share a technical row.
        int fact_pt = (int)(base_pt * 0.84);
        if (fact_pt < 12) fact_pt = 12;
        TTF_Font *fact_font = NULL;
        if (font_path != NULL) fact_font = TTF_OpenFont(font_path, fact_pt);
        if (fact_font == NULL) fact_font = title_info.font;
        const char *facts[6] = {
            menu->detail_facts[0], menu->detail_facts[1],
            menu->detail_facts[2], menu->detail_facts[3],
            menu->detail_facts[4], menu->detail_source_colorimetry
        };
        const SDL_Color fact_colors[6] = {
            {198, 222, 246, 255}, {245, 194, 100, 255},
            {200, 218, 240, 255}, {204, 212, 230, 255},
            {158, 204, 240, 255}, {190, 162, 247, 255}
        };
        int fact_pad_y = (geo.screen_height * 6) / 1000;
        int fact_pad_x = (geo.screen_width * 10) / 1000;
        int fact_gap_y = (geo.screen_height * 7) / 1000;
        int reserved_synopsis = (menu->detail_synopsis != NULL &&
                                 menu->detail_synopsis[0] != '\0')
                              ? geo.screen_height * 18 / 100 : 0;
        int facts_bottom = dock_top_y - reserved_synopsis;
        for (int fi = 0; fi < 4; fi++) {
            if (facts[fi] == NULL || facts[fi][0] == '\0' ||
                cur_y + fact_pad_y * 2 >= facts_bottom)
                continue;
            int row_height = (fi == 3 ? geo.screen_height * 72 / 1000 :
                                        geo.screen_height * 57 / 1000);
            if (row_height > facts_bottom - cur_y)
                row_height = facts_bottom - cur_y;
            if (row_height <= fact_pad_y * 2)
                break;
            menu->detail_fact_textures[fi] = render_text_wrapped(
                facts[fi], fact_font, config.title_fallback_font_path,
                fact_pt, fact_colors[fi],
                text_max_w - fact_pad_x * 2, row_height - fact_pad_y * 2,
                &menu->detail_fact_rects[fi]);
            if (menu->detail_fact_textures[fi] == NULL)
                continue;
            menu->detail_fact_rects[fi].x = text_x + fact_pad_x;
            menu->detail_fact_rects[fi].y = cur_y + fact_pad_y;
            cur_y += menu->detail_fact_rects[fi].h +
                     fact_pad_y * 2 + fact_gap_y;
        }
        int technical_gap = geo.screen_width * 12 / 1000;
        int technical_width = (text_max_w - technical_gap) / 2;
        int technical_height = 0;
        for (int fi = 4; fi < 6; fi++) {
            if (facts[fi] == NULL || facts[fi][0] == '\0' ||
                cur_y + fact_pad_y * 2 >= facts_bottom)
                continue;
            int max_height = geo.screen_height * 82 / 1000;
            if (max_height > facts_bottom - cur_y)
                max_height = facts_bottom - cur_y;
            menu->detail_fact_textures[fi] = render_text_wrapped(
                facts[fi], fact_font, config.title_fallback_font_path,
                fact_pt, fact_colors[fi],
                technical_width - fact_pad_x * 2,
                max_height - fact_pad_y * 2,
                &menu->detail_fact_rects[fi]);
            if (menu->detail_fact_textures[fi] == NULL)
                continue;
            menu->detail_fact_rects[fi].x =
                text_x + (fi - 4) * (technical_width + technical_gap) +
                fact_pad_x;
            menu->detail_fact_rects[fi].y = cur_y + fact_pad_y;
            int height = menu->detail_fact_rects[fi].h +
                         fact_pad_y * 2;
            if (height > technical_height)
                technical_height = height;
        }
        if (technical_height > 0)
            cur_y += technical_height + fact_gap_y;
        if (fact_font != title_info.font)
            TTF_CloseFont(fact_font);

        // 5. Synopsis — remaining height is bounded by the action dock.
        if (menu->detail_synopsis != NULL && menu->detail_synopsis[0] != '\0') {
            int avail_h = dock_top_y - cur_y;
            if (avail_h > 0) {
                int syn_pt = (int)(base_pt * 0.85);
                if (syn_pt < 12) syn_pt = 12;
                TTF_Font *syn_font = NULL;
                if (font_path != NULL) syn_font = TTF_OpenFont(font_path, syn_pt);
                if (syn_font == NULL) syn_font = title_info.font;

                menu->detail_synopsis_texture = render_text_wrapped(
                    menu->detail_synopsis,
                    syn_font,
                    config.title_fallback_font_path,
                    syn_pt,
                    (SDL_Color){215, 215, 215, 255},
                    text_max_w,
                    avail_h,
                    &menu->detail_synopsis_rect
                );
                menu->detail_synopsis_rect.x = text_x;
                menu->detail_synopsis_rect.y = cur_y;

                if (syn_font != title_info.font) TTF_CloseFont(syn_font);
            }
        }
    }

    for (entry = menu->first_entry; entry != NULL; entry = entry->next) {
        entry->icon = load_texture_from_file(entry->icon_path);
        entry->icon_selected = (entry->icon_selected_path != NULL) ? load_texture_from_file(entry->icon_selected_path) : NULL;
        if (config.titles_enabled) {
            TextInfo media_title = title_info;
            if (menu->name != NULL && strncmp(menu->name, "MEDIA", 5) == 0 && !is_movie_detail(menu)) {
                media_title.max_width = (entry->context_cmd != NULL)
                    ? (geo.screen_width * 48) / 100
                    : (geo.screen_width * 72) / 100;
                media_title.oversize_mode = OVERSIZE_TRUNCATE;
            }
            if (menu->name != NULL && strcmp(menu->name, "SYSTEME") == 0) {
                media_title.max_width = (geo.screen_width * 30) / 100;
                media_title.oversize_mode = OVERSIZE_TRUNCATE;
            }
            if (is_menu_disc_ambiguous(menu) && entry->cmd != NULL && strstr(entry->cmd, "openhtpc-bind-disc") != NULL) {
                int card_w = (geo.screen_width * 64) / 100;
                int icon_w = ((geo.screen_height * 115) / 1000 * 2) / 3;
                media_title.max_width = card_w - icon_w - (geo.screen_width * 5) / 100;
                media_title.oversize_mode = OVERSIZE_TRUNCATE;
            } else if (is_menu_disc_sheet(menu) || is_menu_system_subpage(menu) || is_movie_detail(menu)) {
                int btn_count = 0;
                for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
                    if (e->cmd == NULL || strstr(e->cmd, "openhtpc-bind-disc") == NULL) btn_count++;
                }
                int gap = (geo.screen_width * 15) / 1000;
                int max_w = (btn_count <= 2) ? (geo.screen_width * 36) / 100 : (btn_count <= 3) ? (geo.screen_width * 28) / 100 : (geo.screen_width * 22) / 100;
                int avail_w = (geo.screen_width * 88) / 100;
                int btn_w = (avail_w - (btn_count - 1) * gap) / (btn_count > 0 ? btn_count : 1);
                if (btn_w > max_w) btn_w = max_w;
                if ((is_menu_disc_action_sheet(menu) || is_movie_detail(menu)) && entry->icon != NULL) {
                    int reserved_icon = (geo.screen_height * 34) / 1000 + (geo.screen_width * 6) / 1000;
                    media_title.max_width = btn_w - (geo.screen_width * 2) / 100 - reserved_icon;
                } else {
                    media_title.max_width = btn_w - (geo.screen_width * 2) / 100;
                }
                media_title.oversize_mode = OVERSIZE_SHRINK;
            }
            entry->title_texture = render_text_texture(entry->title, &media_title, &entry->text_rect, &h);
            if (config.title_oversize_mode == OVERSIZE_SHRINK && h != geo.font_height)
                entry->title_offset = (geo.font_height - h) / 2;

            if (entry->context_cmd != NULL) {
                const char *ctxt_title = entry->context_title ? entry->context_title : "RETIRER LA SOURCE";
                TextInfo ctxt_info = title_info;
                ctxt_info.max_width = (geo.screen_width * 28) / 100;
                ctxt_info.oversize_mode = OVERSIZE_SHRINK;
                entry->context_texture = render_text_texture(ctxt_title, &ctxt_info, &entry->context_rect, &h);
            }
        }
    }
    menu->rendered = true;
}

static void free_menu_detail_textures(Menu *menu)
{
    if (menu == NULL) return;
    for (int i = 0; i < 6; i++) {
        if (menu->detail_fact_textures[i] != NULL) {
            SDL_DestroyTexture(menu->detail_fact_textures[i]);
            menu->detail_fact_textures[i] = NULL;
        }
    }
    if (menu->detail_poster_texture != NULL) {
        SDL_DestroyTexture(menu->detail_poster_texture);
        menu->detail_poster_texture = NULL;
    }
    if (menu->detail_title_texture != NULL) {
        SDL_DestroyTexture(menu->detail_title_texture);
        menu->detail_title_texture = NULL;
    }
    if (menu->detail_original_title_texture != NULL) {
        SDL_DestroyTexture(menu->detail_original_title_texture);
        menu->detail_original_title_texture = NULL;
    }
    if (menu->detail_metadata_texture != NULL) {
        SDL_DestroyTexture(menu->detail_metadata_texture);
        menu->detail_metadata_texture = NULL;
    }
    if (menu->detail_synopsis_texture != NULL) {
        SDL_DestroyTexture(menu->detail_synopsis_texture);
        menu->detail_synopsis_texture = NULL;
    }
}

static void free_menu_entries(Menu *menu)
{
    if (menu == NULL) return;
    free_media_wall(menu);
    free_menu_detail_textures(menu);
    Entry *entry = menu->first_entry;
    while (entry != NULL) {
        Entry *next = entry->next;
        if (entry->icon != NULL) SDL_DestroyTexture(entry->icon);
        if (entry->icon_selected != NULL) SDL_DestroyTexture(entry->icon_selected);
        if (entry->title_texture != NULL) SDL_DestroyTexture(entry->title_texture);
        if (entry->context_texture != NULL) SDL_DestroyTexture(entry->context_texture);
        free(entry->title);
        free(entry->icon_path);
        free(entry->icon_selected_path);
        free(entry->cmd);
        free(entry->context_cmd);
        free(entry->context_title);
        free(entry);
        entry = next;
    }
    menu->first_entry = NULL;
    menu->num_entries = 0;
    menu->rendered = false;
    menu->root_entry = NULL;
    menu->last_selected_entry = NULL;
}

static void reload_menu_section(Menu *menu)
{
    static bool is_reloading = false;
    if (is_reloading) return;
    if (menu == NULL || menu->name == NULL || config.config_file_path == NULL) return;

    is_reloading = true;
    FILE *f = fopen(config.config_file_path, "r");
    if (f == NULL) {
        is_reloading = false;
        return;
    }

    char line[2048];
    bool in_section = false;
    Entry *new_first = NULL;
    Entry *new_last = NULL;
    int count = 0;

    while (fgets(line, sizeof(line), f) != NULL) {
        char *p = line;
        while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == ';' || *p == '\r' || *p == '\n' || *p == '\0') continue;
        if (*p == '[') {
            char *end = strchr(p, ']');
            if (end != NULL) {
                *end = '\0';
                if (!strcmp(p + 1, menu->name)) {
                    in_section = true;
                    free_menu_detail(menu);
                } else if (in_section) {
                    break;
                }
            }
            continue;
        }
        if (!in_section) continue;

        char *eq = strchr(p, '=');
        if (eq == NULL) continue;
        *eq = '\0';
        char *key = p;
        char *val = eq + 1;
        while (*key && (key[strlen(key)-1] == ' ' || key[strlen(key)-1] == '\t')) key[strlen(key)-1] = '\0';
        while (*val == ' ' || *val == '\t') val++;
        val[strcspn(val, "\r\n")] = '\0';

        if (!strcmp(key, "BackgroundImage")) {
            free(menu->background_path);
            menu->background_path = strdup(val);
            clean_path(menu->background_path);
            continue;
        }

        if (!strcmp(key, "Layout")) {
            if (!strcmp(val, "MovieDetail")) {
                menu->layout = LAYOUT_MOVIE_DETAIL;
            } else if (!strcmp(val, "MediaWall")) {
                menu->layout = LAYOUT_MEDIA_WALL;
            } else {
                menu->layout = LAYOUT_DEFAULT;
            }
            continue;
        }

        if (!strcmp(key, "Poster")) {
            free(menu->detail_poster_path);
            menu->detail_poster_path = strdup(val);
            clean_path(menu->detail_poster_path);
            continue;
        }

        if (!strcmp(key, "Title")) {
            free(menu->detail_title);
            menu->detail_title = strdup(val);
            continue;
        }

        if (!strcmp(key, "OriginalTitle")) {
            free(menu->detail_original_title);
            menu->detail_original_title = strdup(val);
            continue;
        }

        if (!strcmp(key, "Metadata")) {
            free(menu->detail_metadata);
            menu->detail_metadata = strdup(val);
            continue;
        }
        if (strlen(key) == 5 && !strncmp(key, "Fact", 4) &&
            key[4] >= '1' && key[4] <= '5') {
            int fact = key[4] - '1';
            free(menu->detail_facts[fact]);
            menu->detail_facts[fact] = strdup(val);
            continue;
        }
        if (!strcmp(key, "Fact6")) {
            free(menu->detail_source_colorimetry);
            menu->detail_source_colorimetry = strdup(val);
            continue;
        }

        if (strncmp(key, "Synopsis", 8) == 0) {
            int idx = atoi(key + 8);
            if (idx <= 0) idx = 1;
            if (idx < 32) {
                free(menu->synopsis_chunks[idx]);
                menu->synopsis_chunks[idx] = strdup(val);
            }
            continue;
        }

        if (strncmp(key, "Entry", 5) == 0) {
            char *delim = ";";
            char *title_token = strtok(val, delim);
            char *icon_token = strtok(NULL, delim);
            char *cmd_token = strtok(NULL, delim);
            char *context_cmd_token = strtok(NULL, delim);
            char *context_title_token = strtok(NULL, "");
            if (title_token && icon_token && cmd_token) {
                Entry *e = calloc(1, sizeof(Entry));
                e->title = strdup(title_token);
                e->icon_path = strdup(icon_token);
                clean_path(e->icon_path);
                e->cmd = strdup(cmd_token);
                if (context_cmd_token)
                    e->context_cmd = strdup(context_cmd_token);
                if (context_title_token)
                    e->context_title = strdup(context_title_token);
                count++;
                if (new_last == NULL) {
                    new_first = e;
                    new_last = e;
                } else {
                    new_last->next = e;
                    e->previous = new_last;
                    new_last = e;
                }
            }
        }
    }
    fclose(f);

    if (new_first != NULL) {
        Entry *old_selected = menu->last_selected_entry;
        char *saved_cmd = (old_selected && old_selected->cmd) ? strdup(old_selected->cmd) : NULL;
        free_menu_entries(menu);
        menu->first_entry = new_first;
        menu->num_entries = count;
        assemble_menu_synopsis(menu);
        menu->root_entry = menu->first_entry;
        menu->last_selected_entry = menu->first_entry;
        menu->highlight_position = 0;
        menu->page = 0;
        if (new_first->cmd != NULL && strstr(new_first->cmd, "openhtpc-bind-disc") != NULL) {
            // When entering or in AMBIGUOUS state: candidate 1 is default focus
            if (saved_cmd != NULL) {
                if (strstr(saved_cmd, "openhtpc-bind-disc") != NULL) {
                    for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
                        if (e->cmd && !strcmp(e->cmd, saved_cmd)) {
                            menu->last_selected_entry = e;
                            break;
                        }
                    }
                }
                free(saved_cmd);
            }
        } else if (saved_cmd != NULL) {
            for (Entry *e = menu->first_entry; e != NULL; e = e->next) {
                if (e->cmd && !strcmp(e->cmd, saved_cmd)) {
                    menu->last_selected_entry = e;
                    break;
                }
            }
            free(saved_cmd);
        }
        /* The logical DISQUE entry list is stable (e.g. LIRE LE DVD).  Updating
         * its presentation must not rewrite page/selection ownership.
         * Keep refreshed off-screen menus unrendered.  load_menu() renders them
         * when entered, while the visible menu is rendered immediately below. */
        if (current_menu == menu) {
            load_menu(menu, false, false);
        }
    }
    is_reloading = false;
}

static bool is_media_menu_name(const char *name)
{
    return name != NULL && (!strcmp(name, "MEDIA_ROOT") || !strncmp(name, "MEDIA_", 6));
}

static bool config_has_menu_section(const char *name)
{
    if (name == NULL || config.config_file_path == NULL) return false;
    FILE *stream = fopen(config.config_file_path, "r");
    if (stream == NULL) return false;
    char line[2048];
    bool found = false;
    while (fgets(line, sizeof(line), stream) != NULL) {
        char *start = line;
        while (*start == ' ' || *start == '\t') start++;
        if (*start != '[') continue;
        char *end = strchr(start, ']');
        if (end == NULL) continue;
        *end = '\0';
        if (!strcmp(start + 1, name)) {
            found = true;
            break;
        }
    }
    fclose(stream);
    return found;
}

static bool read_media_generation(char *generation, size_t generation_size)
{
    if (generation == NULL || generation_size == 0 || config.config_file_path == NULL) return false;
    FILE *stream = fopen(config.config_file_path, "r");
    if (stream == NULL) return false;
    char line[2048];
    bool found = false;
    if (fgets(line, sizeof(line), stream) != NULL) {
        const char *marker = strstr(line, "media_generation=");
        if (marker != NULL) {
            marker += strlen("media_generation=");
            size_t length = strcspn(marker, " \t\r\n");
            if (length > 0 && length < generation_size) {
                memcpy(generation, marker, length);
                generation[length] = '\0';
                found = true;
            }
        }
    }
    fclose(stream);
    return found;
}

/* A live MEDIA graph commit replaces the token generation for every MEDIA
 * descendant, including menus which Flex loaded lazily before the mutation.
 * Refresh the complete cached MEDIA family, not only the currently visible
 * section.  Sections removed by the new graph are made empty so no stale
 * action remains selectable through an existing back/menu pointer. */
static void reload_media_menu_sections(void)
{
    bool current_removed = false;
    for (Menu *menu = config.first_menu; menu != NULL; menu = menu->next) {
        if (!is_media_menu_name(menu->name)) continue;
        if (config_has_menu_section(menu->name)) {
            reload_menu_section(menu);
        } else {
            if (menu == current_menu) current_removed = true;
            free_menu_entries(menu);
        }
    }
    if (current_removed)
        load_menu_by_name("MEDIA_ROOT", false, true);
}

static void refresh_current_menu_background_and_entries(void)
{
    static ino_t observed_cfg_inode = 0;
    static time_t observed_cfg_mtime = 0;
    static off_t observed_cfg_size = 0;
    static char observed_media_generation[256] = "";
    static ino_t observed_bg_inode = 0;
    static off_t observed_bg_size = 0;

    if (current_menu == NULL) return;

    if (current_menu->background_path != NULL) {
        struct stat bg_info;
        if (stat(current_menu->background_path, &bg_info) == 0) {
            if (bg_info.st_ino != observed_bg_inode || bg_info.st_size != observed_bg_size) {
                SDL_Texture *next = load_texture_from_file(current_menu->background_path);
                if (next != NULL) {
                    if (current_menu->background_texture != NULL)
                        SDL_DestroyTexture(current_menu->background_texture);
                    current_menu->background_texture = next;
                    observed_bg_inode = bg_info.st_ino;
                    observed_bg_size = bg_info.st_size;
                }
            }
        }
    }

    if (config.config_file_path != NULL) {
        struct stat cfg_info;
        if (stat(config.config_file_path, &cfg_info) == 0) {
            if (cfg_info.st_ino != observed_cfg_inode || cfg_info.st_mtime != observed_cfg_mtime || cfg_info.st_size != observed_cfg_size) {
                observed_cfg_inode = cfg_info.st_ino;
                observed_cfg_mtime = cfg_info.st_mtime;
                observed_cfg_size = cfg_info.st_size;
                char media_generation[256] = "";
                bool has_media_generation = read_media_generation(media_generation, sizeof(media_generation));
                bool media_generation_changed = (
                    has_media_generation
                    && observed_media_generation[0] != '\0'
                    && strcmp(media_generation, observed_media_generation) != 0
                );
                if (has_media_generation) {
                    snprintf(observed_media_generation, sizeof(observed_media_generation), "%s", media_generation);
                }
                if (media_generation_changed)
                    reload_media_menu_sections();
                else
                    reload_menu_section(current_menu);
            }
        }
    }
}

static void refresh_live_optical_state(void)
{
    static time_t observed_mtime = 0;
    static off_t observed_size = 0;
    if (config.live_optical_state == NULL || config.first_menu == NULL || config.first_menu->first_entry == NULL)
        return;
    struct stat info;
    if (stat(config.live_optical_state, &info) != 0 || (info.st_mtime == observed_mtime && info.st_size == observed_size))
        return;
    FILE *stream = fopen(config.live_optical_state, "r");
    if (stream == NULL) return;
    char title[1024], icon_path[MAX_PATH_CHARS + 1], state_name[64], device[MAX_PATH_CHARS + 1], disc_title[1024], generation[64];
    if (fgets(title, sizeof(title), stream) == NULL || fgets(icon_path, sizeof(icon_path), stream) == NULL) {
        fclose(stream); return;
    }
    if (fgets(state_name, sizeof(state_name), stream) == NULL || fgets(device, sizeof(device), stream) == NULL ||
        fgets(disc_title, sizeof(disc_title), stream) == NULL || fgets(generation, sizeof(generation), stream) == NULL) {
        fclose(stream); return;
    }
    char auto_open_str[32] = "0", eject_home_str[32] = "0";
    if (fgets(auto_open_str, sizeof(auto_open_str), stream) != NULL) {
        auto_open_str[strcspn(auto_open_str, "\r\n")] = 0;
    }
    if (fgets(eject_home_str, sizeof(eject_home_str), stream) != NULL) {
        eject_home_str[strcspn(eject_home_str, "\r\n")] = 0;
    }
    fclose(stream); title[strcspn(title, "\r\n")] = 0; icon_path[strcspn(icon_path, "\r\n")] = 0;
    state_name[strcspn(state_name, "\r\n")] = 0; device[strcspn(device, "\r\n")] = 0;
    disc_title[strcspn(disc_title, "\r\n")] = 0; generation[strcspn(generation, "\r\n")] = 0;
    Entry *entry = config.first_menu->first_entry;
    SDL_Texture *new_icon = load_texture_from_file(icon_path);
    SDL_Rect new_rect = {0}; int height = 0;
    SDL_Texture *new_title = render_text_texture(title, &title_info, &new_rect, &height);
    if (new_icon != NULL && new_title != NULL) {
        SDL_DestroyTexture(entry->icon); SDL_DestroyTexture(entry->title_texture);
        free(entry->title); free(entry->icon_path);
        entry->title = strdup(title); entry->icon_path = strdup(icon_path);
        entry->icon = new_icon; entry->title_texture = new_title; entry->text_rect.w = new_rect.w; entry->text_rect.h = new_rect.h;
        if (current_menu == config.first_menu) load_menu(current_menu, false, false);
        Menu *disc = get_menu("DISQUE");
        if (disc != NULL) {
            reload_menu_section(disc);
            if (disc->background_path != NULL) {
                SDL_Texture *next_background = load_texture_from_file(disc->background_path);
                if (next_background != NULL) {
                    SDL_DestroyTexture(disc->background_texture);
                    disc->background_texture = next_background;
                }
            }
        }
        static int last_auto_opened_generation = -1;
        static int last_eject_home_generation = -1;
        int gen_num = atoi(generation);
        int auto_open_generation = atoi(auto_open_str);
        int eject_home_generation = atoi(eject_home_str);
        if (auto_open_generation == gen_num && gen_num > 0 && last_auto_opened_generation != gen_num) {
            last_auto_opened_generation = gen_num;
            if (!(state.application_running || state.application_launching) && current_menu == default_menu) {
                Menu *disc = get_menu("DISQUE");
                if (disc != NULL) {
                    if (disc->back == NULL)
                        disc->back = default_menu;
                    load_menu(disc, false, true);
                }
            }
        }
        if (eject_home_generation == gen_num && gen_num > 0 && last_eject_home_generation != gen_num) {
            last_eject_home_generation = gen_num;
            if (!(state.application_running || state.application_launching) && is_disc_sheet())
                load_menu(default_menu, false, true);
        }
    } else {
        if (new_icon != NULL) SDL_DestroyTexture(new_icon);
        if (new_title != NULL) SDL_DestroyTexture(new_title);
    }
    observed_mtime = info.st_mtime; observed_size = info.st_size;
}

static void clear_live_activity_overlay(void)
{
    if (activity_texture != NULL) {
        SDL_DestroyTexture(activity_texture);
        activity_texture = NULL;
    }
    activity_text_rect = (SDL_Rect) {0, 0, 0, 0};
    activity_visible = false;
    activity_level = 0;
}

static void refresh_live_activity_state(void)
{
    static ino_t observed_inode = 0;
    static time_t observed_mtime = 0;
    static off_t observed_size = 0;

    if (config.live_activity_state == NULL) {
        if (activity_visible)
            clear_live_activity_overlay();
        return;
    }

    struct stat info;
    if (stat(config.live_activity_state, &info) != 0) {
        observed_inode = 0;
        observed_mtime = 0;
        observed_size = 0;
        if (activity_visible)
            clear_live_activity_overlay();
        return;
    }

    if (info.st_ino == observed_inode
        && info.st_mtime == observed_mtime
        && info.st_size == observed_size)
        return;

    observed_inode = info.st_ino;
    observed_mtime = info.st_mtime;
    observed_size = info.st_size;

    FILE *stream = fopen(config.live_activity_state, "r");
    if (stream == NULL) {
        clear_live_activity_overlay();
        return;
    }

    char state_name[32] = "";
    char message[512] = "";
    char serial[64] = "";
    bool complete = (
        fgets(state_name, sizeof(state_name), stream) != NULL
        && fgets(message, sizeof(message), stream) != NULL
        && fgets(serial, sizeof(serial), stream) != NULL
    );
    fclose(stream);

    if (!complete) {
        clear_live_activity_overlay();
        return;
    }

    state_name[strcspn(state_name, "\r\n")] = 0;
    message[strcspn(message, "\r\n")] = 0;
    serial[strcspn(serial, "\r\n")] = 0;

    bool serial_valid = serial[0] != '\0';
    for (size_t i = 0; serial_valid && serial[i] != '\0'; i++) {
        if (serial[i] < '0' || serial[i] > '9')
            serial_valid = false;
    }

    bool state_valid = (
        !strcmp(state_name, "IDLE")
        || !strcmp(state_name, "RUNNING")
        || !strcmp(state_name, "SUCCESS")
        || !strcmp(state_name, "FAILED")
    );
    if (!state_valid || !serial_valid || !strcmp(state_name, "IDLE") || message[0] == '\0') {
        clear_live_activity_overlay();
        return;
    }

    TextInfo activity_info = title_info;
    activity_info.max_width = (geo.screen_width * 42) / 100;
    activity_info.oversize_mode = OVERSIZE_SHRINK;

    SDL_Rect next_rect = {0};
    int text_height = 0;
    SDL_Texture *next_texture = render_text_texture(
        message,
        &activity_info,
        &next_rect,
        &text_height
    );
    if (next_texture == NULL) {
        clear_live_activity_overlay();
        return;
    }

    int pad_h = (geo.screen_width * 12) / 1000;
    int pad_v = (geo.screen_height * 8) / 1000;
    if (pad_h < 10) pad_h = 10;
    if (pad_v < 6) pad_v = 6;

    next_rect.x = geo.screen_width - geo.screen_margin - pad_h - next_rect.w;
    next_rect.y = geo.screen_height - geo.screen_margin - pad_v - next_rect.h;

    if (activity_texture != NULL)
        SDL_DestroyTexture(activity_texture);
    activity_texture = next_texture;
    activity_text_rect = next_rect;
    activity_visible = true;
    activity_level = !strcmp(state_name, "RUNNING") ? 1
                   : !strcmp(state_name, "SUCCESS") ? 2
                   : 3;
}

/* Exclude container/tunnel interfaces when choosing the LAN display IP. */
static bool home_is_virtual_interface(const char *name);

/* Prefer the lowest-metric, eligible IPv4 default route (read-only).
 * The route selects a local interface; it NEVER verifies Internet access.
 * No default route is also legitimate for an isolated local network. */
static void home_default_route_interface(char *result, size_t result_size)
{
    if (result == NULL || result_size == 0) return;
    result[0] = '\0';
#ifdef __linux__
    FILE *stream = fopen("/proc/net/route", "r");
    if (stream == NULL) return;
    char line[256];
    unsigned long best_metric = ULONG_MAX;
    if (fgets(line, sizeof(line), stream) != NULL) {
        while (fgets(line, sizeof(line), stream) != NULL) {
            char interface[64] = {0};
            unsigned long destination = 1, gateway = 0, flags = 0;
            unsigned long refs = 0, uses = 0, metric = 0, mask = 1;
            if (sscanf(line, "%63s %lx %lx %lx %lu %lu %lu %lx",
                       interface, &destination, &gateway, &flags,
                       &refs, &uses, &metric, &mask) == 8
                && destination == 0 && mask == 0
                && (flags & 1UL) != 0
                && !home_is_virtual_interface(interface)
                && (metric < best_metric
                    || (metric == best_metric && strcmp(interface, result) < 0))) {
                best_metric = metric;
                snprintf(result, result_size, "%s", interface);
            }
        }
    }
    fclose(stream);
#endif
}

static bool home_is_virtual_interface(const char *name)
{
    if (name == NULL) return true;
    const char *prefixes[] = {"veth", "docker", "virbr", "br-", "cni",
                              "podman", "tun", "tap", "wg", "tailscale"};
    for (size_t i = 0; i < sizeof(prefixes) / sizeof(prefixes[0]); i++) {
        if (strncmp(name, prefixes[i], strlen(prefixes[i])) == 0) return true;
    }
    return false;
}

static HomeNetworkStatus home_network_probe(char *result, size_t result_size)
{
    if (result == NULL || result_size == 0) return HOME_NETWORK_UNKNOWN;
    result[0] = '\0';
#ifdef __linux__
    struct ifaddrs *interfaces = NULL;
    if (getifaddrs(&interfaces) != 0) return HOME_NETWORK_UNKNOWN;

    char default_interface[64] = {0};
    home_default_route_interface(default_interface, sizeof(default_interface));
    bool active_interface_found = false;
    int best_score = -1;
    char best_interface[64] = {0};
    char best_address[48] = {0};

    for (struct ifaddrs *item = interfaces; item != NULL; item = item->ifa_next) {
        if (item->ifa_name == NULL
            || (item->ifa_flags & IFF_LOOPBACK) != 0
            || home_is_virtual_interface(item->ifa_name))
            continue;

        if ((item->ifa_flags & (IFF_UP | IFF_RUNNING)) != (IFF_UP | IFF_RUNNING))
            continue;
        active_interface_found = true;
        if (item->ifa_addr == NULL) continue;

        int family = item->ifa_addr->sa_family;
        char address[48] = {0};
        if (family == AF_INET) {
            const struct sockaddr_in *ipv4 = (const struct sockaddr_in *) item->ifa_addr;
            unsigned long host_ip = ntohl(ipv4->sin_addr.s_addr);
            if (host_ip == 0 || (host_ip >> 24) == 127
                || (host_ip >> 16) == 0xA9FE || (host_ip >> 28) == 0xE)
                continue;
            if (inet_ntop(AF_INET, &ipv4->sin_addr, address, sizeof(address)) == NULL)
                continue;
        } else if (family == AF_INET6) {
            const struct sockaddr_in6 *ipv6 = (const struct sockaddr_in6 *) item->ifa_addr;
            if (IN6_IS_ADDR_LINKLOCAL(&ipv6->sin6_addr)
                || IN6_IS_ADDR_LOOPBACK(&ipv6->sin6_addr)
                || IN6_IS_ADDR_MULTICAST(&ipv6->sin6_addr)
                || IN6_IS_ADDR_UNSPECIFIED(&ipv6->sin6_addr))
                continue;
            if (inet_ntop(AF_INET6, &ipv6->sin6_addr, address, sizeof(address)) == NULL)
                continue;
        } else {
            continue;
        }

        const int is_default = (strcmp(item->ifa_name, default_interface) == 0);
        int score = (is_default ? 100 : 0) + (family == AF_INET ? 20 : 10);
        if (score > best_score || (score == best_score
            && strcmp(item->ifa_name, best_interface) < 0)) {
            best_score = score;
            snprintf(best_interface, sizeof(best_interface), "%s", item->ifa_name);
            snprintf(best_address, sizeof(best_address), "%s", address);
        }
    }
    freeifaddrs(interfaces);
    if (best_score >= 0) {
        snprintf(result, result_size, "%s", best_address);
        return HOME_NETWORK_CONNECTED;
    }
    return active_interface_found ? HOME_NETWORK_UNKNOWN : HOME_NETWORK_DISCONNECTED;
#else
    return HOME_NETWORK_UNKNOWN;
#endif
}

static void refresh_home_network_indicator(void)
{
    Uint32 now = SDL_GetTicks();
    if (home_network_probed && (Uint32) (now - home_network_last_probe) < HOME_NETWORK_POLL_MS)
        return;
    home_network_last_probe = now;
    home_network_probed = true;

    char next_address[sizeof(home_network_address)] = {0};
    HomeNetworkStatus next_status = home_network_probe(next_address, sizeof(next_address));
    if (next_status == home_network_status
        && strcmp(next_address, home_network_address) == 0
        && home_network_texture != NULL)
        return;

    home_network_status = next_status;
    snprintf(home_network_address, sizeof(home_network_address), "%s", next_address);
    const char *label = next_status == HOME_NETWORK_CONNECTED
        ? next_address
        : next_status == HOME_NETWORK_DISCONNECTED
            ? "Réseau déconnecté" : "IP indisponible";

    if (home_network_texture != NULL) {
        SDL_DestroyTexture(home_network_texture);
        home_network_texture = NULL;
    }
    if (title_info.font == NULL || renderer == NULL) return;
    SDL_Color color = {238, 244, 250, 255};
    SDL_Surface *surface = TTF_RenderUTF8_Blended(title_info.font, label, color);
    if (surface == NULL) return;
    home_network_texture = SDL_CreateTextureFromSurface(renderer, surface);
    if (home_network_texture != NULL) {
        int target_h = (geo.screen_height * 19) / 1000;
        if (target_h < 16) target_h = 16;
        int target_w = surface->h > 0 ? surface->w * target_h / surface->h : 0;
        const int max_w = (geo.screen_width * 28) / 100;
        if (target_w > max_w && max_w > 0) {
            /* Preserve glyph proportions for long IPv6 addresses. */
            target_h = target_h * max_w / target_w;
            target_w = max_w;
        }
        home_network_text_rect = (SDL_Rect){0, 0, target_w, target_h};
    }
    SDL_FreeSurface(surface);
}

static void draw_home_network_indicator(void)
{
    if (!is_home_menu() || !home_network_probed) return;
    int unit = geo.screen_height / 100;
    if (unit < 8) unit = 8;
    const int card_h = unit * 4;
    const int icon_w = unit * 3;
    const int text_w = home_network_texture != NULL ? home_network_text_rect.w : 0;
    const int card_w = icon_w + text_w + unit * 3;
    SDL_Rect card = {
        geo.screen_width - geo.screen_margin - card_w,
        geo.screen_height - geo.screen_margin - card_h,
        card_w, card_h
    };
    /* The existing async activity notification also occupies bottom-right. */
    if (activity_visible && activity_texture != NULL)
        card.y = activity_text_rect.y - unit * 2 - card_h;

    fill_rounded_rect(renderer, &card, unit, (SDL_Color){12, 25, 40, 170});
    SDL_Color accent = home_network_status == HOME_NETWORK_CONNECTED
        ? (SDL_Color){55, 185, 220, 220}
        : home_network_status == HOME_NETWORK_DISCONNECTED
            ? (SDL_Color){175, 105, 105, 215}
            : (SDL_Color){168, 175, 184, 215};
    int icon_x = card.x + unit;
    int icon_y = card.y + (card.h - unit * 2) / 2;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 230, 242, 248, 215);
    SDL_Rect monitor = {icon_x, icon_y, unit * 2, unit * 13 / 10};
    SDL_RenderDrawRect(renderer, &monitor);
    SDL_RenderDrawLine(renderer, icon_x + unit, monitor.y + monitor.h,
                       icon_x + unit, monitor.y + monitor.h + unit / 2);
    SDL_RenderDrawLine(renderer, icon_x + unit / 2, monitor.y + monitor.h + unit / 2,
                       icon_x + unit * 3 / 2, monitor.y + monitor.h + unit / 2);
    SDL_Rect dot = {icon_x + unit * 2, icon_y - unit / 3, unit, unit};
    fill_rounded_rect(renderer, &dot, unit / 2, accent);

    if (home_network_texture != NULL) {
        SDL_Rect text = home_network_text_rect;
        text.x = card.x + icon_w + unit * 2;
        text.y = card.y + (card.h - text.h) / 2;
        SDL_RenderCopy(renderer, home_network_texture, NULL, &text);
    }
}

/* P0 V5 modal is purely in-process, non-modal to the persistent service,
 * but blocks ordinary Flex navigation until a choice or B/cancel.
 * The trusted token is always revalidated by openhtpc-play before MPV. */
static bool resume_token_valid(const char *token)
{
    if (token == NULL || strlen(token) != 37 || strncmp(token, "mact_", 5) != 0)
        return false;
    for (int i = 5; i < 37; i++)
        if (!((token[i] >= '0' && token[i] <= '9') ||
              (token[i] >= 'a' && token[i] <= 'f')))
            return false;
    return true;
}

static bool resume_player_path(char *path, size_t length)
{
    const char *install = getenv("OPENHTPC_INSTALL_DIR");
    const char *home = getenv("HOME");
    int n = -1;
    if (install != NULL && install[0] == '/')
        n = snprintf(path, length, "%s/openhtpc-play", install);
    else if (home != NULL && home[0] == '/')
        n = snprintf(path, length, "%s/.local/lib/openhtpc/openhtpc-play", home);
    return n > 0 && (size_t)n < length && access(path, X_OK) == 0;
}

/* Query a checkpoint only when user selects LIRE LE FILM, never during
 * global HOME regeneration. The returned 0/1/2 is stable and bounded.
 * 0 checkpoint: modal; 1 first play: immediate MPV; 2 invalid: deny.
 */
static int resume_offer_probe(const char *token)
{
    char executable[PATH_MAX];
    if (!resume_token_valid(token) ||
        !resume_player_path(executable, sizeof(executable)))
        return 2;
    pid_t pid = fork();
    if (pid < 0) return 2;
    if (pid == 0) {
        /* Isolate probe descendants so a hung helper cannot leave a
         * background subprocess behind when the 1.5 s budget expires. */
        if (setpgid(0, 0) != 0) _exit(126);
        execl(executable, executable, "--resume-probe", token, (char *)NULL);
        _exit(126);
    }
    int status = 0;
    for (int tries = 0; tries < 30; tries++) {
        pid_t result = waitpid(pid, &status, WNOHANG);
        if (result == pid) {
            /* Even when the probe exits quickly, an untrusted helper may
             * leave descendants alive. Reap their dedicated process group
             * without changing the successful 0/1 probe contract. */
            (void)kill(-pid, SIGKILL);
            return WIFEXITED(status) &&
                (WEXITSTATUS(status) == 0 || WEXITSTATUS(status) == 1)
                    ? WEXITSTATUS(status) : 2;
        }
        if (result < 0) {
            if (errno == EINTR) continue;
            if (getpgid(pid) == pid)
                (void)kill(-pid, SIGKILL);
            (void)kill(pid, SIGKILL);
            (void)waitpid(pid, &status, 0);
            return 2;
        }
        SDL_Delay(50);
    }
    /* The child created its own process group before exec; terminate the
     * entire timed-out probe tree, not just its shell wrapper. */
    if (getpgid(pid) == pid)
        (void)kill(-pid, SIGKILL);
    (void)kill(pid, SIGKILL);
    (void)waitpid(pid, &status, 0);
    log_error("P0 resume checkpoint probe exceeded timeout");
    return 2;
}

static void close_resume_modal(void)
{
    for (int i = 0; i < 5; i++) {
        if (resume_modal_labels[i] != NULL) {
            SDL_DestroyTexture(resume_modal_labels[i]);
            resume_modal_labels[i] = NULL;
        }
        resume_modal_label_width[i] = 0;
        resume_modal_label_height[i] = 0;
    }
    resume_modal_active = false;
    resume_modal_selected = 0;
    resume_modal_token[0] = '\0';
}

static void open_resume_modal(const char *token)
{
    if (!resume_token_valid(token) || !is_movie_detail(current_menu)) return;
    close_resume_modal();
    snprintf(resume_modal_token, sizeof(resume_modal_token), "%s", token);
    const char *labels[5] = {
        "REPRISE DE LECTURE",
        "Comment continuer ?",
        "Reprise de lecture",
        "Lire depuis le début",
        "Retour"
    };
    const SDL_Color white = {239, 247, 255, 255};
    for (int i = 0; i < 5; i++) {
        if (title_info.font == NULL) break;
        SDL_Surface *surface = TTF_RenderUTF8_Blended(
            title_info.font, labels[i], white);
        if (surface == NULL) continue;
        resume_modal_labels[i] = SDL_CreateTextureFromSurface(renderer, surface);
        resume_modal_label_width[i] = surface->w;
        resume_modal_label_height[i] = surface->h;
        SDL_FreeSurface(surface);
    }
    resume_modal_active = true;
    resume_modal_selected = 0;
    log_debug("P0_NATIVE_MODAL_OPEN");
}

static void draw_resume_modal_label(int index, const SDL_Rect *area,
                                    int max_text_height)
{
    if (index < 0 || index >= 5 || resume_modal_labels[index] == NULL ||
        resume_modal_label_width[index] <= 0 ||
        resume_modal_label_height[index] <= 0)
        return;
    int h = max_text_height;
    int w = (resume_modal_label_width[index] * h) /
             resume_modal_label_height[index];
    if (w > area->w) {
        w = area->w;
        h = (resume_modal_label_height[index] * w) /
             resume_modal_label_width[index];
    }
    SDL_Rect destination = {
        area->x + (area->w - w) / 2,
        area->y + (area->h - h) / 2, w, h
    };
    if (index == 0)
        SDL_SetTextureColorMod(resume_modal_labels[index], 65, 205, 255);
    else if (index == 1)
        SDL_SetTextureColorMod(resume_modal_labels[index], 190, 206, 218);
    else
        SDL_SetTextureColorMod(resume_modal_labels[index], 250, 250, 250);
    SDL_RenderCopy(renderer, resume_modal_labels[index], NULL, &destination);
}

static void draw_resume_modal(void)
{
    if (!resume_modal_active) return;
    const int sw = geo.screen_width, sh = geo.screen_height;
    if (sw <= 0 || sh <= 0) return;
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    SDL_SetRenderDrawColor(renderer, 0, 4, 12, 150);
    SDL_Rect shade = {0, 0, sw, sh};
    SDL_RenderFillRect(renderer, &shade);
    /* V5.2 cosmetic-only: a clearly compact, centered popup.
     * 36 x 39% of screen area, approximately 55% less than V5 initial.
     * Every controller, token, checkpoint and playback path is unchanged. */
    SDL_Rect panel = {sw * 32 / 100, sh * 305 / 1000,
                      sw * 36 / 100, sh * 39 / 100};
    int radius = sh / 45;
    SDL_Rect shadow = {panel.x - 12, panel.y - 12,
                       panel.w + 24, panel.h + 24};
    fill_rounded_rect(renderer, &shadow, radius + 6,
                      (SDL_Color){0, 0, 0, 150});
    fill_rounded_rect(renderer, &panel, radius,
                      (SDL_Color){40, 170, 225, 245});
    SDL_Rect inner = {panel.x + 2, panel.y + 2,
                      panel.w - 4, panel.h - 4};
    fill_rounded_rect(renderer, &inner, radius - 1,
                      (SDL_Color){11, 24, 37, 248});
    SDL_Rect bar = {panel.x + panel.w / 15, panel.y + panel.h * 31 / 100,
                    panel.w * 13 / 15, sh / 500 + 2};
    fill_rounded_rect(renderer, &bar, 2,
                      (SDL_Color){35, 198, 255, 210});
    SDL_Rect heading = {panel.x + panel.w / 12, panel.y + panel.h * 7 / 100,
                        panel.w * 10 / 12, panel.h * 11 / 100};
    draw_resume_modal_label(0, &heading, sh * 57 / 1000);
    SDL_Rect sub = {panel.x + panel.w / 14, panel.y + panel.h * 20 / 100,
                    panel.w * 12 / 14, panel.h * 10 / 100};
    draw_resume_modal_label(1, &sub, sh * 32 / 1000);
    int first_y = panel.y + panel.h * 37 / 100;
    int row_h = panel.h * 14 / 100;
    int row_gap = panel.h * 5 / 100;
    for (int i = 0; i < 3; i++) {
        SDL_Rect item = {panel.x + panel.w / 8,
                         first_y + i * (row_h + row_gap),
                         panel.w * 3 / 4, row_h};
        if (i == resume_modal_selected) {
            SDL_Rect outer = {item.x - 3, item.y - 3,
                              item.w + 6, item.h + 6};
            fill_rounded_rect(renderer, &outer, sh / 100,
                              (SDL_Color){39, 200, 255, 215});
            fill_rounded_rect(renderer, &item, sh / 100,
                              (SDL_Color){21, 80, 110, 246});
        } else {
            fill_rounded_rect(renderer, &item, sh / 100,
                              (SDL_Color){30, 43, 57, 238});
        }
        SDL_Rect text_area = {item.x + item.w / 15,
                              item.y, item.w * 13 / 15, item.h};
        draw_resume_modal_label(i + 2, &text_area, sh * 44 / 1000);
    }
}


/* Use exactly the same vetted executable for probe and tracked playback.
 * Shell-quote an arbitrary absolute installed path, including spaces and
 * apostrophes. The token and mode remain strictly validated literals. */
static bool resume_shell_quote_path(const char *path, char *dest, size_t cap)
{
    if (path == NULL || path[0] != '/' || cap < 3)
        return false;
    size_t pos = 0;
    dest[pos++] = '\'';
    for (const char *p = path; *p != '\0'; ++p) {
        if (*p == '\'') {
            const char escaped[] = "'\\''";
            if (pos + sizeof(escaped) >= cap)
                return false;
            memcpy(dest + pos, escaped, sizeof(escaped) - 1);
            pos += sizeof(escaped) - 1;
        } else {
            if (pos + 2 >= cap)
                return false;
            dest[pos++] = *p;
        }
    }
    dest[pos++] = '\'';
    dest[pos] = '\0';
    return true;
}

static void resume_launch_player(const char *token, const char *choice)
{
    if (!resume_token_valid(token))
        return;
    if (choice != NULL && strcmp(choice, "resume") != 0 &&
        strcmp(choice, "restart") != 0)
        return;

    char executable[PATH_MAX];
    char quoted[(PATH_MAX * 4) + 3];
    if (!resume_player_path(executable, sizeof(executable)) ||
        !resume_shell_quote_path(executable, quoted, sizeof(quoted))) {
        log_error("P0 player launch refused: executable path unavailable");
        return;
    }

    char cmd[sizeof(quoted) + 128];
    int n = choice != NULL
        ? snprintf(cmd, sizeof(cmd), ":tracked %s --resume-choice %s %s",
                   quoted, choice, token)
        : snprintf(cmd, sizeof(cmd), ":tracked %s %s", quoted, token);
    if (n > 0 && (size_t)n < sizeof(cmd))
        execute_command(cmd);
    else
        log_error("P0 player launch refused: command path too long");
}

static void launch_resume_modal_choice(const char *token, int choice)
{
    if (choice == 2) return; /* Retour means no action, no MPV. */
    if (choice != 0 && choice != 1) return;
    resume_launch_player(token, choice == 0 ? "resume" : "restart");
}

static void run_resume_modal_action(const char *token)
{
    if (!resume_token_valid(token) || !is_movie_detail(current_menu))
        return;
    if (!tracked_can_launch()) return;
    int offer = resume_offer_probe(token);
    if (offer == 0) {
        log_debug("P0_NATIVE_MODAL_CHECKPOINT_OFFER");
        open_resume_modal(token);
        return;
    }
    if (offer == 1) {
        log_debug("P0_NATIVE_MODAL_FIRST_PLAY_DIRECT");
        resume_launch_player(token, NULL);
    } else {
        log_error("P0 resume probe refused playback due to invalid action");
    }
}

static void draw_activity_overlay(void)
{
    if (!activity_visible || activity_texture == NULL)
        return;

    int pad_h = (geo.screen_width * 12) / 1000;
    int pad_v = (geo.screen_height * 8) / 1000;
    int accent_w = (geo.screen_width * 4) / 1000;
    if (pad_h < 10) pad_h = 10;
    if (pad_v < 6) pad_v = 6;
    if (accent_w < 4) accent_w = 4;

    SDL_Rect card = {
        activity_text_rect.x - pad_h,
        activity_text_rect.y - pad_v,
        activity_text_rect.w + (2 * pad_h),
        activity_text_rect.h + (2 * pad_v)
    };
    SDL_Rect shadow = {
        card.x - 3,
        card.y + 3,
        card.w + 6,
        card.h + 4
    };
    SDL_Color accent = activity_level == 2
        ? (SDL_Color) {72, 180, 110, 220}
        : activity_level == 3
            ? (SDL_Color) {210, 72, 72, 220}
            : (SDL_Color) {55, 185, 220, 220};

    fill_rounded_rect(renderer, &shadow, 13, (SDL_Color) {0, 0, 0, 120});
    fill_rounded_rect(renderer, &card, 12, (SDL_Color) {20, 24, 32, 225});

    SDL_Rect accent_rect = {card.x, card.y, accent_w, card.h};
    fill_rounded_rect(renderer, &accent_rect, 4, accent);
    SDL_RenderCopy(renderer, activity_texture, NULL, &activity_text_rect);
}

/* The non-graphical metadata worker atomically replaces this image.  Reload
 * only on the SDL/UI thread and only after a complete replacement exists. */
static void refresh_disc_sheet_background(void)
{
    static ino_t observed_inode = 0;
    static off_t observed_size = 0;
    Menu *disc = get_menu("DISQUE");
    struct stat info;
    if (disc == NULL || disc->background_path == NULL ||
        stat(disc->background_path, &info) != 0 ||
        (info.st_ino == observed_inode && info.st_size == observed_size))
        return;
    SDL_Texture *next = load_texture_from_file(disc->background_path);
    if (next == NULL) return;
    SDL_DestroyTexture(disc->background_texture);
    disc->background_texture = next;
    observed_inode = info.st_ino;
    observed_size = info.st_size;
}

// A function to move the selection left when clicked by user
static void move_left()
{
    if (current_menu == NULL || current_menu->num_entries == 0 || current_entry == NULL)
        return;
    if (current_menu->root_entry == NULL) {
        current_menu->root_entry = current_menu->first_entry;
        current_entry = current_menu->first_entry;
        current_menu->page = 0; current_menu->highlight_position = 0;
        return;
    }
    // If we are not in leftmost position, move highlight left
    if (current_menu->highlight_position > 0) {
        if (config.highlight)
            highlight->rect.x -= geo.x_advance;
        current_menu->highlight_position--;
        Entry *previous = current_entry->previous;
        if (previous == NULL) {
            current_entry = current_menu->first_entry;
            current_menu->page = 0; current_menu->highlight_position = 0;
            current_menu->root_entry = current_menu->first_entry;
            return;
        }
        current_entry = previous;
    }

    // If we are in leftmost position...
    else if (current_menu->highlight_position == 0 && (current_menu->page > 0 || config.wrap_entries)) {
        unsigned int buttons;
        unsigned int page_size = menu_page_size(current_menu);
        current_entry = current_entry->previous;

        // Load the previous page if there is a valid previous entry
        if (current_entry) {
            buttons = page_size;
            Entry *root = advance_entries(current_menu->root_entry, (int) buttons, DIRECTION_LEFT);
            if (root == NULL) {
                current_entry = current_menu->first_entry; current_menu->root_entry = current_entry;
                current_menu->page = 0; current_menu->highlight_position = 0; return;
            }
            current_menu->root_entry = root;
            current_menu->page--;
        }

        // If the user has the wrap entries setting, select the last entry in the menu
        else {
            current_entry = advance_entries(current_menu->first_entry, (int) current_menu->num_entries - 1, DIRECTION_RIGHT);
            unsigned int num_pages = DIV_ROUND_UP(current_menu->num_entries, page_size);
            current_menu->root_entry = advance_entries(current_menu->root_entry,
                (int) ((num_pages - 1 - current_menu->page) * page_size),
                DIRECTION_RIGHT
            );
            current_menu->page = num_pages - 1;
            buttons = current_menu->num_entries - current_menu->page * page_size;
        }

        if (current_entry == NULL || current_menu->root_entry == NULL || buttons == 0) return;
        calculate_button_geometry(current_menu->root_entry, (int) buttons);
        if (config.highlight)
            highlight->rect.x = current_entry->icon_rect.x - config.highlight_hpadding;
        current_menu->highlight_position = buttons - 1;
    }
}

// A function to move the selection right when clicked by the user
static void move_right()
{
    if (current_menu == NULL || current_menu->num_entries == 0 || current_entry == NULL)
        return;
    unsigned int page_size = menu_page_size(current_menu);
    // If we are not in the rightmost position, move highlight right
    if ((int) current_menu->highlight_position < (geo.num_buttons - 1)) {
        if (config.highlight)
            highlight->rect.x += geo.x_advance;
        current_menu->highlight_position++;
        current_entry = current_entry->next;
    }

    // If we are in the rightmost postion, but there are more entries in the menu, load next page
    else if (current_menu->highlight_position + current_menu->page*page_size <
    (current_menu->num_entries - 1)) {
        unsigned int buttons = current_menu->num_entries - (current_menu->page + 1)*page_size;
        if (buttons > page_size)
            buttons = page_size;
        current_entry = current_entry->next;
        current_menu->root_entry = current_entry;
        calculate_button_geometry(current_menu->root_entry, (int) buttons);
        if (config.highlight)
            highlight->rect.x = current_entry->icon_rect.x - config.highlight_hpadding;
        current_menu->page++;
        current_menu->highlight_position = 0;
    }

    // If user has the wrap entries setting, reset menu to first entry
    else if (config.wrap_entries) {
        current_entry = current_menu->first_entry;
        current_menu->root_entry = current_entry;
        current_menu->highlight_position = 0;
        current_menu->page = 0;
        if (config.highlight)
            highlight->rect.x = current_entry->icon_rect.x - config.highlight_hpadding;
        calculate_button_geometry(current_menu->root_entry, (int) MIN(current_menu->num_entries, page_size));
    }
}

// A function to load a submenu
static void load_submenu(const char *submenu)
{
    current_menu->last_selected_entry = current_entry;
    load_menu_by_name(submenu, true, true);
}

// A function to load the previous menu
static void load_back_menu(Menu *menu)
{
    if (menu == NULL)
        return;
    if (menu->back != NULL) {
        /* Preserve the exact action button on MovieDetail after returning
         * from an identification or other child sheet. MediaWall keeps its
         * already validated poster selection behavior unchanged. */
        const bool preserve_action = is_movie_detail(menu->back);
        load_menu(menu->back, false,
                  preserve_action ? false :
                  media_wall_reset_on_back(is_media_wall(menu->back),
                                           config.reset_on_back));
    }
    else if (default_menu != NULL && menu != default_menu)
        load_menu(default_menu, false, config.reset_on_back);
}

// A function to update the screen with all visible textures
static void draw_screen()
{
    // Draw background
    SDL_RenderClear(renderer);
    if (!(state.application_launching && config.on_launch == ON_LAUNCH_BLANK)) {
        if (current_menu != NULL && current_menu->background_texture != NULL)
            SDL_RenderCopy(renderer, current_menu->background_texture, NULL, NULL);
        else if (config.background_mode == BACKGROUND_IMAGE || config.background_mode == BACKGROUND_SLIDESHOW)
            SDL_RenderCopy(renderer, background_texture, NULL, NULL);

        if (config.background_mode == BACKGROUND_SLIDESHOW && state.slideshow_transition)
            SDL_RenderCopy(renderer, slideshow->transition_texture, NULL, NULL);

        // Draw background overlay
        if (config.background_overlay)
            SDL_RenderCopy(renderer, background_overlay, NULL, NULL);

        // Draw scroll indicators
        if (!is_media_wall(current_menu) && config.scroll_indicators &&
        (current_menu->page*menu_page_size(current_menu) + (unsigned int) geo.num_buttons) <= (current_menu->num_entries - 1))
            SDL_RenderCopy(renderer, scroll->texture, NULL, &scroll->rect_right);

        if (!is_media_wall(current_menu) && config.scroll_indicators && current_menu->page > 0)
            SDL_RenderCopyEx(renderer, scroll->texture, NULL, &scroll->rect_left, 0, NULL, SDL_FLIP_HORIZONTAL);

        // Draw clock
        if (config.clock_enabled) {
            SDL_RenderCopy(renderer, clk->time_texture, NULL, &clk->time_rect);
            if (config.clock_show_date)
                SDL_RenderCopy(renderer, clk->date_texture, NULL, &clk->date_rect);
        }

        if (is_media_wall(current_menu)) {
            draw_media_wall();
            draw_home_network_indicator();
            draw_activity_overlay();
            if (state.screensaver_active)
                SDL_RenderCopy(renderer, screensaver->texture, NULL, NULL);


#ifdef OPENHTPC_LAB_QA_CAPTURE
            /* QA-only screenshots: real cached posters, HOME and config remain isolated. */
            bool qa_actions_capture = getenv("OPENHTPC_LAB_QA_SCENARIO") != NULL &&
                strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"),
                       "uxf1-actions") == 0;
            bool tabs_test = getenv("OPENHTPC_LAB_QA_SCENARIO") != NULL &&
                (strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"), "tabs") == 0 ||
                 qa_actions_capture);
            bool capture = (qa_actions_capture && lab_qa_loop == 245) ||
                           (tabs_test
                ? (lab_qa_loop == 20 || lab_qa_loop == 39 ||
                   lab_qa_loop == 54 || lab_qa_loop == 90 ||
                   lab_qa_loop == 104 || lab_qa_loop == 139 ||
                   lab_qa_loop == 155 || lab_qa_loop == 175 ||
                   lab_qa_loop == 195 || lab_qa_loop == 215)
                : (lab_qa_loop == 20 || lab_qa_loop == 36 ||
                   lab_qa_loop == 44 || lab_qa_loop == 60 ||
                   lab_qa_loop == 100 || lab_qa_loop == 130 ||
                   lab_qa_loop == 198 || lab_qa_loop == 235));
            if (capture) {
                const char *prefix = getenv("OPENHTPC_LAB_QA_SCREENSHOT_PREFIX");
                if (prefix != NULL && prefix[0] == '/') {
                    int width = 0, height = 0;
                    if (SDL_GetRendererOutputSize(renderer, &width, &height) == 0
                            && width > 0 && height > 0 && width <= 4096
                            && height <= 2304) {
                        SDL_Surface *frame = SDL_CreateRGBSurfaceWithFormat(
                            0, width, height, 32, SDL_PIXELFORMAT_ARGB8888);
                        if (frame != NULL) {
                            if (SDL_RenderReadPixels(renderer, NULL,
                                SDL_PIXELFORMAT_ARGB8888,
                                frame->pixels, frame->pitch) == 0) {
                                char name[1024];
                                const char *stage = tabs_test ?
                                    (lab_qa_loop == 20 ? "initial" :
                                     lab_qa_loop == 39 ? "tab-films" :
                                     lab_qa_loop == 54 ? "tab-disque" :
                                     lab_qa_loop == 90 ? "back-disque" :
                                     lab_qa_loop == 104 ? "tab-dossiers" :
                                     lab_qa_loop == 139 ? "back-dossiers" :
                                     lab_qa_loop == 155 ? "posters" :
                                     lab_qa_loop == 175 ? "poster-next" :
                                     lab_qa_loop == 195 ? "film-detail" :
                                     qa_actions_capture && lab_qa_loop == 245 ?
                                         "return-film" : "return-film") :
                                    (lab_qa_loop == 20 ? "initial" :
                                     lab_qa_loop == 36 ? "focus-start" :
                                     lab_qa_loop == 44 ? "focus-mid" :
                                     lab_qa_loop == 60 ? "right" :
                                     lab_qa_loop == 100 ? "down" :
                                     lab_qa_loop == 130 ? "return" :
                                     lab_qa_loop == 198 ? "scrolled" : "return-scroll");
                                snprintf(name, sizeof(name), "%s-%s.png",
                                         prefix, stage);
                                int rc = IMG_SavePNG(frame, name);
                                fprintf(stderr, "LAB_QA_CAPTURE %s rc=%d %dx%d\n",
                                    name, rc, width, height);
                            } else {
                                fprintf(stderr, "LAB_QA_READPIXELS %s\n",
                                    SDL_GetError());
                            }
                            SDL_FreeSurface(frame);
                        }
                    }
                }
            }
#endif
            SDL_RenderPresent(renderer);
            if (!config.vsync) {
                Uint32 elapsed_ms = SDL_GetTicks() - ticks.main;
                if (elapsed_ms < refresh_period)
                    SDL_Delay(refresh_period - elapsed_ms);
            }
            return;
        }

        // OpenHTPC MediaSidebar :
        // réaligne le highlight sur l'entrée verticale
        // actuellement sélectionnée.
        if (config.highlight && (is_media_sidebar() || is_media_list())) {

            highlight->rect.x =
                current_entry->icon_rect.x
                -
                config.highlight_hpadding;

            highlight->rect.y =
                current_entry->icon_rect.y
                -
                config.highlight_vpadding;
            if (is_media_list()) {
                highlight->rect.x = (geo.screen_width * 6) / 100;
                highlight->rect.y = current_entry->icon_rect.y - (geo.screen_height * 2) / 100;
                highlight->rect.w = (geo.screen_width * 88) / 100;
                highlight->rect.h = current_entry->icon_rect.h + (geo.screen_height * 4) / 100;
            }
        }

        if (is_disc_ambiguous()) {
            Entry *cand_entry = current_menu->root_entry;
            for (int i = 0; i < geo.num_buttons && cand_entry != NULL; i++) {
                bool selected = (cand_entry == current_entry);
                if (cand_entry->cmd != NULL && strstr(cand_entry->cmd, "openhtpc-bind-disc") != NULL) {
                    int card_w = (geo.screen_width * 64) / 100;
                    int card_h = (geo.screen_height * 115) / 1000;
                    int start_x = (geo.screen_width * 305) / 1000;
                    int card_y = cand_entry->icon_rect.y - ((card_h - cand_entry->icon_rect.h) / 2);
                    SDL_Rect card_rect = { start_x, card_y, card_w, card_h };

                    SDL_Rect shadow = { card_rect.x - 4, card_rect.y + 3, card_rect.w + 8, card_rect.h + 6 };
                    fill_rounded_rect(renderer, &shadow, 18, (SDL_Color){0, 0, 0, 100});

                    if (selected) {
                        SDL_Rect glow = { card_rect.x - 3, card_rect.y - 3, card_rect.w + 6, card_rect.h + 6 };
                        fill_rounded_rect(renderer, &glow, 20, (SDL_Color){32, 200, 255, 90});
                    }

                    fill_rounded_rect(renderer, &card_rect, 16,
                        selected ? (SDL_Color){32, 200, 255, 245} : (SDL_Color){34, 199, 255, 55});

                    SDL_Rect inner = { card_rect.x + 2, card_rect.y + 2, card_rect.w - 4, card_rect.h - 4 };
                    fill_rounded_rect(renderer, &inner, 14,
                        selected ? (SDL_Color){10, 36, 72, 245} : (SDL_Color){6, 18, 36, 215});
                } else {
                    draw_home_card(&cand_entry->icon_rect, selected);
                }
                cand_entry = cand_entry->next;
            }
        } else if (is_disc_sheet() || is_system_subpage() || is_movie_detail(current_menu)) {
            Entry *action = current_menu->root_entry;
            for (int i = 0; i < geo.num_buttons && action != NULL; i++) {
                draw_home_card(&action->icon_rect, action == current_entry);
                action = action->next;
            }
        }
        if (is_system_root()) {
            int rail_width = (geo.screen_width * 38) / 100;
            int row_height = (geo.screen_height * 64) / 1000;
            int gap = (geo.screen_height * 7) / 1000;
            int start_y = (geo.screen_height * 10) / 100;
            Entry *card_entry = current_menu->root_entry;
            for (int i = 0; i < geo.num_buttons && card_entry != NULL; i++) {
                SDL_Rect card_rect = {
                    geo.x_margin,
                    start_y + i * (row_height + gap),
                    rail_width,
                    row_height
                };
                bool selected = (i == (int) current_menu->highlight_position);

                SDL_Rect shadow = { card_rect.x - 4, card_rect.y + 2, card_rect.w + 8, card_rect.h + 4 };
                fill_rounded_rect(renderer, &shadow, 18, (SDL_Color){0, 0, 0, 80});

                if (selected) {
                    SDL_Rect glow = { card_rect.x - 3, card_rect.y - 3, card_rect.w + 6, card_rect.h + 6 };
                    fill_rounded_rect(renderer, &glow, 20, (SDL_Color){32, 200, 255, 60});
                }

                fill_rounded_rect(renderer, &card_rect, 16,
                    selected ? (SDL_Color){32, 200, 255, 230} : (SDL_Color){255, 255, 255, 32});

                SDL_Rect inner = { card_rect.x + 2, card_rect.y + 2, card_rect.w - 4, card_rect.h - 4 };
                fill_rounded_rect(renderer, &inner, 14,
                    selected ? (SDL_Color){10, 36, 68, 240} : (SDL_Color){6, 16, 32, 220});

                card_entry = card_entry->next;
            }
        }

        // Draw movie detail static elements
        if (is_movie_detail(current_menu)) {
            if (current_menu->detail_poster_texture != NULL) {
                SDL_Rect poster_shadow = {
                    current_menu->detail_poster_rect.x - 4,
                    current_menu->detail_poster_rect.y + 4,
                    current_menu->detail_poster_rect.w + 8,
                    current_menu->detail_poster_rect.h + 8
                };
                fill_rounded_rect(renderer, &poster_shadow, 14, (SDL_Color){0, 0, 0, 140});
                SDL_RenderCopy(renderer, current_menu->detail_poster_texture, NULL, &current_menu->detail_poster_rect);
            } else {
                fill_rounded_rect(renderer, &current_menu->detail_poster_rect, 14, (SDL_Color){25, 25, 30, 200});
            }

            if (current_menu->detail_title_texture != NULL) {
                SDL_RenderCopy(renderer, current_menu->detail_title_texture, NULL, &current_menu->detail_title_rect);
            }
            if (current_menu->detail_original_title_texture != NULL) {
                SDL_RenderCopy(renderer, current_menu->detail_original_title_texture, NULL, &current_menu->detail_original_title_rect);
            }
            if (current_menu->detail_metadata_texture != NULL) {
                SDL_RenderCopy(renderer, current_menu->detail_metadata_texture, NULL, &current_menu->detail_metadata_rect);
            }
            /* Compact, consistent cards; each label is a literal CORE fact.
             * Two technical cards share the final row. */
            int fact_pad_x = (geo.screen_width * 10) / 1000;
            int fact_pad_y = (geo.screen_height * 6) / 1000;
            int detail_x = (geo.screen_width * 6) / 100 +
                           (geo.screen_width * 26) / 100 +
                           (geo.screen_width * 4) / 100;
            int detail_width = geo.screen_width * 94 / 100 - detail_x;
            int technical_gap = geo.screen_width * 12 / 1000;
            int technical_width = (detail_width - technical_gap) / 2;
            for (int fi = 0; fi < 6; fi++) {
                if (current_menu->detail_fact_textures[fi] == NULL)
                    continue;
                SDL_Rect text = current_menu->detail_fact_rects[fi];
                SDL_Rect card = {
                    text.x - fact_pad_x, text.y - fact_pad_y,
                    fi < 4 ? detail_width : technical_width,
                    text.h + fact_pad_y * 2
                };
                SDL_Color fill = {13, 29, 53, 233};
                SDL_Color edge = {55, 81, 120, 255};
                if (fi == 1) {
                    fill = (SDL_Color){52, 40, 21, 237};
                    edge = (SDL_Color){150, 112, 55, 255};
                } else if (fi == 5) {
                    MediaWallSourceFormat format = media_wall_parse_source_format(
                        current_menu->detail_source_colorimetry);
                    if (format == MEDIA_WALL_FORMAT_DOLBY_VISION) {
                        fill = (SDL_Color){46, 27, 72, 238};
                        edge = (SDL_Color){139, 94, 189, 255};
                    } else if (format == MEDIA_WALL_FORMAT_HDR10 ||
                               format == MEDIA_WALL_FORMAT_HDR10_PLUS) {
                        fill = (SDL_Color){55, 39, 21, 237};
                        edge = (SDL_Color){151, 113, 53, 255};
                    }
                }
                fill_rounded_rect(renderer, &card,
                                  geo.screen_height / 150, fill);
                SDL_SetRenderDrawColor(renderer, edge.r, edge.g, edge.b, 255);
                SDL_RenderDrawRect(renderer, &card);
                SDL_RenderCopy(renderer, current_menu->detail_fact_textures[fi],
                               NULL, &text);
            }
            if (current_menu->detail_synopsis_texture != NULL) {
                SDL_RenderCopy(renderer, current_menu->detail_synopsis_texture, NULL, &current_menu->detail_synopsis_rect);
            }
        }

        // Draw highlight
        if (config.highlight && !is_home_menu() && !is_disc_sheet() && !is_system_subpage() && !is_system_root() && !is_movie_detail(current_menu))
            SDL_RenderCopy(renderer,
                highlight->texture,
                NULL,
                &highlight->rect
            );

        // Draw buttons
        Entry *entry = current_menu->root_entry;
        SDL_Texture *icon;
        for (int i = 0; i < geo.num_buttons; i++) {
            icon = (entry->icon_selected != NULL && entry == current_entry) ? entry->icon_selected : entry->icon;
            if (is_disc_ambiguous()) {
                if (entry->cmd == NULL || strstr(entry->cmd, "openhtpc-bind-disc") == NULL) {
                    icon = NULL;
                }
            }
            /*
             * OpenHTPC:
             * Preserve the original aspect ratio of entry artwork.
             *
             * Square launcher icons remain unchanged.
             * Portrait movie posters are fitted inside icon_rect
             * without being stretched.
             */
            int texture_w = 0;
            int texture_h = 0;

            SDL_Rect artwork_rect = entry->icon_rect;
            if (is_system_subpage()) {
                int icon_size = (geo.screen_height * 4) / 100;
                int safety_margin = (geo.screen_height * 1) / 100;
                int stack_height = icon_size + safety_margin + entry->text_rect.h;
                artwork_rect.x = entry->icon_rect.x + (entry->icon_rect.w - icon_size) / 2;
                artwork_rect.y = entry->icon_rect.y + (entry->icon_rect.h - stack_height) / 2;
                artwork_rect.w = icon_size;
                artwork_rect.h = icon_size;
            } else if (is_disc_action_sheet() || is_movie_detail(current_menu)) {
                int icon_size = (geo.screen_height * 34) / 1000;
                int icon_gap = (geo.screen_width * 6) / 1000;
                artwork_rect.x = entry->text_rect.x - icon_gap - icon_size;
                artwork_rect.y = entry->icon_rect.y + (entry->icon_rect.h - icon_size) / 2;
                artwork_rect.w = icon_size;
                artwork_rect.h = icon_size;
            }

            if (icon != NULL && SDL_QueryTexture(
                    icon,
                    NULL,
                    NULL,
                    &texture_w,
                    &texture_h
                ) == 0 &&
                texture_w > 0 &&
                texture_h > 0) {

                const double source_ratio =
                    (double) texture_w /
                    (double) texture_h;

                const double target_ratio =
                    (double) artwork_rect.w /
                    (double) artwork_rect.h;

                if (source_ratio > target_ratio) {
                    /*
                     * Landscape image:
                     * full available width.
                     */
                    int target_width = artwork_rect.w;
                    int target_height = artwork_rect.h;
                    int target_x = artwork_rect.x;
                    int target_y = artwork_rect.y;
                    artwork_rect.w = target_width;
                    artwork_rect.h =
                        (int) (
                            target_width /
                            source_ratio
                        );

                    artwork_rect.x =
                        target_x;

                    artwork_rect.y =
                        target_y +
                        (
                            target_height -
                            artwork_rect.h
                        ) / 2;

                } else {
                    /*
                     * Portrait image:
                     * full available height.
                     */
                    int target_width = artwork_rect.w;
                    int target_height = artwork_rect.h;
                    int target_x = artwork_rect.x;
                    int target_y = artwork_rect.y;
                    artwork_rect.h = target_height;
                    artwork_rect.w =
                        (int) (
                            target_height *
                            source_ratio
                        );

                    artwork_rect.y =
                        target_y;

                    artwork_rect.x =
                        target_x +
                        (
                            target_width -
                            artwork_rect.w
                        ) / 2;
                }
            }

            if (icon != NULL && is_home_menu()) {
                Uint8 old_r = 255, old_g = 255, old_b = 255, old_a = 255;
                SDL_GetTextureColorMod(icon, &old_r, &old_g, &old_b);
                SDL_GetTextureAlphaMod(icon, &old_a);

                /* True drop shadow: silhouette only, no card and no coloured halo. */
                SDL_SetTextureColorMod(icon, 0, 0, 0);
                SDL_SetTextureAlphaMod(icon, 22);
                int dx = (geo.screen_width * 5) / 1000;
                int dy = (geo.screen_height * 8) / 1000;
                if (dx < 5) dx = 5;
                if (dy < 7) dy = 7;
                const int shadow_offsets[5][2] = {
                    {0,0},{-2,0},{2,0},{0,-2},{0,2}
                };
                for (int s = 0; s < 5; s++) {
                    SDL_Rect shadow_rect = artwork_rect;
                    shadow_rect.x += dx + shadow_offsets[s][0];
                    shadow_rect.y += dy + shadow_offsets[s][1];
                    SDL_RenderCopy(renderer, icon, NULL, &shadow_rect);
                }

                SDL_SetTextureColorMod(icon, old_r, old_g, old_b);
                SDL_SetTextureAlphaMod(icon, old_a);
            }
            if (icon != NULL)
                SDL_RenderCopy(renderer, icon, NULL, &artwork_rect);

            /* Minimal home selection marker: a thin cyan underline only. */
            if (is_home_menu() && entry == current_entry) {
                int line_w = artwork_rect.w * 44 / 100;
                int line_h = geo.screen_height / 540;
                if (line_w < 36) line_w = 36;
                if (line_h < 3) line_h = 3;
                SDL_Rect selection_line = {
                    artwork_rect.x + (artwork_rect.w - line_w) / 2,
                    artwork_rect.y + artwork_rect.h + (geo.screen_height / 180),
                    line_w, line_h
                };
                fill_rounded_rect(renderer, &selection_line, line_h / 2,
                    (SDL_Color){34, 199, 255, 185});
            }

            if (config.titles_enabled)
                SDL_RenderCopy(renderer, entry->title_texture, NULL, &entry->text_rect);

            if (entry->context_cmd != NULL && entry->context_texture != NULL) {
                bool is_selected_row = (entry == current_entry);
                bool is_focused = is_selected_row && entry->context_selected;
                int pad_h = (geo.screen_width * 14) / 1000;
                int pad_v = (geo.screen_height * 8) / 1000;
                SDL_Rect pill_rect = {
                    entry->context_rect.x - pad_h,
                    entry->context_rect.y - pad_v,
                    entry->context_rect.w + pad_h * 2,
                    entry->context_rect.h + pad_v * 2
                };
                if (is_focused) {
                    SDL_Rect glow = { pill_rect.x - 3, pill_rect.y - 3, pill_rect.w + 6, pill_rect.h + 6 };
                    fill_rounded_rect(renderer, &glow, 16, (SDL_Color){255, 60, 60, 110});
                    fill_rounded_rect(renderer, &pill_rect, 14, (SDL_Color){215, 45, 45, 235});
                } else if (is_selected_row) {
                    fill_rounded_rect(renderer, &pill_rect, 14, (SDL_Color){55, 65, 85, 210});
                } else {
                    fill_rounded_rect(renderer, &pill_rect, 14, (SDL_Color){30, 35, 45, 110});
                }
                SDL_RenderCopy(renderer, entry->context_texture, NULL, &entry->context_rect);
            }
            entry = entry-> next;
        }

        // Draw non-blocking OPENHTPC activity feedback above the menu, but
        // below the screensaver. It never participates in input/navigation.
        draw_home_network_indicator();
        draw_activity_overlay();
        draw_resume_modal();

        // Draw screensaver
        if (state.screensaver_active)
            SDL_RenderCopy(renderer, screensaver->texture, NULL, NULL);
    }
    else
        SDL_RenderFillRect(renderer, NULL);

#ifdef OPENHTPC_LAB_QA_CAPTURE
    /* The main wall takes its own screenshots before an early return.
     * MovieDetail uses the ordinary renderer path: capture it separately,
     * without changing any real production behavior or controller input. */
    if (is_movie_detail(current_menu) &&
        lab_qa_loop == 195 &&
        getenv("OPENHTPC_LAB_QA_SCENARIO") != NULL &&
        (strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"), "tabs") == 0 ||
         strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"), "uxf1-actions") == 0)) {
        const char *prefix = getenv("OPENHTPC_LAB_QA_SCREENSHOT_PREFIX");
        if (prefix != NULL && prefix[0] == '/') {
            int width = 0, height = 0;
            if (SDL_GetRendererOutputSize(renderer, &width, &height) == 0 &&
                width > 0 && height > 0 && width <= 4096 && height <= 2304) {
                SDL_Surface *frame = SDL_CreateRGBSurfaceWithFormat(
                    0, width, height, 32, SDL_PIXELFORMAT_ARGB8888);
                if (frame != NULL) {
                    if (SDL_RenderReadPixels(renderer, NULL,
                        SDL_PIXELFORMAT_ARGB8888, frame->pixels,
                        frame->pitch) == 0) {
                        char name[1024];
                        snprintf(name, sizeof(name), "%s-film-detail.png",
                                 prefix);
                        int rc = IMG_SavePNG(frame, name);
                        int facts_count = 0;
                        for (int i = 0; i < 6; i++)
                            if (current_menu->detail_fact_textures[i] != NULL)
                                facts_count++;
                        fprintf(stderr,
                            "LAB_QA_DETAIL title=%s facts=%d synopsis=%d\n",
                            current_menu->detail_title != NULL ?
                            current_menu->detail_title : "NULL",
                            facts_count,
                            current_menu->detail_synopsis_texture != NULL);
                        fprintf(stderr, "LAB_QA_CAPTURE %s rc=%d %dx%d\n",
                                name, rc, width, height);
                    }
                    SDL_FreeSurface(frame);
                }
            }
        }
    }
#endif
#ifdef OPENHTPC_MODAL_QA
    /* QA-only screenshot; never compiled into the Release payload. */
    if (resume_modal_active) {
        const char *path = getenv("OPENHTPC_MODAL_QA_BMP");
        if (path != NULL && path[0] == '/' && access(path,F_OK) != 0) {
            SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormat(
                0, geo.screen_width, geo.screen_height, 32, SDL_PIXELFORMAT_ARGB8888);
            if (surface != NULL) {
                if (SDL_RenderReadPixels(renderer,NULL,SDL_PIXELFORMAT_ARGB8888,
                                         surface->pixels,surface->pitch)==0)
                    SDL_SaveBMP(surface,path);
                SDL_FreeSurface(surface);
            }
        }
    }
#endif

    // Output to screen
    SDL_RenderPresent(renderer);
    if (!config.vsync) {
        Uint32 elapsed_ms = SDL_GetTicks() - ticks.main;
        if (elapsed_ms < refresh_period)
            SDL_Delay(refresh_period - elapsed_ms);
    }
}

// A function to execute the user's command
static void execute_command(const char *command)
{
    if (command == NULL)
        return;

    if (resume_modal_active) {
        if (!strcmp(command, ":up") || !strcmp(command, ":left")) {
            resume_modal_selected = (resume_modal_selected + 2) % 3;
        } else if (!strcmp(command, ":down") || !strcmp(command, ":right")) {
            resume_modal_selected = (resume_modal_selected + 1) % 3;
        } else if (!strcmp(command, ":back")) {
            close_resume_modal();
        } else if (!strcmp(command, ":select")) {
            char token[sizeof(resume_modal_token)];
            int selected = resume_modal_selected;
            snprintf(token, sizeof(token), "%s", resume_modal_token);
            close_resume_modal();
            launch_resume_modal_choice(token, selected);
        }
        return;
    }


    if (!tracked_guard_command(command))
        return;

    // Copy command into separate buffer
    char *cmd = strdup(command);

    // Parse special commands
    if (cmd[0] == ':') {
        char *delimiter = " ";
        char *special_command = strtok(cmd, delimiter);
        if (!strcmp(special_command, SCMD_SUBMENU)) {
            char *submenu = strtok(NULL, "");
            if (submenu != NULL)
                load_submenu(submenu);
        }
        else if (!strcmp(special_command, ":mediaresumepopup")) {
            char *token = strtok(NULL, " ");
            run_resume_modal_action(token);
        }
        else if (!strcmp(special_command, SCMD_FORK)) {
            char *fork_command = strtok(NULL, "");
            if (fork_command != NULL)
                start_process(fork_command, false, false);
        }
        else if (!strcmp(special_command, SCMD_TRACKED)) {
            char *tracked_command = strtok(NULL, "");
            if (tracked_command == NULL || strlen(tracked_command) == 0) {
                log_error("No command specified for :tracked");
                free(cmd);
                return;
            }
            while (*tracked_command == ' ')
                tracked_command++;
            if (*tracked_command == '\0') {
                log_error("Empty command specified for :tracked");
                free(cmd);
                return;
            }
            if (!tracked_can_launch()) {
                log_debug("Tracked process already running (pid %d), rejecting launch", tracked_get_pid());
                free(cmd);
                return;
            }
            pid_t pid = start_process_tracked(tracked_command);
            if (pid > 0) {
                tracked_start(pid);
                state.application_running = true;
                state.application_launching = false;
                pre_launch();
                if (config.on_launch == ON_LAUNCH_BLANK) {
                    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0xFF);
                    SDL_RenderClear(renderer);
                    SDL_RenderPresent(renderer);
                }
                log_debug("Started tracked application with pid %d", pid);
            } else {
                log_error("Failed to start tracked process: %s", tracked_command);
            }
        }
        else if (!strcmp(special_command, SCMD_APPLY_BACK)) {
            char operation_id[UI_ACTION_OPERATION_ID_MAX] = {0};
            (void) ui_action_trace_begin(operation_id, sizeof(operation_id));
            char *settings_command = strtok(NULL, "");
            Menu *parent = current_menu != NULL ? current_menu->back : NULL;
            if (settings_command != NULL && parent != NULL && run_process_sync(settings_command, operation_id)) {
                ui_action_trace_event("flex_reload_begin", operation_id, 0);
                reload_menu_section(parent);
                /* presentation_mode is global.  Keep an already-created DVD
                 * detail menu coherent when the selector was used in SYSTEME. */
                Menu *disc = get_menu("DISQUE");
                if (disc != NULL && disc != parent)
                    reload_menu_section(disc);
                if (parent->background_path != NULL) {
                    SDL_Texture *next = load_texture_from_file(parent->background_path);
                    if (next != NULL) {
                        if (parent->background_texture != NULL)
                            SDL_DestroyTexture(parent->background_texture);
                        parent->background_texture = next;
                    }
                }
                if (load_menu(parent, false, true) == 0)
                    ui_action_trace_event("flex_ui_ready", operation_id, 0);
                else
                    ui_action_trace_event("flex_ui_reload_failed", operation_id, 0);
            }
        }
        else if (!strcmp(special_command, SCMD_REPLACE)) {
            char *replacement_command = strtok(NULL, "");
            if (replacement_command != NULL && start_process(replacement_command, true, true)) {
                SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0xFF);
                SDL_RenderClear(renderer);
                SDL_RenderPresent(renderer);
                quit(EXIT_SUCCESS);
            }
        }
        else if (!strcmp(special_command, SCMD_LEFT)) {
            if (is_media_wall(current_menu))
                media_wall_move(-1, 0);
            else if (is_media_list() && current_entry != NULL && current_entry->context_selected)
                current_entry->context_selected = false;
            else {
                if (current_entry != NULL) current_entry->context_selected = false;
                move_left();
            }
        }
        else if (!strcmp(special_command, SCMD_RIGHT)) {
            if (is_media_wall(current_menu))
                media_wall_move(1, 0);
            else if (is_media_list() && current_entry != NULL && current_entry->context_cmd != NULL && !current_entry->context_selected)
                current_entry->context_selected = true;
            else {
                if (current_entry != NULL) current_entry->context_selected = false;
                move_right();
            }
        }
        else if (!strcmp(special_command, SCMD_UP)) {
            if (is_media_wall(current_menu)) media_wall_move(0, -1);
            else move_left();
        }
        else if (!strcmp(special_command, SCMD_DOWN)) {
            if (is_media_wall(current_menu)) media_wall_move(0, 1);
            else move_right();
        }
        else if (!strcmp(special_command, SCMD_SELECT)) {
            if (is_media_wall(current_menu) && current_menu->media_wall.tab_focused)
                media_wall_activate_tab();
            else if (current_entry != NULL && current_entry->context_selected && current_entry->context_cmd != NULL)
                execute_command(current_entry->context_cmd);
            else if (current_entry != NULL)
                execute_command(current_entry->cmd);
        }
        else if (!strcmp(special_command, SCMD_HOME))
            load_menu(default_menu, false, true);
        else if (!strcmp(special_command, SCMD_BACK))
            load_back_menu(current_menu);
        else if (!strcmp(special_command, SCMD_QUIT))
            quit(EXIT_SUCCESS);
        else if (!strcmp(special_command, SCMD_SHUTDOWN))
            scmd_shutdown();
        else if (!strcmp(special_command, SCMD_RESTART))
            scmd_restart();
        else if (!strcmp(special_command, SCMD_SLEEP))
            scmd_sleep();
    }

    // Launch external application
    else {
        SDL_Delay(50);
        if (start_process(cmd, true, false)) {
            state.application_launching = true;
            ticks.application_launched = ticks.main;
            /* Playback must be allowed above the retained appliance UI. */
            SDL_SetWindowAlwaysOnTop(window, SDL_FALSE);
            if (config.on_launch == ON_LAUNCH_BLANK)
                SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0xFF);
            else if (config.on_launch == ON_LAUNCH_QUIT) {
                SDL_SetRenderDrawColor(renderer, 0, 0, 0, 0xFF);
                SDL_RenderClear(renderer);
                SDL_RenderPresent(renderer);
                quit(EXIT_SUCCESS);
            }
        }
    }
    free(cmd);
}

// A function to initialize the gamepad struct
static void init_gamepad(Gamepad **gamepad, int device_index)
{
    *gamepad = malloc(sizeof(Gamepad));
    **gamepad = (Gamepad) {
        .device_index = device_index,
        .id = (int) SDL_JoystickGetDeviceInstanceID(device_index),
        .controller = NULL,
        .next = NULL,
        .previous = NULL,
    };
}

// A function to open the SDL controller
static void open_controller(Gamepad *gamepad, bool raise_error)
{
    gamepad->controller = SDL_GameControllerOpen(gamepad->device_index);
    if (gamepad->controller == NULL) {
        if (raise_error)
            log_error("Could not open gamepad at device index %i", config.gamepad_device);
        return;
    }
    if (config.debug && raise_error) {
        char *mapping = SDL_GameControllerMapping(gamepad->controller);
        log_debug("Gamepad Mapping:\n%s", mapping);
        SDL_free(mapping);
    }
}

// A function to connect gamepad(s)
static void connect_gamepad(int device_index, bool open, bool raise_error)
{
    if (device_index >= 0) {
        Gamepad *gamepad = NULL;
        for (gamepad = gamepads; gamepad != NULL; gamepad = gamepad->next) {
            if (gamepad->id == device_index)
                break;
        }
        if (gamepad == NULL) {
            init_gamepad(&gamepad, device_index);
            if (gamepads == NULL)
                gamepads = gamepad;

            // Add to end of the linked list
            else {
                Gamepad *i;
                for (i = gamepads; i->next != NULL; i = i->next);
                i->next = gamepad;
                gamepad->previous = i;
            }
        }
        if (open)
            open_controller(gamepad, raise_error);
    }
    else if (open) {
        for (Gamepad *i = gamepads; i != NULL; i = i->next)
            open_controller(i, raise_error);
    }
}

// A function to disconnect gamepad(s)
static void disconnect_gamepad(int id, bool disconnect, bool remove)
{
    for (Gamepad *i = gamepads; i != NULL;) {
        if (id < 0 || i->id == id) {
            if (disconnect)
                SDL_GameControllerClose(i->controller);
            if (remove) {
                if (i->next != NULL)
                    i->next->previous = i->previous;
                if (i->previous != NULL)
                    i->previous->next = i->next;
                if (i == gamepads)
                    gamepads = i->next;
                Gamepad *tmp = i->next;
                free(i);
                i = tmp;
            }
            else {
                i->controller = NULL;
                i = i->next;
            }
        }
        else
            i = i->next;
    }
}

// A function to poll the connected gamepad for commands
static bool gamepad_any_mapped_input_pressed(void)
{
    for (GamepadControl *binding = gamepad_controls; binding != NULL;
         binding = binding->next) {
        for (Gamepad *gamepad = gamepads; gamepad != NULL;
             gamepad = gamepad->next) {
            if (gamepad->controller == NULL)
                continue;
            if (binding->type == TYPE_BUTTON) {
                if (SDL_GameControllerGetButton(gamepad->controller,
                                                binding->index))
                    return true;
            } else if (binding->type == TYPE_AXIS_POS ||
                       binding->type == TYPE_AXIS_NEG) {
                int axis = SDL_GameControllerGetAxis(gamepad->controller,
                                                     binding->index);
                int sign = binding->type == TYPE_AXIS_POS ? 1 : -1;
                if (sign * axis > GAMEPAD_DEADZONE)
                    return true;
            }
        }
    }
    return false;
}

static void poll_gamepad()
{
    /* The original Flex polls raw SDL controller state even in the background.
     * The candidate must not: two fullscreen SDL processes may see the same
     * physical button. Require both Wayland focus and SDL's live focus handle. */
    if (!media_wall_controller_input_allowed(
            state.has_focus, SDL_GetKeyboardFocus() == window))
        return;
    if (!tracked_guard_controller())
        return;
    if (!media_wall_controller_rearm_after_neutral(
            &state.controller_requires_neutral,
            gamepad_any_mapped_input_pressed()))
        return;

    /* Following an exact-child MPV exit, ignore all controller commands until
     * B has been physically released at least once.  Reconnects are common:
     * do not clear the latch when no controller is currently opened.
     */
    if (gamepad_return_requires_b_release) {
        bool observed_controller = false;
        bool b_is_held = false;
        for (Gamepad *g = gamepads; g != NULL; g = g->next) {
            if (g->controller != NULL) {
                observed_controller = true;
                if (SDL_GameControllerGetButton(g->controller, SDL_CONTROLLER_BUTTON_B))
                    b_is_held = true;
            }
        }
        for (GamepadControl *i = gamepad_controls; i != NULL; i = i->next)
            i->repeat = 0;
        if (!observed_controller || b_is_held)
            return;
        gamepad_return_requires_b_release = false;
    }


    int value_multiplier = 1; // Handles positive or negative axis safely for malformed mappings
    bool pressed;
    for (GamepadControl *i = gamepad_controls; i != NULL; i = i->next) {
        pressed = false;
        for (Gamepad *gamepad = gamepads; gamepad != NULL; gamepad = gamepad->next) {
            if (gamepad->controller == NULL)
                continue;

            // Check if axis value exceeds dead zone
            if (i->type == TYPE_AXIS_POS || i->type == TYPE_AXIS_NEG) {
                if (i->type == TYPE_AXIS_POS)
                    value_multiplier = 1;
                else if (i->type == TYPE_AXIS_NEG)
                    value_multiplier = -1;
                if (value_multiplier*SDL_GameControllerGetAxis(gamepad->controller, i->index) > GAMEPAD_DEADZONE) {
                    i->repeat++;
                    pressed = true;
                    break;
                }
            }

            // Check buttons
            else if (i->type == TYPE_BUTTON) {
                if (SDL_GameControllerGetButton(gamepad->controller, i->index)) {
                    i->repeat++;
                    pressed = true;
                    break;
                }
            }
        }
        if (!pressed) {
            i->repeat = 0;
            continue;
        }

        /* The default CORE repeat is 25 ms, too fast for a 9-poster row.
         * Only directional controls in the poster wall use 420/120 ms.
         * Outside the wall, retain the original CORE timings unchanged. */
        const bool wall_direction =
            is_media_wall(current_menu) &&
            media_wall_is_directional_control(i->label);
        const Uint32 nav_delay = wall_direction
            ? media_wall_repeat_delay_frames(refresh_period) : delay_period;
        const Uint32 nav_interval = wall_direction
            ? media_wall_repeat_interval_frames(refresh_period) : repeat_period;

        // Execute command immediately on the first press, then repeat slowly.
        if (i->repeat == 1) {
            log_debug("Gamepad %s detected", i->label);
            ticks.last_input = ticks.main;
            const char *wall_cmd = is_media_wall(current_menu)
                ? media_wall_gamepad_override(i->label) : NULL;
            tracked_handle_controller_action(wall_cmd != NULL ? wall_cmd : i->cmd,
                                             execute_command);
        }
        else if (i->repeat == nav_delay) {
            ticks.last_input = ticks.main;
            const char *wall_cmd = is_media_wall(current_menu)
                ? media_wall_gamepad_override(i->label) : NULL;
            tracked_handle_controller_action(wall_cmd != NULL ? wall_cmd : i->cmd,
                                             execute_command);
            i->repeat -= nav_interval;
        }
    }
}

// A function to update the slideshow
static void update_slideshow()
{
    // If image duration time has elapsed, load the next image and start the transition
    if (!state.slideshow_transition && (ticks.main - ticks.slideshow_load > config.slideshow_image_duration) &&
    !state.slideshow_paused) {
        
        // Render the new background image in a separate thread so we don't block the main thread
        if (!state.slideshow_background_rendering && !state.slideshow_background_ready) {
            Slideshowhread = SDL_CreateThread(load_next_slideshow_background_async, "Slideshow Thread", (void*) slideshow);
            state.slideshow_background_rendering = true;
        }

        // Convert background to texture after the rendering thread has completed
        else if (state.slideshow_background_ready) {
            SDL_WaitThread(Slideshowhread, NULL);
            Slideshowhread = NULL;
            if (config.slideshow_transition_time > 0) {
                slideshow->transition_texture = load_texture(slideshow->transition_surface);
                SDL_SetTextureAlphaMod(slideshow->transition_texture, 0);
                state.slideshow_transition = true;
            }
            else {
                SDL_DestroyTexture(background_texture);
                background_texture = load_texture(slideshow->transition_surface);
                ticks.slideshow_load = ticks.main;
            }
        slideshow->transition_surface = NULL;
        state.slideshow_background_ready = false;
        }
    }
    else if (state.slideshow_transition) {
        
        // Increase the transparency
        slideshow->transition_alpha += slideshow->transition_change_rate;
        
        // If transition is done, destroy old background and replace it with the new one
        if (slideshow->transition_alpha >= 255.0f) {
            SDL_SetTextureAlphaMod(slideshow->transition_texture, 0xFF);
            slideshow->transition_alpha = 0.0f;
            SDL_DestroyTexture(background_texture);
            background_texture = slideshow->transition_texture;
            slideshow->transition_texture = NULL;
            state.slideshow_transition = false;
            ticks.slideshow_load = ticks.main;
        }
        else
            SDL_SetTextureAlphaMod(slideshow->transition_texture, (Uint8) slideshow->transition_alpha);
    }
}

// A function to update the screensaver
static void update_screensaver()
{
    // Activate the screensaver if the launcher has been idle for the required time
    if (!state.screensaver_active && ticks.main - ticks.last_input > config.screensaver_idle_time) {
        state.screensaver_active = true;
        state.screensaver_transition = true;
        if (config.background_mode == BACKGROUND_SLIDESHOW && config.screensaver_pause_slideshow)
            state.slideshow_paused = true;
    }
    else {

        // Transition the screen to dark
        if (state.screensaver_transition) {
            screensaver->alpha += screensaver->transition_change_rate;
            if (screensaver->alpha >= screensaver->alpha_end_value) {
                SDL_SetTextureAlphaMod(screensaver->texture, (Uint8) screensaver->alpha_end_value);
                state.screensaver_transition = false;
            }
            else
                SDL_SetTextureAlphaMod(screensaver->texture, (Uint8) screensaver->alpha);
        }

        // User has pressed input, deactivate the screensaver
        if (state.screensaver_active && ticks.last_input == ticks.main) {
            SDL_SetTextureAlphaMod(screensaver->texture, 0);
            screensaver->alpha = 0.0f;
            state.screensaver_active = false;
            state.screensaver_transition = false;
            if (config.background_mode == BACKGROUND_SLIDESHOW) {
                state.slideshow_paused = false;
                
                // Reset the slideshow time so we don't have a transition immediately 
                // after coming out of screensaver mode
                ticks.slideshow_load = ticks.main;
            }
        }
    }
}

// A function to update the clock display
static void update_clock(bool block)
{
    if (ticks.main - ticks.clock_update > CLOCK_UPDATE_PERIOD) {
        if (!state.clock_rendering) {

            // Check to see if the time has changed
            get_time(clk);
            if (clk->render_time) {
                state.clock_rendering = true;
                if (block)
                    render_clock(clk);
                else
                    clock_thread = SDL_CreateThread(render_clock_async, "Clock Thread", (void*) clk); 
            }
            else
                ticks.clock_update = ticks.main;
        }

        // Render texture
        if (state.clock_ready) {
            SDL_WaitThread(clock_thread, NULL);
            clock_thread = NULL;
            SDL_DestroyTexture(clk->time_texture);
            clk->time_texture = load_texture(clk->time_surface);
            clk->time_surface = NULL;
            if (clk->render_date) {
                SDL_DestroyTexture(clk->date_texture);
                clk->date_texture = load_texture(clk->date_surface);
                clk->date_surface = NULL;
            }
            ticks.clock_update = ticks.main;
            clk->render_time = false;
            clk->render_date = false;
            state.clock_rendering = false;
            state.clock_ready = false;
        }
    }
}

static void pre_launch()
{
    SDL_SetWindowAlwaysOnTop(window, SDL_FALSE);
    if (gamepads != NULL)
        disconnect_gamepad(-1, true, false);

// Initialize exit hotkey for Windows
#ifdef _WIN32
    if (has_exit_hotkey())
        SDL_EventState(SDL_SYSWMEVENT, SDL_ENABLE);
#endif
}

static void post_launch()
{
    gamepad_return_requires_b_release = true;
    SDL_SetWindowAlwaysOnTop(window, SDL_TRUE);
    SDL_RaiseWindow(window);
    // Rebaseline the timing after the program is done
    ticks.main = SDL_GetTicks();
    ticks.last_input = ticks.main;

    // Post-application updates
    if (config.gamepad_enabled)
        connect_gamepad(-1, true, false);
    if (config.clock_enabled)
        update_clock(true);
    if (config.background_mode == BACKGROUND_SLIDESHOW)
        resume_slideshow();
    if (config.on_launch == ON_LAUNCH_BLANK)
        set_draw_color();

#ifdef _WIN32
    SDL_EventState(SDL_SYSWMEVENT, SDL_DISABLE);
    if (config.background_mode == BACKGROUND_TRANSPARENT)
        hide_cursor(current_entry);
#endif
}

// A function to quit the launcher
void quit(int status)
{
    log_debug("Quitting program");
    if (status != EXIT_SUCCESS)
        SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, 
            PROJECT_NAME, 
            "A critical error occurred. Check the log file for details.", 
            NULL
        );
    if (config.quit_cmd != NULL) {
        execute_command(config.quit_cmd);
        free(config.quit_cmd);
        config.quit_cmd = NULL;
    }
    cleanup();
    exit(status);
}

// A function to print the version and other info to command line
void print_version(FILE *stream)
{
    SDL_version sdl_version;
    SDL_GetVersion(&sdl_version);
    const SDL_version *img_version = IMG_Linked_Version();
    const SDL_version *ttf_version = TTF_Linked_Version();
    fprintf(stream, PROJECT_NAME " version " PROJECT_VERSION ", using:" endline);
    fprintf(stream, "  SDL       %u.%u.%u" endline, sdl_version.major, sdl_version.minor, sdl_version.patch);
    fprintf(stream, "  SDL_image %u.%u.%u" endline, img_version->major, img_version->minor, img_version->patch);
    fprintf(stream, "  SDL_ttf   %u.%u.%u" endline, ttf_version->major, ttf_version->minor, ttf_version->patch);
}

int main(int argc, char *argv[]) 
{
    int error;
    char *config_file_path = NULL;
    config.exe_path = SDL_GetBasePath();

    // Handle command line arguments, find config file
    handle_arguments(argc, argv, &config_file_path);

    // Parse config file for settings and menu entries
    parse_config_file(config_file_path);
    free(config_file_path);

    // Get default menu
    if (config.default_menu == NULL)
        log_fatal("No default menu defined in config file");
    default_menu = get_menu(config.default_menu);
    if (default_menu == NULL)
        log_fatal("Default menu %s not found in config file", config.default_menu);

    // Initialize SDL, verify all settings are in their allowable range
    init_sdl();
    init_sdl_image();
    init_sdl_ttf();
    validate_settings(&geo);
    
    // Initialize slideshow
    if (config.background_mode == BACKGROUND_SLIDESHOW)
        init_slideshow();

    // Initialize Nanosvg, create window and renderer
    init_svg();
    create_window();

    // Initialize timing
    ticks.main = SDL_GetTicks();
    ticks.last_input = ticks.main;
    ticks.program_start = ticks.main;

    // Load gamepad overrides
    if (config.gamepad_enabled && config.gamepad_mappings_file != NULL) {
        error = SDL_GameControllerAddMappingsFromFile(config.gamepad_mappings_file);
        if (error < 0) {
            log_error("Could not load gamepad mappings from %s\n%s", 
                config.gamepad_mappings_file,
                SDL_GetError()
            );
        }
    }

    // Render background
    if (config.background_mode == BACKGROUND_IMAGE) {
        if (config.background_image == NULL)
            log_error("Background 'Image' setting not specified in config file");
        else
            background_texture = load_texture_from_file(config.background_image);

        // Switch to color mode if loading background image failed
        if (background_texture == NULL) {
            config.background_mode = BACKGROUND_COLOR;
            log_error("Couldn't load background image, defaulting to color background");
            set_draw_color();
        }
    }

    // Render first slideshow image
    else if (config.background_mode == BACKGROUND_SLIDESHOW) {
        SDL_Surface *surface = load_next_slideshow_background(slideshow, false);
        background_texture = load_texture(surface);
    }

    // Initialize screensaver
    if (config.screensaver_enabled)
        init_screensaver();

    // Initialize clock
    if (config.clock_enabled) {
        clk = malloc(sizeof(Clock));
        init_clock(clk);
        ticks.clock_update = ticks.main;
    }
    
    // Render highlight
    if (config.highlight) {
        int button_height = config.icon_size + config.title_padding + geo.font_height;
        highlight = malloc(sizeof(Highlight));
        highlight->texture = render_highlight(config.icon_size + 2*config.highlight_hpadding,
                                button_height + 2*config.highlight_vpadding,
                                &highlight->rect
                            );
    }

    // Render scroll indicators
    if (config.scroll_indicators) {
        scroll = malloc(sizeof(Scroll));
        scroll->texture = NULL;
        int scroll_indicator_height = (int) ((float) geo.screen_height * SCROLL_INDICATOR_HEIGHT);
        render_scroll_indicators(scroll, scroll_indicator_height, &geo);
    }

    // Render background overlay
    if (config.background_overlay) {
        SDL_Surface *overlay_surface = NULL;
        overlay_surface = SDL_CreateRGBSurfaceWithFormat(0, 
                              geo.screen_width, 
                              geo.screen_height, 
                              32,
                              SDL_PIXELFORMAT_ARGB8888
                          );
        Uint32 overlay_color = SDL_MapRGBA(overlay_surface->format, 
                                   config.background_overlay_color.r, 
                                   config.background_overlay_color.g, 
                                   config.background_overlay_color.b, 
                                   config.background_overlay_color.a
                               );
        SDL_FillRect(overlay_surface, NULL, overlay_color);
        background_overlay = load_texture(overlay_surface);
    }

    // Register exit hotkey with Windows
#ifdef _WIN32
    if (has_exit_hotkey())
        register_exit_hotkey();
#endif

    // Print debug info to log
    if (config.debug) {
        debug_video(renderer, &display_mode);
        debug_settings();
        debug_gamepad(gamepad_controls);
        debug_hotkeys(hotkeys);    
        debug_menu_entries(config.first_menu, config.num_menus);
    }

    // Load the default menu and display it
    error = load_menu(default_menu, false, true);
    if (error)
        log_fatal("Could not load default menu %s", config.default_menu);

    // Execute startup command
    if (config.startup_cmd != NULL)
        execute_command(config.startup_cmd);
    
    // Main program loop
    log_debug("Begin program loop");
    while (1) {
        ticks.main = SDL_GetTicks();
#ifdef OPENHTPC_LAB_QA_CAPTURE
        if (getenv("OPENHTPC_LAB_QA_SCENARIO") != NULL) {
            lab_qa_loop++;
            SDL_Keycode injected = 0;
            bool qa_actions = strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"),
                                     "uxf1-actions") == 0;
            bool tab_test = strcmp(getenv("OPENHTPC_LAB_QA_SCENARIO"),
                                   "tabs") == 0 || qa_actions;
            if (tab_test) {
                /* Up: FILMS; Right: DISQUE (skips disabled SERIES).
                 * A/B: DISQUE and back; Right/A/B: DOSSIERS and back;
                 * Down: poster focus and A/B: film detail/return. */
                if (lab_qa_loop == 30) injected = SDLK_UP;
                if (lab_qa_loop == 45 || lab_qa_loop == 95 ||
                    lab_qa_loop == 165 ||
                    (qa_actions && (lab_qa_loop == 189 ||
                                    lab_qa_loop == 232 ||
                                    lab_qa_loop == 233)))
                    injected = SDLK_RIGHT;
                if (lab_qa_loop == 60 || lab_qa_loop == 110 ||
                    lab_qa_loop == 185 ||
                    (qa_actions && (lab_qa_loop == 200 ||
                                    lab_qa_loop == 219 ||
                                    lab_qa_loop == 235)))
                    injected = SDLK_RETURN;
                if (lab_qa_loop == 80 || lab_qa_loop == 130 ||
                    (!qa_actions && lab_qa_loop == 205) ||
                    (qa_actions && (lab_qa_loop == 210 ||
                                    lab_qa_loop == 229)))
                    injected = SDLK_BACKSPACE;
                if (lab_qa_loop == 145) injected = SDLK_DOWN;
                if (qa_actions && lab_qa_loop == 215)
                    injected = SDLK_LEFT;
            } else {
                if (lab_qa_loop == 35) injected = SDLK_RIGHT;
                if (lab_qa_loop == 75) injected = SDLK_DOWN;
                if (lab_qa_loop == 112 || lab_qa_loop == 205)
                    injected = SDLK_RETURN;
                if (lab_qa_loop == 125 || lab_qa_loop == 220)
                    injected = SDLK_BACKSPACE;
                if (lab_qa_loop >= 140 && lab_qa_loop <= 185 &&
                    (lab_qa_loop - 140) % 5 == 0)
                    injected = SDLK_RIGHT;
            }
            if (lab_qa_loop == (qa_actions ? 260U :
                                 (tab_test ? 235U : 245U))) {
                SDL_Event done = {0};
                done.type = SDL_QUIT;
                SDL_PushEvent(&done);
            }
            if (injected != 0) {
                SDL_Event synthetic = {0};
                synthetic.type = SDL_KEYDOWN;
                synthetic.key.keysym.sym = injected;
                SDL_PushEvent(&synthetic);
                fprintf(stderr, "LAB_QA_INPUT step=%u key=%s\n", lab_qa_loop,
                    SDL_GetKeyName(injected));
            }
        }
#endif
        while (SDL_PollEvent(&event)) {
            switch(event.type) {
                case SDL_QUIT:
                    quit(EXIT_SUCCESS);
                    break;

                case SDL_KEYDOWN:
                    if (!tracked_is_interaction_allowed())
                        break;
                    ticks.last_input = ticks.main;
                    handle_keypress(&event.key.keysym);
                    break;
                
                case SDL_MOUSEBUTTONDOWN:
                    if (!tracked_is_interaction_allowed())
                        break;
                    if (config.mouse_select && event.button.button == SDL_BUTTON_LEFT) {
                        ticks.last_input = ticks.main;
                        execute_command(current_entry->cmd);
                    }
                    break;

                case SDL_JOYDEVICEADDED:
                    if (SDL_IsGameController(event.jdevice.which) == SDL_TRUE) {
                        log_debug("Gamepad connected with device index %i", event.jdevice.which);
                        if (config.gamepad_device < 0 || config.gamepad_device == event.jdevice.which)
                            connect_gamepad(event.jdevice.which, !state.application_running, true);
                    }
                    break;

                case SDL_JOYDEVICEREMOVED:
                    if (SDL_IsGameController(event.jdevice.which) == SDL_TRUE || 1) {
                        log_debug("Gamepad disconnected");
                        if (config.gamepad_device < 0 || config.gamepad_device == event.jdevice.which)
                            disconnect_gamepad(event.jdevice.which, true, true);
                    }
                    break;

                case SDL_WINDOWEVENT:
                    if (event.window.event == SDL_WINDOWEVENT_FOCUS_LOST) {
                        log_debug("Lost keyboard focus");
                        state.has_focus = false;
                        state.controller_requires_neutral = true;
                        /* Release held/repeat state before a possible handoff
                         * to the other fullscreen Flex on the same machine. */
                        for (GamepadControl *binding = gamepad_controls;
                             binding != NULL; binding = binding->next)
                            binding->repeat = 0;
                        if (state.application_launching && tracked_can_restore_on_focus()) {
                            log_debug("Application detected");
                            state.application_launching = false;
                            state.application_running = true;
                            pre_launch();
                        }
#ifdef _WIN32
                        // Sometimes the launcher will lose focus on Windows when autostarting
                        // So if we lose the window focus within 10 seconds of the launcher starting
                        // we will grab back th Window focus. This is a bit of a hack
                        else if (ticks.main - ticks.program_start < 10000)
                            set_foreground_window();
#endif
                    }
                    else if (event.window.event == SDL_WINDOWEVENT_FOCUS_GAINED) {
                        log_debug("Gained keyboard focus");
                        state.has_focus = true;
                        state.controller_requires_neutral = true;
                    }
                    else if (event.window.event == SDL_WINDOWEVENT_LEAVE)
                        log_debug("Lost mouse focus");
                    break;
#ifdef _WIN32
                case SDL_SYSWMEVENT:
                    check_exit_hotkey(event.syswm.msg);
                    break;
#endif
            }
        }

#ifdef OPENHTPC_CORE_IDENT_QA
        /* Isolated QA: exercise only :submenu and :back, never apply/launch. */
        static bool ident_qa_done = false;
        const char *ident_result = getenv("OPENHTPC_CORE_IDENT_QA_RESULT");
        const char *ident_page = getenv("OPENHTPC_CORE_IDENT_QA_PAGE");
        if (!ident_qa_done && ident_result != NULL && ident_result[0] == '/' &&
            SDL_GetTicks() - ticks.program_start > 500) {
            ident_qa_done = true;
            bool detail_ok = false, entry_ok = false, sheet_ok = false;
            bool focus_ok = false, parent_ok = false;
            const char *parent_name = current_menu ? current_menu->name : "";
            char parent_copy[128] = {0}, expected[64] = {0};
            snprintf(parent_copy, sizeof(parent_copy), "%s", parent_name);
            if (ident_page != NULL && strlen(ident_page) == 15 &&
                strncmp(ident_page, "MEDIA_D", 7) == 0) {
                snprintf(expected, sizeof(expected), "MEDIA_R%s", ident_page + 7);
                detail_ok = load_menu_by_name(ident_page, true, true) == 0 &&
                    current_menu != NULL &&
                    strcmp(current_menu->name, ident_page) == 0;
                if (detail_ok) {
                    execute_command(":right");
                    entry_ok = current_entry != NULL &&
                        current_entry->cmd != NULL &&
                        strcmp(current_entry->cmd, ":submenu MEDIA_R") != 0 &&
                        strstr(current_entry->cmd, ":submenu MEDIA_R") ==
                            current_entry->cmd &&
                        strcmp(current_entry->cmd + strlen(":submenu "), expected) == 0;
                    if (entry_ok) {
                        execute_command(":select");
                        sheet_ok = current_menu != NULL &&
                            strcmp(current_menu->name, expected) == 0;
                        if (sheet_ok) {
                            execute_command(":back");
                            focus_ok = current_menu != NULL &&
                                strcmp(current_menu->name, ident_page) == 0 &&
                                current_entry != NULL && current_entry->cmd != NULL &&
                                strcmp(current_entry->cmd + strlen(":submenu "), expected) == 0;
                            execute_command(":back");
                            parent_ok = current_menu != NULL &&
                                strcmp(current_menu->name, parent_copy) == 0;
                        }
                    }
                }
            }
            FILE *out = fopen(ident_result, "w");
            if (out != NULL) {
                fprintf(out, "QA_IDENT_DETAIL=%d\nQA_IDENT_ENTRY=%d\n"
                             "QA_IDENT_SHEET=%d\nQA_IDENT_FOCUS=%d\n"
                             "QA_IDENT_BACK_TO_PARENT=%d\n",
                        detail_ok, entry_ok, sheet_ok, focus_ok, parent_ok);
                fclose(out);
            }
            quit(detail_ok && entry_ok && sheet_ok && focus_ok && parent_ok ?
                 EXIT_SUCCESS : EXIT_FAILURE);
        }
#endif

#ifdef OPENHTPC_MODAL_QA
        /* Executable SDL QA path, product builds never contain it. */
        static int qa_phase = 0;
        static Uint32 qa_started_at = 0;
        const char *qa_result = getenv("OPENHTPC_MODAL_QA_RESULT");
        if (qa_result != NULL && qa_result[0] == '/') {
            if (qa_started_at == 0) qa_started_at = SDL_GetTicks();
            if (SDL_GetTicks() - qa_started_at > 450 && qa_phase == 0) {
                const char *page = getenv("OPENHTPC_MODAL_QA_PAGE");
                const char *token = getenv("OPENHTPC_MODAL_QA_TOKEN");
                if (page == NULL || token == NULL || 
                    load_menu_by_name(page,true,true) != 0) {
                    FILE *f = fopen(qa_result,"w");
                    if (f != NULL) {fputs("QA_PAGE_FAILED\n",f);fclose(f);}
                    quit(EXIT_FAILURE);
                }
                if (current_entry == NULL || current_entry->cmd == NULL ||
                    strstr(current_entry->cmd, ":mediaresumepopup ") == NULL) {
                    FILE *f = fopen(qa_result,"w");
                    if (f != NULL) {fputs("QA_DETAIL_COMMAND_MISSING\n",f);fclose(f);}
                    quit(EXIT_FAILURE);
                }
                /* Real entry selection, including command parsing,
                 * tracked command gate and optional probe. */
                execute_command(current_entry->cmd);
                if (getenv("OPENHTPC_MODAL_QA_FIRSTPLAY") != NULL) {
                    FILE *f = fopen(qa_result,"w");
                    if (f != NULL) {
                        fprintf(f, "QA_FIRSTPLAY_NO_MODAL=%d\n", !resume_modal_active);
                        fclose(f);
                    }
                    qa_phase = 3;
                } else {
                    if (!resume_modal_active) {
                        FILE *f = fopen(qa_result,"w");
                        if (f != NULL) {fputs("QA_MODAL_NOT_OPEN\n",f);fclose(f);}
                        quit(EXIT_FAILURE);
                    }
                    if (getenv("OPENHTPC_MODAL_QA_HOLD_PREVIEW") != NULL) {
                        /* QA-only physical demonstration: leave the native
                         * popup visible for the bounded external runner.
                         * No synthetic button presses or player launches. */
                        FILE *hold = fopen(qa_result, "w");
                        if (hold != NULL) {
                            fprintf(hold, "QA_NATIVE_MODAL_VISIBLE=%d\\n",
                                    resume_modal_active);
                            fclose(hold);
                        }
                        qa_phase = 4;
                    } else {
                        qa_phase = 1;
                    }
                }
            } else if (qa_phase == 1) {
                execute_command(":down");
                bool moved = resume_modal_selected == 1;
                execute_command(":up");
                moved = moved && resume_modal_selected == 0;
                SDL_Keysym keyboard = {0};
                keyboard.sym = SDLK_DOWN;
                handle_keypress(&keyboard);
                moved = moved && resume_modal_selected == 1;
                keyboard.sym = SDLK_UP;
                handle_keypress(&keyboard);
                moved = moved && resume_modal_selected == 0;
                keyboard.sym = SDLK_ESCAPE;
                handle_keypress(&keyboard);
                bool cancelled = !resume_modal_active;
                run_resume_modal_action(getenv("OPENHTPC_MODAL_QA_TOKEN"));
                bool reopened = resume_modal_active;
                FILE *f = fopen(qa_result,"w");
                if (f != NULL) {
                    fprintf(f,"QA_MODAL=%d\nQA_DPAD=%d\nQA_B_CANCEL=%d\nQA_REOPEN=%d\n",
                            reopened,moved,cancelled,reopened);
                    fclose(f);
                }
                qa_phase = 2;
            } else if (qa_phase == 2 && getenv("OPENHTPC_MODAL_QA_SELECT") != NULL) {
                bool active_before = resume_modal_active;
                const char *choice_env = getenv("OPENHTPC_MODAL_QA_CHOICE_INDEX");
                if (choice_env != NULL && strcmp(choice_env, "1") == 0)
                    execute_command(":down");
                else if (choice_env != NULL && strcmp(choice_env, "2") == 0) {
                    execute_command(":down");
                    execute_command(":down");
                }
                execute_command(":select");
                bool modal_dismissed = !resume_modal_active;
                FILE *f = fopen(qa_result,"a");
                if (f != NULL) {
                    fprintf(f,"QA_A_SELECT=%d\n",active_before && modal_dismissed);
                    fclose(f);
                }
                qa_phase = 3;
            } else if (qa_phase == 2 &&
                       SDL_GetTicks() - qa_started_at > 1100) {
                close_resume_modal();
                quit(EXIT_SUCCESS);
            } else if (qa_phase == 3 &&
                       SDL_GetTicks() - qa_started_at > 1600) {
                quit(EXIT_SUCCESS);
            }
        }
#endif

#ifdef OPENHTPC_LAB_QA_CAPTURE
        const char *qa_scenario = getenv("OPENHTPC_LAB_QA_SCENARIO");
        bool tabs_qa = qa_scenario != NULL &&
            strcmp(qa_scenario, "tabs") == 0;
        bool actions_qa = qa_scenario != NULL &&
            strcmp(qa_scenario, "uxf1-actions") == 0;
        bool qa_checkpoint = actions_qa
            ? (lab_qa_loop == 186 || lab_qa_loop == 190 ||
               lab_qa_loop == 196 || lab_qa_loop == 202 ||
               lab_qa_loop == 206 || lab_qa_loop == 211 ||
               lab_qa_loop == 216 || lab_qa_loop == 221 ||
               lab_qa_loop == 225 || lab_qa_loop == 230 ||
               lab_qa_loop == 234 || lab_qa_loop == 236 ||
               lab_qa_loop == 246)
            : tabs_qa
            ? (lab_qa_loop == 29 || lab_qa_loop == 31 ||
               lab_qa_loop == 46 || lab_qa_loop == 61 ||
               lab_qa_loop == 81 || lab_qa_loop == 96 ||
               lab_qa_loop == 111 || lab_qa_loop == 131 ||
               lab_qa_loop == 146 || lab_qa_loop == 166 ||
               lab_qa_loop == 186 || lab_qa_loop == 196 ||
               lab_qa_loop == 206)
            : (lab_qa_loop == 111 || lab_qa_loop == 113 ||
               lab_qa_loop == 126 || lab_qa_loop == 198 ||
               lab_qa_loop == 206 || lab_qa_loop == 221 ||
               lab_qa_loop == 235);
        if (qa_scenario != NULL && qa_checkpoint) {
            fprintf(stderr, "LAB_QA_STATE step=%u menu=%s entry=%s row=%d selected=%zu scroll=%zu tabfocus=%d tab=%d\n",
                lab_qa_loop, current_menu ? current_menu->name : "NULL",
                current_entry ? current_entry->title : "NULL",
                current_menu && is_media_wall(current_menu)
                    ? (int)current_menu->media_wall.row : -1,
                current_menu && is_media_wall(current_menu)
                    ? current_menu->media_wall.selected[current_menu->media_wall.row] : 0,
                current_menu && is_media_wall(current_menu)
                    ? current_menu->media_wall.scroll[current_menu->media_wall.row] : 0,
                current_menu && is_media_wall(current_menu)
                    ? (int)current_menu->media_wall.tab_focused : -1,
                current_menu && is_media_wall(current_menu)
                    ? (int)current_menu->media_wall.tab : -1);
        }
#endif
        // Update application state
        if (tracked_is_active()) {
            TrackedLifecycleStatus status = tracked_update(post_launch);
            if (status == TRACKED_STATUS_FINISHED) {
                state.application_running = false;
            }
        }
        else if (state.application_running && state.has_focus) {
            state.application_running = false;
            post_launch();
            log_debug("Application finished");
        }

        // Post-event loop updates
        refresh_live_optical_state();
        refresh_live_activity_state();
        if (!(state.application_running || state.application_launching) && is_home_menu())
            refresh_home_network_indicator();
        if (!(state.application_running || state.application_launching)) {
            refresh_disc_sheet_background();
            refresh_current_menu_background_and_entries();
            if (gamepads != NULL)
                poll_gamepad();
            if (config.background_mode == BACKGROUND_SLIDESHOW)
                update_slideshow();
            if (config.screensaver_enabled)
                update_screensaver();
            if (config.clock_enabled)
                update_clock(false);
        }
        if (state.application_launching && tracked_can_restore_on_timeout() &&
        ticks.main - ticks.application_launched > config.application_timeout) {
            state.application_launching = false;
            if (config.on_launch == ON_LAUNCH_BLANK)
                set_draw_color();
        }
        if (state.application_running)
            SDL_Delay(APPLICATION_WAIT_PERIOD);
        else
            draw_screen();
    }
    quit(EXIT_SUCCESS);
}
