// QMK 0.28 adapter for the vendor's body-light buffer.
// SPDX-License-Identifier: GPL-2.0-or-later
#include "rgblight.h"
#include "rgblight_drivers.h"

extern LED_TYPE led[RGBLED_NUM];

static void body_light_init(void) {}

static void body_light_set_color(int index, uint8_t red, uint8_t green, uint8_t blue) {
    if (index < 0 || index >= RGBLED_NUM) return;
    led[index].r = red;
    led[index].g = green;
    led[index].b = blue;
}

static void body_light_set_color_all(uint8_t red, uint8_t green, uint8_t blue) {
    for (int index = 0; index < RGBLED_NUM; index++) {
        body_light_set_color(index, red, green, blue);
    }
}

// The vendor's rgb_matrix_indicators_advanced_rgblight() copies this buffer
// into the main LED chain. Sending another WS2812 frame here would conflict.
static void body_light_flush(void) {}

const rgblight_driver_t rgblight_driver = {
    .init = body_light_init,
    .set_color = body_light_set_color,
    .set_color_all = body_light_set_color_all,
    .flush = body_light_flush,
};
