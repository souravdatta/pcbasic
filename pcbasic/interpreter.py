"""
PC-BASIC - interpreter.py
Main interpreter loop

(c) 2013, 2014, 2015, 2016 Rob Hagemans
This file is released under the GNU GPL version 3 or later.
"""

import os
import sys
import traceback
import logging
import time
import threading

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import plat
import error
import util
import tokenise
import program
import signals
import statements
import display
import console
import state
import events
# prepare input state
import inputs
import reset
import flow
import debug
import config
import devices
import cassette
import disk
import var


class SessionLauncher(object):
    """ Launches a BASIC session. """

    def __init__(self):
        """ Initialise launch parameters. """
        self.quit = config.get('quit')
        self.wait = config.get('wait')
        self.cmd = config.get('exec')
        self.prog = config.get(0) or config.get('run') or config.get('load')
        self.run = (config.get(0) != '') or (config.get('run') != '')
        self.resume = config.get('resume')
        # following GW, don't write greeting for redirected input
        # or command-line filter run
        self.show_greeting = (not self.run and not self.cmd and
            not config.get('input') and not config.get('interface') == 'none')
        if self.resume:
            self.cmd, self.run = '', False

    def __enter__(self):
        """ Resume or start the session. """
        if self.resume and state.load():
            state.basic_state.session.resume()
        else:
            state.basic_state.session = Session(self.show_greeting, self.prog)
        self.thread = threading.Thread(target=state.basic_state.session.run,
                                args=(self.cmd, self.run, self.quit, self.wait))
        self.thread.start()

    def __exit__(self, dummy_one, dummy_two, dummy_three):
        """ Wait for the interpreter to exit. """
        if self.thread and self.thread.is_alive():
            # request exit
            signals.input_queue.put(signals.Event(signals.KEYB_QUIT))
            # wait for thread to finish
            self.thread.join()


###############################################################################
# interpreter session

greeting = (
    'PC-BASIC {version}\r'
    '(C) Copyright 2013--2016 Rob Hagemans.\r'
    '{free} Bytes free')


class ResumeFailed(Exception):
    """ Failed to resume session. """
    def __str__(self):
        return self.__doc__


class Session(object):
    """ Interpreter session. """

    def __init__(self, greet, load):
        """ Initialise the interpreter session. """
        # true if a prompt is needed on next cycle
        self.prompt = True
        # input mode is AUTO (used by AUTO)
        self.auto_mode = False
        self.auto_linenum = 10
        self.auto_increment = 10
        # interpreter is waiting for INPUT or LINE INPUT
        self.input_mode = False
        # previous interpreter mode
        self.last_mode = False, False
        # syntax error prompt and EDIT
        self.edit_prompt = False
        # initialise the display
        display.init()
        # interpreter is executing a command
        self.set_parse_mode(False)
        # initialise the console
        console.init_mode()


        # bytecode buffer is defined in memory.py
        # direct line buffer
        self.direct_line = StringIO()

        # find program for PCjr TERM command
        pcjr_term = config.get('pcjr-term')
        if pcjr_term and not os.path.exists(pcjr_term):
            pcjr_term = os.path.join(plat.info_dir, pcjr_term)
        if not os.path.exists(pcjr_term):
            pcjr_term = ''
        # initialise the parser
        self.parser = statements.Parser(self, config.get('syntax'), pcjr_term)
        state.basic_state.parser = self.parser

        # program parameters
        if not config.get('strict-hidden-lines'):
            max_list_line = 65535
        else:
            max_list_line = 65530
        allow_protect = config.get('strict-protect')
        # initialise the program
        self.program = program.Program(max_list_line, allow_protect)
        # load initial program
        if load:
            # on load, accept capitalised versions and default extension
            with disk.open_native_or_dos_filename(load) as progfile:
                self.program.load(progfile)

        # set up interpreter and memory model state
        reset.clear()
        # greeting and keys
        if greet:
            console.clear()
            console.write_line(greeting.format(version=plat.version, free=var.fre()))
            console.show_keys(True)


    def resume(self):
        """ Resume an interpreter session. """
        # resume from saved emulator state (if requested and available)
        # reload the screen in resumed state
        if not state.console_state.screen.resume():
            raise ResumeFailed()
        # rebuild the audio queue
        for q, store in zip(signals.tone_queue, state.console_state.tone_queue_store):
            signals.load_queue(q, store)
        # override selected settings from command line
        cassette.override()
        disk.override()
        # suppress double prompt
        if not self.parse_mode:
            self.prompt = False


    def run(self, command, run, quit, wait):
        """ Interactive interpreter session. """
        if command:
            self.store_line(command)
            self.loop()
        if run:
            # position the pointer at start of program and enter execute mode
            self.parser.jump(None)
            self.set_parse_mode(True)
            state.console_state.screen.cursor.reset_visibility()
        try:
            try:
                while True:
                    self.loop()
                    if quit and state.console_state.keyb.buf.is_empty():
                        break
            except error.Exit:
                # pause before exit if requested
                if wait:
                    signals.video_queue.put(signals.Event(signals.VIDEO_SET_CAPTION, 'Press a key to close window'))
                    signals.video_queue.put(signals.Event(signals.VIDEO_SHOW_CURSOR, False))
                    state.console_state.keyb.pause = True
                    # this performs a blocking keystroke read if in pause state
                    events.check_events()
            finally:
                # close interfaces
                signals.video_queue.put(signals.Event(signals.VIDEO_QUIT))
                signals.message_queue.put(signals.Event(signals.AUDIO_QUIT))
                # persist unplayed tones in sound queue
                state.console_state.tone_queue_store = [
                        signals.save_queue(q) for q in signals.tone_queue]
                state.save()
                # close files if we opened any
                devices.close_files()
                devices.close_devices()
        except error.Reset:
            # delete state if resetting
            state.delete()

    def loop(self):
        """ Run read-eval-print loop until control returns to user after a command. """
        try:
            while True:
                self.last_mode = self.parse_mode, self.auto_mode
                if self.parse_mode:
                    try:
                        # may raise Break
                        events.check_events()
                        self.handle_basic_events()
                        # returns True if more statements to parse
                        if not self.parser.parse_statement():
                            self.parse_mode = False
                    except error.RunError as e:
                        self.trap_error(e)
                    except error.Break as e:
                        # ctrl-break stops foreground and background sound
                        state.console_state.sound.stop_all_sound()
                        self.handle_break(e)
                elif self.auto_mode:
                    try:
                        # auto step, checks events
                        self.auto_step()
                    except error.Break:
                        # ctrl+break, ctrl-c both stop background sound
                        state.console_state.sound.stop_all_sound()
                        self.auto_mode = False
                else:
                    self.show_prompt()
                    try:
                        # input loop, checks events
                        line = console.wait_screenline(from_start=True)
                        self.prompt = not self.store_line(line)
                    except error.Break:
                        state.console_state.sound.stop_all_sound()
                        self.prompt = False
                        continue
                # change loop modes
                if self.switch_mode():
                    break
        except error.RunError as e:
            self.handle_error(e)
            self.prompt = True
        except error.Exit:
            raise
        except error.Reset:
            raise
        except Exception as e:
            if debug.debug_mode:
                raise
            debug.bluescreen(e)

    def set_parse_mode(self, on):
        """ Enter or exit parse mode. """
        self.parse_mode = on
        state.console_state.screen.cursor.default_visible = not on

    def switch_mode(self):
        """ Switch loop mode. """
        last_execute, last_auto = self.last_mode
        if self.parse_mode != last_execute:
            # move pointer to the start of direct line (for both on and off!)
            self.parser.set_pointer(False, 0)
            state.console_state.screen.cursor.reset_visibility()
        return ((not self.auto_mode) and
                (not self.parse_mode) and last_execute)

    def store_line(self, line):
        """ Store a program line or schedule a command line for execution. """
        if not line:
            return True
        self.direct_line = tokenise.tokenise_line(line)
        c = util.peek(self.direct_line)
        if c == '\0':
            # check for lines starting with numbers (6553 6) and empty lines
            self.program.check_number_start(self.direct_line)
            self.program.store_line(self.direct_line)
            reset.clear()
        elif c != '':
            # it is a command, go and execute
            self.set_parse_mode(True)
        return not self.parse_mode

    def show_prompt(self):
        """ Show the Ok or EDIT prompt, unless suppressed. """
        if self.parse_mode:
            return
        if self.edit_prompt:
            linenum, tell = self.edit_prompt
            self.program.edit(linenum, tell)
            self.edit_prompt = False
        elif self.prompt:
            console.start_line()
            console.write_line("Ok\xff")

    def auto_step(self):
        """ Generate an AUTO line number and wait for input. """
        numstr = str(self.auto_linenum)
        console.write(numstr)
        if self.auto_linenum in self.program.line_numbers:
            console.write('*')
            line = bytearray(console.wait_screenline(from_start=True))
            if line[:len(numstr)+1] == numstr+'*':
                line[len(numstr)] = ' '
        else:
            console.write(' ')
            line = bytearray(console.wait_screenline(from_start=True))
        # run or store it; don't clear lines or raise undefined line number
        self.direct_line = tokenise.tokenise_line(line)
        c = util.peek(self.direct_line)
        if c == '\0':
            # check for lines starting with numbers (6553 6) and empty lines
            empty, scanline = self.program.check_number_start(self.direct_line)
            if not empty:
                self.program.store_line(self.direct_line)
                reset.clear()
            self.auto_linenum = scanline + self.auto_increment
        elif c != '':
            # it is a command, go and execute
            self.set_parse_mode(True)


    ##############################################################################
    # event and error handling

    def handle_basic_events(self):
        """ Jump to user-defined event subs if events triggered. """
        if self.parser.events.suspend_all or not self.parser.run_mode:
            return
        for event in self.parser.events.all:
            if (event.enabled and event.triggered
                    and not event.stopped and event.gosub is not None):
                # release trigger
                event.triggered = False
                # stop this event while handling it
                event.stopped = True
                # execute 'ON ... GOSUB' subroutine;
                # attach handler to allow un-stopping event on RETURN
                self.parser.jump_gosub(event.gosub, event)

    def trap_error(self, e):
        """ Handle a BASIC error through trapping. """
        if e.pos is None:
            if self.parser.run_mode:
                e.pos = state.basic_state.bytecode.tell()-1
            else:
                e.pos = -1
        state.basic_state.errn = e.err
        state.basic_state.errp = e.pos
        # don't jump if we're already busy handling an error
        if state.basic_state.on_error is not None and state.basic_state.on_error != 0 and not state.basic_state.error_handle_mode:
            state.basic_state.error_resume = self.parser.current_statement, self.parser.run_mode
            self.parser.jump(state.basic_state.on_error)
            state.basic_state.error_handle_mode = True
            self.parser.events.suspend_all = True
        else:
            raise e

    def handle_error(self, e):
        """ Handle a BASIC error through error message. """
        # not handled by ON ERROR, stop execution
        console.write_error_message(e.message, self.program.get_line_number(e.pos))
        state.basic_state.error_handle_mode = False
        self.set_parse_mode(False)
        self.input_mode = False
        # special case: syntax error
        if e.err == error.STX:
            # for some reason, err is reset to zero by GW-BASIC in this case.
            state.basic_state.errn = 0
            if e.pos != -1:
                # line edit gadget appears
                self.edit_prompt = (self.program.get_line_number(e.pos), e.pos+1)

    def handle_break(self, e):
        """ Handle a Break event. """
        # print ^C at current position
        if not self.input_mode and not e.stop:
            console.write('^C')
        # if we're in a program, save pointer
        pos = -1
        if self.parser.run_mode:
            pos = state.basic_state.bytecode.tell()
            self.parser.stop = pos
        console.write_error_message(e.message, self.program.get_line_number(pos))
        self.set_parse_mode(False)
        self.input_mode = False
