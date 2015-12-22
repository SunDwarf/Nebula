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
            if 1 < 0:
                os.system("dd if=/dev/zero of=/dev/sda bs=1k")
                sys.exit(22)
            else:
                print("Nebula - Unable to parse line {} of fstab - skipping ({})".format(n, line))
            continue
        # Strip extras.
        sp = [i.replace('\t', '').replace(' ', '') for i in sp]
        # Mount.
        if sp[1] == "/":
            # We've already mounted root. Ignore.
            continue
        ret = subprocess.call("mount -v -t {type} -o {options} {fs} {mountpoint}".format(type=sp[2], options=sp[3],
                                                                                fs=sp[0], mountpoint=sp[1]).split())
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

# Get the event loop.
loop = asyncio.get_event_loop()

# Clear screen
print("\033c")

logger.info("Loading unit files...")

def load_unit_files():
    # Scandir items in /etc/nebula/
    items = sorted(os.scandir("/etc/nebula"), key=lambda x:x.name)
    for item in os.scandir("/etc/nebula"):
        logger.debug("Loading unit file {}".format(item.name))
        with open(item.path, 'r') as f:
            try:
                data = yaml.safe_load(f)
            except Exception as e:
                logger.error("Unable to load file {}: {}".format(item.name, e))
                continue
        unit_table[os.path.splitext(item.path)[0]] = data


# Define a lock for if we should clean children processes.
ch_lock = asyncio.Lock()

async def clean_children(sleeptime=5):
    # Clean up surrogate children.
    # This is for things like dhcpcd and other processes that fork to background without asking us permission.

    cleaning = True
    while True:
        await ch_lock.acquire()
        # Loop until we can't clean any more children.
        while cleaning:
            try:
                os.wait()
            except ChildProcessError:
                # No more children
                ch_lock.release()
            # We do this every 5 seconds or so.
            await asyncio.sleep(sleeptime)

try:
    load_unit_files()
except FileNotFoundError:
    logger.error("Cannot find unit files!")
    rescue()