#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the personal controls and LED output from the compiled ARM firmware."""
import argparse
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                               UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP)

from test_wake import ROOT, FLASH, RAM, RETURN, read_build

PRESETS = [(255, 0, 0), (255, 85, 0), (255, 255, 0), (0, 255, 0),
           (0, 255, 255), (0, 0, 255), (128, 0, 255), (255, 0, 128),
           (255, 180, 100), (255, 255, 255)]
checks = 0


def expect(condition, message):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)


class Firmware:
    def __init__(self, symbols, segments, eeprom=None):
        self.symbols = symbols
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.uc.mem_map(FLASH, 0x40000)
        self.uc.mem_map(RAM, 0x10000)
        for address, data in segments:
            self.uc.mem_write(address, data)
        self.now = 1000
        self.mods = 0
        self.eeprom = bytearray(eeprom if eeprom is not None else b'\xa5' * 4096)
        self.saved = []
        self.colors = {}
        self.stub = {symbols[name]: name for name in [
            'timer_read32', 'timer_elapsed32', 'get_mods', 'eeprom_read_block',
            'eeprom_update_block', 'rgb_matrix_set_color', 'host_keyboard_led_state',
            'rgb_matrix_blink_task', 'rgb_matrix_wls_indicator', 'is_keyboard_master',
        ] if name in symbols}
        self.uc.hook_add(UC_HOOK_CODE, self.hook)
        self.matrix()

    def hook(self, uc, address, size, data):
        name = self.stub.get(address)
        if not name:
            return
        a, b, c, d = [uc.reg_read(reg) for reg in [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3]]
        result = 0
        if name == 'timer_read32':
            result = self.now
        elif name == 'timer_elapsed32':
            result = (self.now - a) & 0xffffffff
        elif name == 'get_mods':
            result = self.mods
        elif name == 'is_keyboard_master':
            result = 1
        elif name == 'eeprom_read_block':
            assert b + c <= len(self.eeprom), 'EEPROM read exceeds device size'
            uc.mem_write(a, bytes(self.eeprom[b:b + c]))
        elif name == 'eeprom_update_block':
            assert b + c <= len(self.eeprom), 'EEPROM write exceeds device size'
            self.eeprom[b:b + c] = uc.mem_read(a, c)
            self.saved.append((b, c))
        elif name == 'rgb_matrix_set_color':
            expect(a < 88, 'LED index exceeds the chain')
            self.colors[a] = (b, c, d)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def call(self, name, *args):
        uc = self.uc
        for reg, value in zip([UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], args):
            uc.reg_write(reg, value)
        uc.reg_write(UC_ARM_REG_SP, RAM + 0xf000)
        uc.reg_write(UC_ARM_REG_LR, RETURN | 1)
        uc.emu_start(self.symbols[name] | 1, RETURN, count=500000)
        assert uc.reg_read(UC_ARM_REG_PC) == RETURN, name + ' failed to return'
        assert uc.reg_read(UC_ARM_REG_SP) == RAM + 0xf000, name + ' changed stack'
        return uc.reg_read(UC_ARM_REG_R0)

    def matrix(self, enabled=True, brightness=120, speed=153):
        self.uc.mem_write(self.symbols['rgb_matrix_config'], bytes([4 | enabled, 85, 255, brightness, speed, 255, 0, 0]))

    def key(self, keycode, pressed=True, handler='personal_rgb_process_record'):
        # Pinned QMK with short enums: col,row,time16,type8,pressed8.
        record = RAM + 0xe000
        self.uc.mem_write(record, struct.pack('<BBHBB', 4, 3, self.now & 0xffff, 1, pressed) + b'\0' * 10)
        return self.call(handler, keycode, record)

    def tap(self, keycode):
        expect(self.key(keycode) == 0, 'Personal press leaked to host processing')
        expect(self.key(keycode, False) == 0, 'Personal release leaked to host processing')

    def render(self, ripple=False, hits=()):
        # QMK's packed eight-hit snapshot, with time since each press in ms.
        data = bytearray(41)
        data[0] = len(hits)
        for n, (x, y, age) in enumerate(hits):
            data[1 + n] = x
            data[9 + n] = y
            struct.pack_into('<H', data, 25 + 2 * n, age)
        self.uc.mem_write(self.symbols['g_last_hit_tracker'], bytes(data))
        self.colors = {}
        self.call('personal_rgb_render', 0, 88, ripple)
        expect(len(self.colors) == 88, 'Effect omitted LEDs')
        return dict(self.colors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path)
    args = parser.parse_args()
    symbols, segments = read_build(args.toolchain)
    keyboard = json.loads((ROOT / 'keyboard/keyboard.json').read_text())
    codes = {item['key']: 0x7e00 + n for n, item in enumerate(keyboard['keycodes'])}
    via = json.loads((ROOT / 'keyboard/Epomaker Luma84.json').read_text())
    expect([k['name'] for k in via['customKeycodes']] == list(codes), 'VIA custom codes disagree with firmware')
    f = Firmware(symbols, segments)
    untouched = bytes(f.eeprom)
    f.call('personal_rgb_init')
    expect(f.saved == [(808, 8)], 'Defaults overlap vendor or VIA data')
    expect(f.eeprom[:808] == untouched[:808] and f.eeprom[816:] == untouched[816:], 'Defaults changed unrelated EEPROM')
    solid = f.call('rgb_matrix_get_mode')
    f.tap(0x7821) # RGB_MOD in the pinned QMK
    ripple = f.call('rgb_matrix_get_mode')
    expect(solid != ripple, 'Mode toggle did not change effect')
    expect(via['menus'][0]['content'][0]['content'][1]['options'] == [
        ['Solid color', solid], ['Solid color with ripple', ripple]], 'VIA effect IDs disagree with compiled firmware')
    f.tap(0x7821)
    expect(f.call('rgb_matrix_get_mode') == solid, 'Mode cycle contains more than two modes')

    # Check actual compiled Fn mappings on Windows and Mac.
    for layer in [1, 3]:
        for row, col, name in [(3, 9, 'PC_RED_UP'), (4, 8, 'PC_RED_DOWN'),
                               (3, 10, 'PC_GREEN_UP'), (4, 9, 'PC_GREEN_DOWN'),
                               (3, 11, 'PC_BLUE_UP'), (4, 10, 'PC_BLUE_DOWN'),
                               (2, 1, 'KC_BT1'), (2, 2, 'KC_BT2'),
                               (2, 3, 'KC_BT3'), (2, 4, 'KC_2G4')]:
            address = symbols['keymaps'] + 2 * ((layer * 6 + row) * 16 + col)
            expect(struct.unpack('<H', f.uc.mem_read(address, 2))[0] == codes[name], 'Fn color or wireless control is on the wrong key')
        for col, code in [(8, 0x47), (9, 0x48)]:
            address = symbols['keymaps'] + 2 * ((layer * 6 + 2) * 16 + col)
            expect(struct.unpack('<H', f.uc.mem_read(address, 2))[0] == code, 'Fn I/O must remain Scroll Lock/Pause')
        for n in range(10):
            address = symbols['keymaps'] + 2 * ((layer * 6 + 1) * 16 + n + 1)
            expect(struct.unpack('<H', f.uc.mem_read(address, 2))[0] == codes[f'PC_PRESET_{(n + 1) % 10}'], 'Preset is on the wrong digit')

    # All presets retain direct RGB values, and the body follows the keys.
    for n, rgb in enumerate(PRESETS):
        f.tap(codes[f'PC_PRESET_{(n + 1) % 10}'])
        expect(set(f.render().values()) == {tuple(x * 120 // 255 for x in rgb)}, 'Preset RGB differs from the requested channels')

    # Independent channels clamp at both ends and offer one-step fine adjustment.
    for channel, prefix in enumerate(['RED', 'GREEN', 'BLUE']):
        for value in [0, 1, 16, 17, 127, 238, 254, 255]:
            for down in [False, True]:
                f.uc.mem_write(symbols['personal_rgb'] + 4, bytes([value, value, value]))
                f.tap(codes[f'PC_{prefix}_{"DOWN" if down else "UP"}'])
                actual = tuple(f.uc.mem_read(symbols['personal_rgb'] + 4, 3))
                wanted = [value] * 3
                wanted[channel] = max(0, value - 17) if down else min(255, value + 17)
                expect(actual == tuple(wanted), 'Channel adjustment wrapped or changed another channel')
    f.tap(codes['PC_PRESET_6'])
    f.mods = 2 # Left Shift
    f.tap(codes['PC_RED_UP'])
    expect(bytes(f.uc.mem_read(symbols['personal_rgb'] + 4, 3)) == b'\x01\x00\xff', 'Fine adjustment is not one RGB step')
    f.mods = 0

    f.tap(codes['PC_PRESET_6'])
    f.key(codes['PC_RED_UP'])
    f.now += 349
    f.call('personal_rgb_task')
    expect(f.uc.mem_read(symbols['personal_rgb'] + 4, 1)[0] == 17, 'Held key repeated before delay')
    f.now += 1
    f.call('personal_rgb_task')
    expect(f.uc.mem_read(symbols['personal_rgb'] + 4, 1)[0] == 34, 'Held key failed to repeat')
    f.key(codes['PC_RED_UP'], False)
    f.now += 200
    f.call('personal_rgb_task')
    expect(f.uc.mem_read(symbols['personal_rgb'] + 4, 1)[0] == 34, 'Released key continued repeating')

    # Save after the controls settle, then restore in a fresh MCU instance.
    f.tap(codes['PC_PRESET_7'])
    f.tap(0x7821)
    before = len(f.saved)
    f.now += 499
    f.call('personal_rgb_task')
    expect(len(f.saved) == before, 'Saved during the debounce interval')
    f.now += 1
    f.call('personal_rgb_task')
    expect(len(f.saved) == before + 1, 'Did not save after the debounce interval')
    g = Firmware(symbols, segments, f.eeprom)
    g.matrix(enabled=False)
    g.call('personal_rgb_init')
    expect(g.call('rgb_matrix_get_mode') == ripple, 'Saved mode was not restored while disabled')
    expect(g.uc.mem_read(symbols['rgb_matrix_config'], 1)[0] & 3 == 0, 'Loading preferences enabled the lights')
    g.tap(0x7821)
    g.call('personal_rgb_task')
    expect(g.call('rgb_matrix_get_mode') == solid, 'Disabled mode change was lost')
    expect(g.uc.mem_read(symbols['rgb_matrix_config'], 1)[0] & 3 == 0, 'Changing mode enabled the lights')
    expect(set(g.render().values()) == {tuple(x * 120 // 255 for x in PRESETS[6])}, 'Saved color was not restored')

    # An adjacent key lights before a farther key, then the ring moves outward.
    g.tap(codes['PC_PRESET_1'])
    base = g.render()
    layout = keyboard['rgb_matrix']['layout']
    center = next(i for i, led in enumerate(layout) if led['matrix'] == [3, 5])
    x, y = layout[center]['x'], layout[center]['y']
    near = next(i for i, led in enumerate(layout[4:], 4) if led['y'] == y and led['x'] == x + 15)
    far = next(i for i, led in enumerate(layout[4:], 4) if led['y'] == y and led['x'] == x + 30)
    early = g.render(True, [(x, y, 70)])
    later = g.render(True, [(x, y, 140)])
    expect(early[near][1] > early[far][1], 'Ripple did not first reach the neighboring key')
    expect(later[far][1] > later[near][1], 'Ripple did not spread outward')
    expect(later[center] == base[center], 'Ripple did not leave the pressed key behind')
    expect(g.render(True, [(x, y, 2000)]) == base, 'Ripple did not return to the solid background')
    expect(all(early[i] == base[i] for i in range(4)), 'Body lights joined the ripple')
    g.tap(codes['PC_PRESET_0'])
    white = g.render(True, [(x, y, 70)])
    expect(white[near][0] < 120, 'Ripple is invisible on a white background')
    for brightness in [0, 1, 24, 120]:
        g.matrix(brightness=brightness)
        colors = g.render(True, [(x, y, 70), (x + 30, y, 140)])
        expect(all(0 <= c <= brightness for rgb in colors.values() for c in rgb), 'Ripple exceeds selected brightness')
        if not brightness:
            expect(set(colors.values()) == {(0, 0, 0)}, 'Zero brightness left an LED lit')

    # Board-level processing must consume our controls before vendor handlers.
    expect(g.key(codes['PC_PRESET_5'], handler='process_record_kb') == 0, 'Board did not consume personal control')
    expect(g.key(codes['PC_PRESET_5'], False, handler='process_record_kb') == 0, 'Board did not consume release')
    g.matrix()
    g.render()
    g.colors = {}
    g.call('rgb_matrix_indicators_advanced_kb', 0, 88)
    expect(not g.colors, 'Vendor body driver repainted the personal color')

    print(f'Passed {checks} personal RGB assertions from the compiled ELF. No hardware accessed.')


if __name__ == '__main__':
    main()
