#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the built wake hooks in a Cortex-M emulator, without accessing hardware."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import struct
import subprocess

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_SP

ROOT = Path(__file__).resolve().parents[1]
FLASH = 0x08000000
RAM = 0x20000000
RETURN = FLASH + 0x3f000


def read_build(toolchain):
    path = ROOT / 'dist/epomaker_hc844_via.elf'
    report = json.loads((ROOT / 'dist/build.json').read_text())
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['artifacts'][path.name]['sha256']:
        raise SystemExit('ELF differs from dist/build.json; rebuild first')
    for name, expected in report['source_sha256'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise SystemExit('Source changed since compilation: ' + name)
    nm = toolchain / 'bin/arm-none-eabi-nm' if toolchain else next(
        (ROOT / 'work').glob('xpack*/bin/arm-none-eabi-nm'))
    output = subprocess.check_output([str(nm), '-P', str(path)], text=True)
    symbols = {parts[0]: int(parts[2], 16) for line in output.splitlines()
               if len(parts := line.split()) >= 3 and parts[1] != 'U'}
    # Load both the flash copy and runtime RAM copy of initialized data.
    assert raw[:7] == b'\x7fELF\x01\x01\x01', 'Expected little-endian ELF32'
    phoff = struct.unpack_from('<I', raw, 28)[0]
    phsize, phcount = struct.unpack_from('<HH', raw, 42)
    segments = []
    for index in range(phcount):
        kind, offset, virtual, physical, size, _, _, _ = struct.unpack_from(
            '<8I', raw, phoff + index * phsize)
        if kind == 1 and size:
            segments.append((virtual, raw[offset:offset + size]))
            if physical != virtual:
                segments.append((physical, raw[offset:offset + size]))
    return symbols, segments


def check(symbols, segments, hook, flags, brightness, matrix_on, power_on):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    uc.mem_map(FLASH, 0x40000)
    uc.mem_map(RAM, 0x10000)
    uc.mem_map(0x40000000, 0x1000)
    for address, data in segments:
        uc.mem_write(address, data)
    # These are the layouts in the pinned QMK and board source, not an OEM dump.
    confinfo = bytes([1, 0, flags, 7])
    uc.mem_write(symbols['confinfo'], confinfo)
    uc.mem_write(symbols['rgb_matrix_config'], bytes([16 | matrix_on, 85, 255, brightness, 128, 0, 0, 0]))
    uc.reg_write(UC_ARM_REG_SP, RAM + 0x8000)
    uc.reg_write(UC_ARM_REG_LR, RETURN | 1)
    state = {'power': power_on, 'enabled_writes': 0}
    # Isolate radio, host callbacks and time; execute the real QMK RGB routines.
    stubs = {'wireless_get_current_devs': 0, 'wireless_devs_change': 0,
             'suspend_wakeup_init_user': 0, 'hs_rgb_blink_set_timer': 0,
             'timer_read32': 123, 'hs_mode_scan': 0}
    returns = {symbols[name]: value for name, value in stubs.items() if name in symbols}
    eeprom = {address: name for name, address in symbols.items()
              if name.startswith(('eeconfig_', 'eeprom_'))}
    def code(machine, address, size, data):
        if address in eeprom:
            raise AssertionError('Wake must not change saved settings: ' + eeprom[address])
        if address in returns:
            machine.reg_write(UC_ARM_REG_R0, returns[address])
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
    def write(machine, access, address, size, value, data):
        if address == 0x40000018:
            if value & 0x100:
                state['power'] = True
                state['enabled_writes'] += 1
            if value & 0x1000000:
                state['power'] = False
    uc.hook_add(UC_HOOK_CODE, code)
    uc.hook_add(UC_HOOK_MEM_WRITE, write)
    uc.emu_start(symbols[hook] | 1, RETURN, count=1000)
    label = (hook, hex(flags), brightness, matrix_on, power_on)
    assert uc.reg_read(UC_ARM_REG_PC) == RETURN, ('Hook did not return', label)
    assert uc.reg_read(UC_ARM_REG_SP) == RAM + 0x8000, ('Stack not restored', label)
    assert uc.mem_read(symbols['confinfo'], 4) == confinfo, ('Saved flags changed', label)
    enabled = uc.mem_read(symbols['rgb_matrix_config'], 1)[0] & 3
    if not flags & 0x80:
        assert not enabled, ('Key matrix re-enabled with master off', label)
        assert not state['power'], ('LED power left on with master off', label)
        assert not state['enabled_writes'], ('LED power briefly enabled with master off', label)
    else:
        expected_power = True if hook == 'lpwr_wakeup_hook' else power_on or bool(brightness and flags & 0x20)
        assert state['power'] == expected_power, ('Enabled power behavior changed', label)
        assert enabled == matrix_on, ('Enabled matrix behavior changed', label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, help='Same compiler directory passed to tools/build.py')
    args = parser.parse_args()
    symbols, segments = read_build(args.toolchain)
    hooks = ['suspend_wakeup_init_kb', 'lpwr_wakeup_hook']
    cases = 0
    for case in itertools.product(hooks, range(256), [0, 96], [False, True], [False, True]):
        check(symbols, segments, *case)
        cases += 1
    print(f'Passed {cases} wake-hook cases from the compiled ELF. No hardware accessed.')


if __name__ == '__main__':
    main()
