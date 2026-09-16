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
#include <errno.h>
#include "image.h"
#include "util.h"
#include "debug.h"
#include "clock.h"
#include "platform/platform.h"

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
static void load_submenu(const char *submenu);
static void load_back_menu(Menu *menu);
static void draw_screen(void);
static void handle_keypress(SDL_Keysym *key);
static void execute_command(const char *command);
static void refresh_live_optical_state(void);
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

// Initialize default settings
Config config = {
    .default_menu                     = NULL,
    .background_image                 = NULL,
    .slideshow_directory              = NULL,
    .title_font_path                  = NULL,
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
Hotkey *hotkeys                       = NULL;
Clock *clk                            = NULL;
TTF_Font *clock_font                  = NULL;
SDL_Thread *Slideshowhread            = NULL;
SDL_Thread *clock_thread              = NULL;
SDL_Event event;
SDL_SysWMinfo wm_info;
SDL_DisplayMode display_mode;
TextInfo title_info;
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
    geo.screen_width = display_mode.w;
    geo.screen_height = display_mode.h;
    refresh_period = 1000 / (Uint32) display_mode.refresh_rate;
    geo.screen_margin = (int) (SCREEN_MARGIN * (float) geo.screen_height);
}

// A function to create the window and renderer
static void create_window()
{
    window = SDL_CreateWindow(PROJECT_NAME,
                 SDL_WINDOWPOS_UNDEFINED,
                 SDL_WINDOWPOS_UNDEFINED,
                 0,
                 0,
                 SDL_WINDOW_FULLSCREEN_DESKTOP | SDL_WINDOW_BORDERLESS | SDL_WINDOW_ALWAYS_ON_TOP
             );
    if (window == NULL)
        log_fatal("Could not create SDL Window\n%s", SDL_GetError());
    SDL_ShowCursor(SDL_DISABLE);

    // Create HW accelerated renderer, get screen resolution for geometry calculations
    Uint32 renderer_flags = SDL_RENDERER_ACCELERATED;
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
    free(config.exe_path);
    free(config.slideshow_directory);
    free(config.clock_font_path);
    free(config.gamepad_mappings_file);
    free(config.startup_cmd);
    free(config.quit_cmd);
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
            strcmp(name, "SYSTEM_METADATA") == 0 ||
            strcmp(name, "SYSTEM_TMDB") == 0 ||
            strcmp(name, "SYSTEM_PROCESSING") == 0 ||
            strcmp(name, "SYSTEM_PLAYBACK") == 0 ||
            strcmp(name, "PLAYBACK_VIDEO") == 0 ||
            strcmp(name, "PLAYBACK_AUDIO") == 0 ||
            strcmp(name, "PLAYBACK_SUBTITLES") == 0 ||
            strcmp(name, "DVD_VIDEO_MODE") == 0 ||
            strcmp(name, "SYSTEM_DIAGNOSTICS") == 0 ||
            strcmp(name, "SYSTEM_TECHNICAL") == 0);
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
        strcmp(current_menu->name, "Accueil") == 0
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

    if (config.debug)
        log_debug("Key %s (#%X) detected", SDL_GetKeyName(key->sym), key->sym);

    // Check default keys
    if ((is_media_sidebar() || is_media_list() || is_system_root() || is_disc_ambiguous()) && key->sym == SDLK_UP) {
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

    buttons = current_menu->num_entries - (current_menu->page)*config.max_buttons;
    if (buttons > config.max_buttons)
        buttons = config.max_buttons;
    
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
        int row_height = (geo.screen_height * 90) / 1000;
        int gap = (geo.screen_height * 10) / 1000;
        int icon_size = (geo.screen_height * 68) / 1000;
        int start_y = (geo.screen_height * 14) / 100;
        geo.x_margin = (geo.screen_width * 6) / 100;
        geo.x_advance = 0;
        for (int i = 0; i < buttons && entry != NULL; i++) {
            entry->icon_rect.x = geo.x_margin + (geo.screen_width * 15) / 1000;
            entry->icon_rect.y = start_y + i * (row_height + gap) + (row_height - icon_size) / 2;
            entry->icon_rect.w = icon_size;
            entry->icon_rect.h = icon_size;
            entry->text_rect.x = entry->icon_rect.x + icon_size + (geo.screen_width * 18) / 1000;
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
        int base_pt = (config.title_font_size > 0) ? (int)config.title_font_size : 28;

        // 1. Title
        if (menu->detail_title != NULL && menu->detail_title[0] != '\0') {
            int title_pt = (int)(base_pt * 1.35);
            TTF_Font *title_font = NULL;
            if (font_path != NULL) title_font = TTF_OpenFont(font_path, title_pt);
            if (title_font == NULL) title_font = title_info.font;

            menu->detail_title_texture = render_text_wrapped(
                menu->detail_title,
                title_font,
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

            menu->detail_original_title_texture = render_text_wrapped(
                menu->detail_original_title,
                orig_font,
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

        // 4. Synopsis
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
        render_buttons(menu);
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
        /* The logical DISQUE entry list is stable (e.g. LIRE LE DVD).  Updating its
                 * presentation must not rewrite page/selection ownership. */
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
        current_entry = current_entry->previous;

        // Load the previous page if there is a valid previous entry
        if (current_entry) {
            buttons = config.max_buttons;
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
            unsigned int num_pages = DIV_ROUND_UP(current_menu->num_entries, config.max_buttons);
            current_menu->root_entry = advance_entries(current_menu->root_entry,
                (int) ((num_pages - 1 - current_menu->page) * config.max_buttons),
                DIRECTION_RIGHT
            );
            current_menu->page = num_pages - 1;
            buttons = current_menu->num_entries - current_menu->page * config.max_buttons;
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
    // If we are not in the rightmost position, move highlight right
    if ((int) current_menu->highlight_position < (geo.num_buttons - 1)) {
        if (config.highlight)
            highlight->rect.x += geo.x_advance;
        current_menu->highlight_position++;
        current_entry = current_entry->next;
    }

    // If we are in the rightmost postion, but there are more entries in the menu, load next page
    else if (current_menu->highlight_position + current_menu->page*config.max_buttons <
    (current_menu->num_entries - 1)) {
        unsigned int buttons = current_menu->num_entries - (current_menu->page + 1)*config.max_buttons;
        if (buttons > config.max_buttons)
            buttons = config.max_buttons;
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
        calculate_button_geometry(current_menu->root_entry, (int) MIN(current_menu->num_entries, config.max_buttons));
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
    if (menu->back != NULL)
        load_menu(menu->back, false, config.reset_on_back);
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
        if (config.scroll_indicators &&
        (current_menu->page*config.max_buttons + (unsigned int) geo.num_buttons) <= (current_menu->num_entries - 1))
            SDL_RenderCopy(renderer, scroll->texture, NULL, &scroll->rect_right);

        if (config.scroll_indicators && current_menu->page > 0)
            SDL_RenderCopyEx(renderer, scroll->texture, NULL, &scroll->rect_left, 0, NULL, SDL_FLIP_HORIZONTAL);

        // Draw clock
        if (config.clock_enabled) {
            SDL_RenderCopy(renderer, clk->time_texture, NULL, &clk->time_rect);
            if (config.clock_show_date)
                SDL_RenderCopy(renderer, clk->date_texture, NULL, &clk->date_rect);
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

        // Plaques de contraste propres à l'accueil. Elles restent derrière
        // l'illustration et remplacent le highlight carré historique.
        if (is_home_menu()) {
            Entry *card_entry = current_menu->root_entry;
            for (int i = 0; i < geo.num_buttons; i++) {
                draw_home_card(
                    &card_entry->icon_rect,
                    i == (int) current_menu->highlight_position
                );
                card_entry = card_entry->next;
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
            int rail_width = (geo.screen_width * 42) / 100;
            int row_height = (geo.screen_height * 90) / 1000;
            int gap = (geo.screen_height * 10) / 1000;
            int start_y = (geo.screen_height * 14) / 100;
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

            if (icon != NULL)
                SDL_RenderCopy(renderer, icon, NULL, &artwork_rect);
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

        // Draw screensaver
        if (state.screensaver_active)
            SDL_RenderCopy(renderer, screensaver->texture, NULL, NULL);
    }
    else
        SDL_RenderFillRect(renderer, NULL);

    // Output to screen
    SDL_RenderPresent(renderer);
    if (!config.vsync) {
        Uint32 sleep_time = refresh_period - (SDL_GetTicks() - ticks.main);
        if (sleep_time > 0)
            SDL_Delay(sleep_time);
    }
}

// A function to execute the user's command
static void execute_command(const char *command)
{
    if (command == NULL)
        return;

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
            char *settings_command = strtok(NULL, "");
            Menu *parent = current_menu != NULL ? current_menu->back : NULL;
            if (settings_command != NULL && parent != NULL && run_process_sync(settings_command)) {
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
                load_menu(parent, false, true);
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
            if (is_media_list() && current_entry != NULL && current_entry->context_selected)
                current_entry->context_selected = false;
            else {
                if (current_entry != NULL) current_entry->context_selected = false;
                move_left();
            }
        }
        else if (!strcmp(special_command, SCMD_RIGHT)) {
            if (is_media_list() && current_entry != NULL && current_entry->context_cmd != NULL && !current_entry->context_selected)
                current_entry->context_selected = true;
            else {
                if (current_entry != NULL) current_entry->context_selected = false;
                move_right();
            }
        }
        else if (!strcmp(special_command, SCMD_SELECT)) {
            if (current_entry != NULL && current_entry->context_selected && current_entry->context_cmd != NULL)
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
static void poll_gamepad()
{
    if (!tracked_guard_controller())
        return;

    int value_multiplier = 1; // Handles positive or negative axis safely for malformed mappings
    bool pressed;
    for (GamepadControl *i = gamepad_controls; i != NULL; i = i->next) {
        pressed = false;
        for (Gamepad *gamepad = gamepads; gamepad != NULL; gamepad = gamepad->next) {

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

        // Execute command if first press or valid repeat
        if (i->repeat == 1) {
            log_debug("Gamepad %s detected", i->label);
            ticks.last_input = ticks.main;
            tracked_handle_controller_action(i->cmd, execute_command);
        }
        else if (i->repeat == delay_period) {
            ticks.last_input = ticks.main;
            tracked_handle_controller_action(i->cmd, execute_command);
            i->repeat -= repeat_period;
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
