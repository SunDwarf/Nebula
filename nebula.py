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
# Nebula is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Nebula.  If not, see <http://www.gnu.org/licenses/>.
import os
import sys

import time

if not os.getpid() == 1:
    print("Nebula must be run as init.")
    sys.exit(22)
from collections import OrderedDict

__version__ = (0, 0, 1)

# Imports
import threading
import asyncio
import yaml
import logging
import logging.handlers
import subprocess
import shlex
import asyncio.log
import tqdm
import time
try:
    import setproctitle
except ImportError:
    print("Nebula - Setproctitle is not installed. Recommendation: install it.")
else:
    setproctitle.setproctitle("nebula")

import ctypes

# Load libc.
libc = ctypes.CDLL("libc.so.6")

def sync():
    libc.sync()

def reboot(arg):
    libc.reboot(arg)


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

# The process table is a master table for every process spawned by Nebula.
# It is key-value of service => list of processes spawned.
# This list consists of tuples with two values:
#  - the PID
#  - the subprocess object created by asyncio.
process_table = {}

# The unit table consists of a dictionary that maps the unit name to the YAML dictionary.
unit_table = OrderedDict()
enabled_unit_table = OrderedDict()

# Define a logger.
logger = logging.getLogger("nebula")
logger.setLevel(logging.DEBUG)

# Fuck up asyncio's logger
asyncio.log.logger.setLevel(99999)

logo = """ ______              _                 _
|  ___ \            | |               | |
| |   | |    ____   | | _     _   _   | |    ____
| |   | |   / _  )  | || \   | | | |  | |   / _  |
| |   | |  ( (/ /   | |_) )  | |_| |  | |  ( ( | |
|_|   |_|   \____)  |____/    \____|  |_|   \_||_|
                                                  """

# region logger
# Method for setting up logger.
# Called after mounting everything.
def setup_logger():
    if not os.path.exists("/var/log/nebula"):
        os.makedirs("/var/log/nebula")

    # Quick and dirty hack to fuck up logging easily.
    logging.addLevelName( logging.DEBUG, "\033[1;35m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
    logging.addLevelName( logging.INFO, "\033[1;32m%s\033[1;0m" % logging.getLevelName(logging.INFO))
    logging.addLevelName( logging.WARNING, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
    logging.addLevelName( logging.ERROR, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
    logging.addLevelName( logging.CRITICAL, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.CRITICAL))

    format = logging.Formatter("[%(levelname)s] - %(message)s")

    fh = logging.handlers.RotatingFileHandler("/var/log/nebula/nebula.log", maxBytes=(1048576*4), backupCount=7) # 4mb
    fh.setFormatter(format)
    logger.addHandler(fh)
# endregion

# Define a rescue function.
def rescue():
    print("Something bad happened - dropping to an emergency shell.")
    print("Exit this shell to continue.")
    subprocess.call(["/bin/sh"])

if not os.path.exists("/sbin/nebula.d/"):
    print("Nebula safety scripts cannot be found. Panicing.")
    rescue()
    sys.exit(22)


# Clear screen
print("\033c", end='')

print("Nebula version {} starting!".format('.'.join(map(str, __version__))))

# Run fstab.
ret = subprocess.call(["/sbin/nebula.d/fstab.py"])

# Mount tmpfs.
subprocess.call("mount -v -t tmpfs tmpfs /tmp".split())

# Remount root as read-write if we can.
print("Nebula - Remounting filesystem...")
try:
    subprocess.check_call("mount -v -o remount,rw /".split())
except subprocess.CalledProcessError:
    logger.error("Unable to remount root!")
    logger.error("Bailing out, you're on your own now.")
    rescue()

# Disable kernel messages.
subprocess.call("dmesg -n 1".split())

setup_logger()

# Begin initialization.
print("Early init completed - Starting nebula...")
# Check our cmdline.
with open("/proc/cmdline", 'r') as f:
    sp = f.read().split(' ')
    sp = [s.replace('\n', '') for s in sp]
    if 'rescue' in sp or 'nebula.rescue' in sp:
        rescue()

if not os.path.exists("/run/nebula"):
    os.makedirs("/run/nebula")

# region Setup

print("Setting hostname...")
with open("/etc/hostname", 'a+') as f:
    f.seek(0)
    data = f.read().replace('\n', '')
    subprocess.call(["hostname", data])

print("Setting vconsole...")
subprocess.call(["/sbin/nebula.d/vconsole.py"])

# endregion

print("Loading unit files...")

def _reraise(err):
    raise err

def load_unit_files():
    error = False
    # Scandir items in /etc/nebula/enabled
    if not os.path.exists("/etc/nebula/enabled"):
        os.makedirs("/etc/nebula/enabled")
    items = sorted(os.scandir("/etc/nebula"), key=lambda x:x.name)
    for item in tqdm.tqdm(items):
        if not item.name.endswith(".yml"):
            continue
        logger.debug("Loading unit file {}".format(item.name))
        with open(item.path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except Exception as e:
                logger.error("Unable to load file {}: {}".format(item.name, e))
                error = True
                continue
        try:
            unit_table[data["name"]] = data
            if os.path.exists("/etc/nebula/enabled/{}".format(item.name)):
                enabled_unit_table[data["name"]] = data
        except KeyError:
            logger.error("Unit file {} does not have a name specified!".format(item.name))
    if error:
        print("Some unit files failed to load.")

# Try and load unit files.
try:
    load_unit_files()
except FileNotFoundError:
    logger.error("Cannot find unit files!")
    rescue()


async def run_unit(commands, wait, name) -> list:
    processes = []
    failed = False
    tq = tqdm.tqdm(total=len(commands), nested=True, mininterval=0.0001)
    for command in commands:
        tq.set_description(command.split(" ")[0])
        # Spawn a new asyncio Process.
        logger.debug("Running command: {}".format(command))
        proc = await asyncio.create_subprocess_exec(*command.split(" "))
        if wait:
            exitstatus = await proc.wait()
            if exitstatus != 0:
                logger.error("Command '{}' for unit {} failed with error code {}.".format(command, name, ret))
                failed = True
                break
        tq.update(1)
        time.sleep(0.005)
        if failed:
            break
        else:
            # Setup the table
            processes.append((proc.pid, proc))
    tq.close()
    time.sleep(0.005)
    return processes, failed

# Begin running units.
async def run_units():
    any_failed = False
    # Complex logic!
    tq = tqdm.tqdm(enabled_unit_table)
    for name, data in enabled_unit_table.items():
        tq.set_description(name)
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
            any_failed = True
        else:
            logger.info("Started unit {}".format(name))
            process_table[name] = processes
        tq.update(1)
        # Blocking sleep because asyncio fucks with tqdm
        time.sleep(0.005)
    # Don't remove the pretty progress bar.
    #tq.close()
    if any_failed:
        print("Some units failed to start properly. See the log file for more information.")


# Define a callback handler for the unix socket.
async def connection_cb(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    # Get data from the client.
    data = await reader.read().decode()
    # Because we're lazy, this is a plain text format.
    data = shlex.split(data)
    # Branch by command.
    if data[0] == "start":
        # Start a unit.
        if len(data) < 2:
            # Go fuck yourself
            return
        unit = data[1]
        if not unit in unit_table:
            # What are you doing
            return
        udata = unit_table[unit]
        cmds = udata['commands']
        start_commands = cmds.get("start")


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

    print("\033c", end='')
    print(logo)

    print("Bringing system online...")
    await run_units()
    # Spawn agetty on tty1.
    await asyncio.create_subprocess_exec("/usr/bin/agetty", "--noclear", "tty1", "38400", "linux")


# Begin Nebula daemon.
loop.create_task(main())
try:
    loop.run_forever()
except KeyboardInterrupt:
    loop.stop()
loop.close()