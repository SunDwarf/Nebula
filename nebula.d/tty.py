#!/usr/bin/env python3
#
# Spawn a handler for getty.
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
import asyncio
import signal
import sys

tty = sys.argv[1]

loop = asyncio.get_event_loop()

async def _agetty(tty):
    # Just run in an infinite loop.
    # The wait will mean it won't spawn infinite agetty.
    while True:
        sub = await asyncio.create_subprocess_exec("/usr/bin/agetty", "--noclear", "tty{}".format(tty), "38400", "linux")
        await sub.wait()


fut = loop.create_task(_agetty(tty))

# Create kill callback
def _15(*args, **kwargs):
    fut.cancel()
    loop.stop()

loop.add_signal_handler(signal.SIGTERM, _15)
loop.run_forever()