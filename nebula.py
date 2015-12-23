#!/usr/bin/env python3
# Nebula core file.
#
# Copyright (C) 2015 Isaac Dickinson.
#
# This file is part of Nebula.
#
# Nebula is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Foobar is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nebula.  If not, see <http://www.gnu.org/licenses/>.
import os
from collections import OrderedDict

__version__ = (0, 0, 1)

# Imports
import threading
import asyncio
import yaml
import logging
import logging.handlers
import sys
import subprocess
try:
    import setproctitle
except ImportError:
    print("Nebula - Setproctitle is not installed. Recommendation: install it.")
else:
    setproctitle.setproctitle("nebula")
import ctypes
import signal

# We define our own EventLoopPolicy to create FastChildWatcher
# this means asyncio can perform the hard work of child murdering
# asyncio babysitting service - only £19.95 a hour
# 100% effective


class NebulaEventLoopPolicy(asyncio.unix_events._UnixDefaultEventLoopPolicy):
     def _init_watcher(self):
        with asyncio.events._lock:
            if self._watcher is None:
                # Cr
                self._watcher = asyncio.FastChildWatcher()
                if isinstance(threading.current_thread(),
                              threading._MainThread):
                    self._watcher.attach_loop(self._local._loop)

asyncio.set_event_loop_policy(NebulaEventLoopPolicy())
loop = asyncio.get_event_loop()

# Load libc.
libc = ctypes.CDLL("libc.so.6")

# The process table is a master table for every process spawned by Nebula.
# It is key-value of service => list of processes spawned.
# This list consists of tuples with two values:
#  - the PID
#  - the subprocess object created by asyncio.
process_table = {}

# The unit table consists of a dictionary that maps the unit name to the YAML dictionary.
unit_table = OrderedDict()

# Define a logger.
logger = logging.getLogger("nebula")
logger.setLevel(logging.DEBUG)

# region logger
# Method for setting up logger.
# Called after mounting everything.
def setup_logger():
    if not os.path.exists("/var/log/nebula"):
        os.makedirs("/var/log/nebula")

    ch = logging.StreamHandler(sys.stdout)

    # Quick and dirty hack to fuck up logging easily.
    logging.addLevelName( logging.DEBUG, "\033[1;35m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
    logging.addLevelName( logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName( logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName( logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName( logging.CRITICAL, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.CRITICAL))

    format = logging.Formatter("[%(levelname)s] - %(message)s")


    ch.setFormatter(format)
    logger.addHandler(ch)

    fh = logging.handlers.RotatingFileHandler("/var/log/nebula/nebula.log", maxBytes=(1048576*5), backupCount=7)
    logger.addHandler(fh)
# endregion

# Define a callback handler for the unix socket.
async def connection_cb(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    writer.close()

# Define a rescue function.
def rescue():
    print("Something bad happened - dropping to an emergency shell.")
    print("Exit this shell to continue.")
    subprocess.call(["/bin/sh"])

print("Nebula version {} starting!".format('.'.join(map(str, __version__))))

#region fstab

# Load fstab.
with open("/etc/fstab") as fstab:
    print("Nebula - Mounting filesystems...")
    # Parse and mount.
    for n, line in enumerate(fstab.readlines()):
        if line.startswith("#"):
            continue
        if line == "\n":
            continue
        n += 1
        if '\t' in line:
            sp = line.split('\t')
        elif ' ' in line:
            sp = line.split(' ')
        else:
            print("Nebula - Unable to parse line {} of fstab - skipping ({})".format(n, line))
            continue
        # Strip extras.
        sp = [i.replace('\t', '').replace(' ', '') for i in sp]
        # Mount.
        if sp[1] == "/":
            # We've already mounted root. Ignore.
            continue
        # Noauto
        if 'noauto' in sp[3]:
            continue
        # Vboxsf
        if sp[2] == 'vboxsf':
            verb = ""
        else:
            verb = "-v"
        ret = subprocess.call("mount {verb} -t {type} -o {options} {fs} {mountpoint}".format(type=sp[2], options=sp[3],
                fs=sp[0], mountpoint=sp[1], verb=verb).split())
        if ret:
            print("Nebula - Unable to mount filesystem, skipping")
            continue
        # mounted

# endregion

# Remount root as read-write if we can.
print("Nebula - Remounting filesystem...")
try:
    subprocess.check_call("mount -v -o remount,rw /".split())
except subprocess.CalledProcessError:
    logger.error("Unable to remount root!")
    logger.error("Bailing out, you're on your own now.")
    rescue()

setup_logger()

# Begin initialization.
logger.info("Early init completed - starting system")

# Check our cmdline.
with open("/proc/cmdline", 'r') as f:
    sp = f.read().split(' ')
    sp = [s.replace('\n', '') for s in sp]
    if 'rescue' in sp or 'nebula.rescue' in sp:
        rescue()
    else:
        for item in sp:
            if 'nebula.loglevel' in item:
                i = item.split('=')
                if len(i) >= 2:
                    if hasattr(logging, i[1]):
                        logger.setLevel(getattr(logging, i[1]))


# Clear screen
print("\033c", end='')

# region Setup

logger.info("Setting hostname...")
with open("/etc/hostname", 'a+') as f:
    data = f.read().encode()
    length = len(data)
    libc.sethostname(data, ctypes.c_size_t(length))


# endregion

logger.info("Loading unit files...")

def _reraise(err):
    raise err

def load_unit_files():
    # Scandir items in /etc/nebula/enabled
    if not os.path.exists("/etc/nebula/enabled"):
        os.makedirs("/etc/nebula/enabled")
    items = sorted(os.scandir("/etc/nebula/enabled"), key=lambda x:x.name)
    for item in items:
        if not item.name.endswith(".yml"):
            continue
        logger.debug("Loading unit file {}".format(item.name))
        with open(item.path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except Exception as e:
                logger.error("Unable to load file {}: {}".format(item.name, e))
                continue
        try:
            unit_table[data["name"]] = data
        except KeyError:
            logger.error("Unit file {} does not have a name specified!".format(item.name))

# Try and load unit files.
try:
    load_unit_files()
except FileNotFoundError:
    logger.error("Cannot find unit files!")
    rescue()

async def run_unit(commands, wait, name) -> list:
    processes = []
    failed = False
    for command in commands:
        # Spawn a new asyncio Process.
        logger.debug("Running command: {}".format(command))
        proc = await asyncio.create_subprocess_exec(*command.split(" "))
        if wait:
            exitstatus = await proc.wait()
            if exitstatus != 0:
                logger.error("Command '{}' for unit {} failed with error code {}.".format(command, name, ret))
                failed = True
                break
        if failed:
            break
        else:
            # Setup the table
            processes.append((proc.pid, proc))
    return processes, failed

# Begin running units.
async def run_units():
    # Complex logic!
    for name, data in unit_table.items():
        failed = False
        logger.info("Starting service {}...".format(name))
        # Check 'commands'
        cmds = data['commands']
        # Get the options
        options = cmds.get("options", [])
        if "wait" in options:
            wait = True
        else:
            wait = False

        start_commands = cmds.get("start", [])
        if isinstance(start_commands, str): start_commands = [start_commands]
        processes, failed = await run_unit(start_commands, wait, name)

        if failed:
            logger.error("Unit {} failed to start.".format(name))
        else:
            logger.info("Started unit {}".format(name))
            process_table[name] = processes

async def clean_children(*args, **kwargs):
    # Clean up surrogate children.
    # This is for things like dhcpcd and other processes that fork to background without asking us permission.
    # Loop until we can't clean any more children.
    logger.debug("Called signal handler")
    try:
        reap = os.waitpid(-1, os.WNOHANG)
        if reap == (0,0):
            # no more children
            return
        logger.debug("Reaped {}".format(reap))
    except ChildProcessError:
        # No more children to terminate
        return


# Define a main function.
async def main():

    def hup_handler(*args, **kwargs):
        load_unit_files()

    # Add signal handlers.
    loop.add_signal_handler(1, hup_handler)
    loop.add_signal_handler(10, hup_handler)
    # add our SIGCHLD handler.
    # loop.add_signal_handler(signal.SIGCHLD, loop.create_task, clean_children())
    # nvm asyncio

    await run_units()

# Begin Nebula daemon.
loop.create_task(main())
try:
    loop.run_forever()
except KeyboardInterrupt:
    loop.stop()
loop.close()