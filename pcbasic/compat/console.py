"""
PC-BASIC - compat.console
Cross-platform compatibility utilities

(c) 2018 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import sys
from collections import deque

from .base import PY2, WIN32


if PY2:
    import codecs

    if WIN32:
        from .win32_console import bstdin, bstdout, bstderr
        #from .colorama import AnsiToWin32
        #bstdout, bstderr = AnsiToWin32(bstdout).stream, AnsiToWin32(bstderr).stream
    else:
        bstdin, bstdout, bstderr = sys.stdin, sys.stdout, sys.stderr

    def _wrap_output_stream(stream):
        """Wrap std streams to make them behave more like in Python 3."""
        wrapped = codecs.getwriter(stream.encoding or 'utf-8')(stream)
        wrapped.buffer = stream
        return wrapped

    def _wrap_input_stream(stream):
        """Wrap std streams to make them behave more like in Python 3."""
        wrapped = codecs.getreader(stream.encoding or 'utf-8')(stream)
        wrapped.buffer = stream
        return wrapped

    stdin = _wrap_input_stream(bstdin)
    stdout = _wrap_output_stream(bstdout)
    stderr = _wrap_output_stream(bstderr)

else:
    stdin, stdout, stderr = sys.stdin, sys.stdout, sys.stderr

if WIN32:
    import msvcrt

    from ctypes import windll, byref
    from ctypes.wintypes import DWORD

    # determine if we have a console attached or are a GUI app
    def _has_console():
        try:
            STD_OUTPUT_HANDLE = -11
            handle = windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            dummy_mode = DWORD(0)
            return bool(windll.kernel32.GetConsoleMode(handle, byref(dummy_mode)))
        except Exception as e:
            return False

    HAS_CONSOLE = _has_console()

    def set_raw():
        pass

    def unset_raw():
        pass

    # key pressed on keyboard
    from msvcrt import kbhit as key_pressed

    try:
        # set stdio as binary, to avoid Windows messing around with CRLFs
        # only do this for redirected output, as it breaks interactive Python sessions
        # pylint: disable=no-member
        if not sys.stdin.isatty():
            msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        if not sys.stdout.isatty():
            msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
        pass
    except EnvironmentError:
        # raises an error if started in gui mode, as we have no stdio
        pass

    def read_all_available(stream):
        """Read all available characters from a stream; nonblocking; None if closed."""
        if hasattr(stream, 'isatty') and stream.isatty():
            instr = []
            # get characters while keyboard buffer has them available
            # this does not echo
            while msvcrt.kbhit():
                c = msvcrt.getch()
                if not c:
                    return None
                instr.append(c)
            return b''.join(instr)
        else:
            # this would work on unix too
            # just read the whole file and be done with it
            return stream.read() or None

else:
    import tty, termios, select, fcntl, array

    # output buffer for ioctl call
    _sock_size = array.array('i', [0])

    # no such thing as console- and GUI-apps
    # check if we can treat stdin like a tty, file or socket
    HAS_CONSOLE = True
    if not sys.stdin.isatty():
        try:
            fcntl.ioctl(sys.stdin, termios.FIONREAD, _sock_size)
        except EnvironmentError:
            # maybe /dev/null, but not a real file or console
            HAS_CONSOLE = False
            if MACOS:
                # for macOS - presumably we're launched as a bundle, set working directory to user home
                # bit of a hack but I don't know a better way
                os.chdir(HOME_DIR)

    # save termios state
    _term_attr = None

    def set_raw():
        """Enter raw terminal mode."""
        global _term_attr
        fd = sys.stdin.fileno()
        _term_attr = termios.tcgetattr(fd)
        tty.setraw(fd)

    def unset_raw():
        """Leave raw terminal mode."""
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _term_attr)

    def key_pressed():
        """Return whether a character is ready to be read from the keyboard."""
        return select.select([sys.stdin], [], [], 0)[0] != []

    def read_all_available(stream):
        """Read all available characters from a stream; nonblocking; None if closed."""
        # this function works for everything on unix, and sockets on Windows
        instr = []
        # we're getting bytes counts for unicode which is pretty useless - so back to bytes
        try:
            encoding = stream.encoding
            stream = stream.buffer
        except:
            encoding = None
        # if buffer has characters/lines to read
        if select.select([stream], [], [], 0)[0]:
            # find number of bytes available
            fcntl.ioctl(stream, termios.FIONREAD, _sock_size)
            count = _sock_size[0]
            # and read them all
            c = stream.read(count)
            if not c and not instr:
                # break out, we're closed
                return None
            instr.append(c)
        if encoding:
            return b''.join(instr).decode(encoding, 'replace')
        return b''.join(instr)


# console is a terminal (tty)
is_tty = sys.stdin.isatty()

# input buffer
_read_buffer = deque()

def read_char():
    """Read unicode char from console, non-blocking."""
    s = read_all_available(sys.stdin)
    if s is None:
        # stream closed, send ctrl-d
        if not _read_buffer:
            return u'\x04'
    else:
        _read_buffer.extend(list(s))
    if _read_buffer:
        return _read_buffer.popleft()
    return u''

def write(unicode_str):
    """Write unicode to console."""
    stdout.write(unicode_str)
    stdout.flush()
