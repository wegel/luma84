// SPDX-License-Identifier: GPL-2.0-or-later
#include QMK_KEYBOARD_H
#include "personal_rgb.h"
#include "eeprom.h"
#include <lib/lib8tion/lib8tion.h>

// Reuse the vendor's 16 per-effect color bytes. Keep VIA/keymap offsets intact.
#define PERSONAL_RGB_ADDR ((void *)((uintptr_t)CONFINFO_EECONFIG_ADDR + 4))
#define PERSONAL_RGB_MAGIC 0x31424752UL // "RGB1"
#define PERSONAL_RGB_SAVE_MS 500
#define PERSONAL_RGB_REPEAT_DELAY_MS 350
#define PERSONAL_RGB_REPEAT_MS 60

typedef struct PACKED {
    uint32_t magic;
    RGB color;
    uint8_t ripple;
} personal_rgb_config_t;

_Static_assert(sizeof(personal_rgb_config_t) <= 16, "Personal colors exceed reserved vendor bytes");

static personal_rgb_config_t personal_rgb;
static bool dirty;
static uint32_t changed_at;
static uint8_t held_channels;
static uint32_t repeat_at[6];
static uint8_t next_preset;

static const RGB presets[] = {
    {255, 0, 0},     // 1: red
    {255, 85, 0},    // 2: orange
    {255, 255, 0},   // 3: yellow
    {0, 255, 0},     // 4: green
    {0, 255, 255},   // 5: cyan
    {0, 0, 255},     // 6: blue
    {128, 0, 255},   // 7: violet
    {255, 0, 128},   // 8: pink
    {255, 180, 100}, // 9: warm white
    {255, 255, 255}, // 0: white
};

static void save(void) {
    eeprom_update_block(&personal_rgb, PERSONAL_RGB_ADDR, sizeof(personal_rgb));
    dirty = false;
}

static void changed(void) {
    dirty = true;
    changed_at = timer_read32();
}

static void apply_mode(void) {
    uint8_t mode = personal_rgb.ripple ? RGB_MATRIX_CUSTOM_PERSONAL_RIPPLE : RGB_MATRIX_CUSTOM_PERSONAL_SOLID;
    if (rgb_matrix_get_mode() != mode) {
        // QMK's mode setter ignores requests while disabled. Stage the new mode
        // without enabling LEDs so the next toggle/wake starts in our effect.
        if (rgb_matrix_is_enabled()) rgb_matrix_mode_noeeprom(mode);
        else rgb_matrix_config.mode = mode;
    }
}

void personal_rgb_reset(void) {
    personal_rgb = (personal_rgb_config_t){PERSONAL_RGB_MAGIC, {255, 180, 100}, false};
    held_channels = 0;
    next_preset = 9;
    save();
}

void personal_rgb_init(void) {
    eeprom_read_block(&personal_rgb, PERSONAL_RGB_ADDR, sizeof(personal_rgb));
    if (personal_rgb.magic != PERSONAL_RGB_MAGIC || personal_rgb.ripple > 1) personal_rgb_reset();
    held_channels = 0;
    dirty = false;
    next_preset = 0;
    for (uint8_t i = 0; i < ARRAY_SIZE(presets); i++) {
        if (memcmp(&personal_rgb.color, &presets[i], sizeof(RGB)) == 0) next_preset = (i + 1) % ARRAY_SIZE(presets);
    }
    apply_mode();
}

static void adjust_channel(uint8_t key) {
    uint8_t *channel = key < 2 ? &personal_rgb.color.r : key < 4 ? &personal_rgb.color.g : &personal_rgb.color.b;
    uint8_t step = (get_mods() & MOD_BIT(KC_LSFT)) ? 1 : 17;
    uint8_t value = (key & 1) ? qsub8(*channel, step) : qadd8(*channel, step);
    if (*channel != value) {
        *channel = value;
        changed();
    }
}

static void select_preset(uint8_t index) {
    personal_rgb.color = presets[index];
    next_preset = (index + 1) % ARRAY_SIZE(presets);
    changed();
}

bool personal_rgb_process_record(uint16_t keycode, keyrecord_t *record) {
    if (keycode >= PC_RED_UP && keycode <= PC_BLUE_DOWN) {
        uint8_t key = keycode - PC_RED_UP;
        if (record->event.pressed) {
            held_channels |= 1 << key;
            repeat_at[key] = timer_read32() + PERSONAL_RGB_REPEAT_DELAY_MS;
            adjust_channel(key);
        } else {
            held_channels &= ~(1 << key);
        }
        return false;
    }
    if (keycode >= PC_PRESET_1 && keycode <= PC_PRESET_0) {
        if (record->event.pressed) select_preset(keycode - PC_PRESET_1);
        return false;
    }
    switch (keycode) {
        case RGB_MOD:
        case RGB_RMOD:
        case RL_MOD:
            if (record->event.pressed) {
                personal_rgb.ripple ^= 1;
                apply_mode();
                changed();
            }
            return false;
        case RGB_HUI:
            if (record->event.pressed) select_preset(next_preset);
            return false;
        default:
            return true;
    }
}

void personal_rgb_task(void) {
    // Accept either personal effect from VIA; reject the vendor's other modes.
    uint8_t mode = rgb_matrix_get_mode();
    if (mode == RGB_MATRIX_CUSTOM_PERSONAL_SOLID || mode == RGB_MATRIX_CUSTOM_PERSONAL_RIPPLE) {
        uint8_t ripple = mode == RGB_MATRIX_CUSTOM_PERSONAL_RIPPLE;
        if (personal_rgb.ripple != ripple) {
            personal_rgb.ripple = ripple;
            changed();
        }
    } else {
        apply_mode();
    }

    uint32_t now = timer_read32();
    for (uint8_t key = 0; key < 6; key++) {
        if ((held_channels & (1 << key)) && (int32_t)(now - repeat_at[key]) >= 0) {
            adjust_channel(key);
            repeat_at[key] = now + PERSONAL_RGB_REPEAT_MS;
        }
    }
    if (dirty && timer_elapsed32(changed_at) >= PERSONAL_RGB_SAVE_MS) save();
}

static uint8_t blend(uint8_t base, uint8_t target, uint8_t amount, uint8_t brightness) {
    uint16_t color = ((uint16_t)base * (255 - amount) + (uint16_t)target * amount) / 255;
    return color * brightness / 255;
}

void personal_rgb_render(uint8_t led_min, uint8_t led_max, bool ripple) {
    RGB base = personal_rgb.color;
    // Dark rings remain visible on white/light colors; other colors get white rings.
    uint16_t luma = ((uint16_t)base.r * 77 + (uint16_t)base.g * 150 + (uint16_t)base.b * 29) >> 8;
    uint8_t target = luma >= 128 ? 0 : 255;
    uint8_t brightness = rgb_matrix_get_val();

    for (uint8_t i = led_min; i < led_max; i++) {
        uint8_t amount = 0;
        // LEDs 0..3 are body lights. They keep the steady background color.
        if (ripple && i >= RGBLED_NUM) {
            for (uint8_t hit = 0; hit < g_last_hit_tracker.count; hit++) {
                uint32_t radius = (uint32_t)g_last_hit_tracker.tick[hit] * (rgb_matrix_get_speed() + 64) / 1024;
                if (radius >= 280) continue;
                int16_t dx = (int16_t)g_led_config.point[i].x - g_last_hit_tracker.x[hit];
                int16_t dy = (int16_t)g_led_config.point[i].y - g_last_hit_tracker.y[hit];
                uint16_t distance = sqrt16(dx * dx + dy * dy);
                uint16_t gap = distance > radius ? distance - radius : radius - distance;
                if (gap >= 24) continue;
                uint8_t strength = (uint32_t)(24 - gap) * 255 * (280 - radius) / (24 * 280);
                if (strength > amount) amount = strength;
            }
        }
        rgb_matrix_set_color(i, blend(base.r, target, amount, brightness),
                                blend(base.g, target, amount, brightness),
                                blend(base.b, target, amount, brightness));
    }
}
