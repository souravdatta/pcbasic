"""
PC-BASIC - dos.py
Operating system shell and environment

(c) 2013--2018 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import subprocess
import logging
import threading
import time
import shlex
from collections import deque

from .base import error
from . import values


# delay for input threads, in seconds
DELAY = 0.001

# the shell's encoding
# strange to use sys.stdin but locale.getpreferredencoding() is definitely wrong on Windows
# whereas this seems to work if started from console
# - but does this work if launched from a pythonw link? no
ENCODING = sys.stdin.encoding or 'utf-8'
ENCODING = 'utf-8' if ENCODING == 'cp65001' else ENCODING


class InitFailed(Exception):
    """Shell object initialisation failed."""
    def __init__(self, msg=u''):
        self._msg = msg
    def __str__(self):
        return self._msg


#########################################
# calling shell environment

class Environment(object):
    """Handle environment changes."""

    def __init__(self, values):
        """Initialise."""
        self._values = values

    def environ_(self, args):
        """ENVIRON$: get environment string."""
        expr, = args
        if isinstance(expr, values.String):
            parm = expr.to_str()
            if not parm:
                raise error.BASICError(error.IFC)
            envstr = os.getenv(parm) or b''
        else:
            expr = values.to_int(expr)
            error.range_check(1, 255, expr)
            envlist = list(os.environ)
            if expr > len(envlist):
                envstr = ''
            else:
                envstr = '%s=%s' % (envlist[expr-1], os.getenv(envlist[expr-1]))
        return self._values.new_string().from_str(envstr)

    def environ_statement_(self, args):
        """ENVIRON: set environment string."""
        envstr = values.next_string(args)
        list(args)
        eqs = envstr.find('=')
        if eqs <= 0:
            raise error.BASICError(error.IFC)
        envvar = str(envstr[:eqs])
        val = str(envstr[eqs+1:])
        os.environ[envvar] = val


#########################################
# shell

def get_shell_manager(*args, **kwargs):
    """Return a new shell manager object."""
    # move to shell_ generator
    try:
        if sys.platform == 'win32':
            return WindowsShell(*args, **kwargs)
        else:
            return UnixShell(*args, **kwargs)
    except InitFailed as e:
        return NoShell(warn=e)


class NoShell(object):
    """Launcher to throw IFC for emulation targets with no DOS."""

    def __init__(self, warn=None, *args, **kwargs):
        """Initialise the shell."""
        self._warn = warn

    def launch(self, command):
        """Launch the shell."""
        if self._warn:
            logging.warning(b'SHELL statement not enabled: %s', self._warn)
        raise error.BASICError(error.IFC)


class BaseShell(object):
    """Launcher for command shell."""

    # these should be overridden
    _command_pattern = u''
    _eol = b''
    _echoes = False

    def __init__(self, queues, keyboard, screen, codepage, shell):
        """Initialise the shell."""
        if not shell:
            raise InitFailed('No command interpreter (shell) specified.')
        self._shell = shell
        self._queues = queues
        self._keyboard = keyboard
        self._screen = screen
        self._codepage = codepage

    def _process_stdout(self, stream, output):
        """Retrieve SHELL output and write to console."""
        while True:
            # blocking read
            c = stream.read(1)
            if c:
                # don't access screen in this thread
                # the other thread already does
                output.append(c)
            else:
                # don't hog cpu, sleep 1 ms
                time.sleep(DELAY)

    def launch(self, command):
        """Run a SHELL subprocess."""
        shell_output = deque()
        shell_cerr = deque()
        cmd = [e.decode('utf-8') for e in shlex.split(self._shell.encode('utf-8'))]
        if command:
            cmd += [self._command_pattern, self._codepage.str_to_unicode(command)]
        try:
            p = subprocess.Popen(
                    cmd, shell=False,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (EnvironmentError, UnicodeEncodeError) as e:
            logging.warning(u'SHELL: command interpreter `%s` not accessible: %s', self._shell, e)
            raise error.BASICError(error.IFC)
        outp = threading.Thread(target=self._process_stdout, args=(p.stdout, shell_output))
        # daemonise or join later?
        outp.daemon = True
        outp.start()
        errp = threading.Thread(target=self._process_stdout, args=(p.stderr, shell_cerr))
        errp.daemon = True
        errp.start()
        word = []
        while p.poll() is None or shell_output or shell_cerr:
            self._show_output(shell_output)
            self._show_output(shell_cerr)
            if p.poll() is not None:
                # drain output then break
                continue
            try:
                self._queues.wait()
                # expand=False suppresses key macros
                c = self._keyboard.get_fullchar(expand=False)
            except error.Break:
                pass
            if not c:
                continue
            elif c in (b'\r', b'\n'):
                n_chars = len(word)
                # shift the cursor left so that CMD.EXE's echo can overwrite
                # the command that's already there.
                if self._echoes:
                    self._screen.write(b'\x1D' * len(word))
                else:
                    self._screen.write_line()
                # send line-buffered input to pipe
                self._send_input(p.stdin, word)
                word = []
            elif c == b'\b':
                # handle backspace
                if word:
                    word.pop()
                    self._screen.write(b'\x1D \x1D')
            elif not c.startswith(b'\0'):
                # exclude e-ascii (arrow keys not implemented)
                word.append(c)
                self._screen.write(c)

    def _send_input(self, pipe, word):
        """Write keyboard input to pipe."""
        bytes_word = b''.join(word) + self._eol
        unicode_word = self._codepage.str_to_unicode(bytes_word, preserve_control=True)
        pipe.write(unicode_word.encode(ENCODING, errors='replace'))

    def _show_output(self, shell_output):
        """Write shell output to screen."""
        if shell_output:
            lines = []
            while shell_output:
                lines.append(shell_output.popleft())
            lines = b''.join(lines).split(self._eol)
            lines = (l.decode(ENCODING, errors='replace') for l in lines)
            lines = (self._codepage.str_from_unicode(l, errors='replace') for l in lines)
            self._screen.write('\r'.join(lines))


class UnixShell(BaseShell):
    """Launcher for Unix shell."""

    _command_pattern = u'-c'
    _eol = b'\n'
    _echoes = False


class WindowsShell(UnixShell):
    """Launcher for Windows shell."""

    _command_pattern = u'/C'
    _eol = b'\r\n'
    _echoes = True
