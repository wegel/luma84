// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "quantum.h"

void personal_rgb_init(void);
void personal_rgb_reset(void);
void personal_rgb_task(void);
bool personal_rgb_process_record(uint16_t keycode, keyrecord_t *record);
void personal_rgb_render(uint8_t led_min, uint8_t led_max, bool ripple);
