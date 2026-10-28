// Copyright 2024 sdk66 (@sdk66)
// SPDX-License-Identifier: GPL-2.0-or-later

#ifdef ENABLE_RGB_MATRIX_RGBR_PLAY
RGB_MATRIX_EFFECT(RGBR_PLAY)
#    ifdef RGB_MATRIX_CUSTOM_EFFECT_IMPLS

bool RGBR_PLAY(effect_params_t *params) {
    RGB_MATRIX_USE_LIMITS(led_min, led_max);

    extern void rgbrec_play(uint8_t led_min, uint8_t led_max);
    rgbrec_play(led_min, led_max);

    return rgb_matrix_check_finished_leds(led_max);
}

#    endif // RGB_MATRIX_CUSTOM_EFFECT_IMPLS
#endif

RGB_MATRIX_EFFECT(PERSONAL_SOLID)
RGB_MATRIX_EFFECT(PERSONAL_RIPPLE)
#ifdef RGB_MATRIX_CUSTOM_EFFECT_IMPLS
#    include "personal_rgb.h"

bool PERSONAL_SOLID(effect_params_t *params) {
    RGB_MATRIX_USE_LIMITS(led_min, led_max);
    personal_rgb_render(led_min, led_max, false);
    return rgb_matrix_check_finished_leds(led_max);
}

bool PERSONAL_RIPPLE(effect_params_t *params) {
    RGB_MATRIX_USE_LIMITS(led_min, led_max);
    personal_rgb_render(led_min, led_max, true);
    return rgb_matrix_check_finished_leds(led_max);
}
#endif
