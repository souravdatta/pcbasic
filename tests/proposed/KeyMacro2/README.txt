this proposed test aims to use --keys to trigger key macros and key event traps
this doesn't work, for at least two reasons:
1. --keys injects only eascii, not the scancode, while event traps are scancode based
2. event traps pick keypress events out before they enter the key buffer, while --keys injects into the key buffer
3. even if the above are amended, the key events are only activated when the program runs, while the injection through the Session object has to happen before the program takes control. this would perhaps be possible in a test frame interface

A similar issue would occur if we wanted to test key definitions (KEYDEF.BAS)
