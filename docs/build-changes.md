# Changes from EPOMAKER's source

The `personal/wegel` branch also adds [personal RGB controls and two light
effects](personal-build.md). Those changes are kept on this branch.

EPOMAKER published the board at commit
`3753140abcc9ba7c8cca04721f0e1400b82ff9fe`. The vendor README gives the target
`epomaker/hc844:default`, but it does not identify the QMK base or compiler used
for its factory HEX file. This project uses the VIA keymap and the revisions in
`sources.lock.json`.

The compiler needed these changes:

- `keyboard/config.h` adds the QMK names for the vendor's existing serial
  connection: SD3, transmit pin C10, receive pin C11, and alternate function 7.
  The vendor already declares the same serial peripheral and pins under older
  names. This change supplies the names used by QMK and the sleep code.
- `wireless/transport.c` calls
  `usb_device_state_set_protocol(USB_PROTOCOL_REPORT)` instead of writing the
  removed `keyboard_protocol` global.
- `keyboard/rgb_record/rgblight_driver_compat.c` supplies QMK 0.28's custom driver
  interface. It writes the vendor's body-light buffer. The main RGB matrix code
  still copies that buffer into the LED chain, so the adapter does not send a
  second hardware frame.
- `keyboard/rgb_record/rgb_record.mk` compiles that adapter.
- `patches/qmk-rgblight-overrides.patch` lets the vendor's `rgblight_set`, breathing,
  and rainbow-mood functions override QMK's defaults. It marks the three core
  functions weak, which tells the linker to use the vendor's definitions when
  both exist.

QMK 0.28 was chosen because it supplies the APIs used by the board and keeps
the VIA send call at line 461. The vendor's `wireless/md_raw.h` intercepts that
call using a line-number macro. Moving to another QMK revision requires checking
that macro, even if the compiler accepts the code.

These changes make a local build possible. We have not proved that they
reproduce the original vendor build or preserve every hardware behavior.
The original keymaps and saved light flags remain in the source.

## Keep the master light switch off after wake

`RGB_TOG` saves the master light switch in `confinfo.hs_rgb_tog`. The separate
`confinfo.rgb_enable` flag can remain true when the master switch is off.
The original `suspend_wakeup_init_kb()` checks brightness and that separate flag
before restoring LED power, without checking the master switch. Fn release
checks the master switch and cuts LED power, so these handlers can disagree.

`suspend_wakeup_init_kb()` now cuts LED power and disables the key-light matrix
when the master switch is off. `lpwr_wakeup_hook()` also checks the master switch
before raising LED power and disables the matrix in its off branch. The shared
sleep code can restore the matrix before calling these hooks. Both hooks use
`rgb_matrix_disable_noeeprom()`, which changes the running state without saving
new preferences. When the master switch is on, both hooks keep their previous
behavior. Fn's temporary light display remains unchanged.

`tools/test_wake.py` runs both hooks from the compiled firmware in a Cortex-M
emulator. It checks all 256 combinations of the saved flag byte, zero and nonzero
brightness, initial LED power, and initial matrix state: 4,096 cases in total.
The checks require LED power and the matrix to stay off when the master switch
is off, preserve the previous behavior when it is on, and reject calls that
would save preferences. The unmodified build fails the off-state checks.

On October 28, 2026, one owner flashed the source build from `3f660be` and
reported that everything seemed to work so far. This records one keyboard and
setup; the owner did not list individual feature tests, connection modes, or
test duration. Firmware dumps and the earlier binary patch remain outside this
repository.
