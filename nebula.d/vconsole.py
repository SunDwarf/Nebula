#!/usr/bin/env python3
#
# Set tty font.
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


import subprocess


def parse_bash(lines: list) -> dict:
    d = {}
    for l in lines:
        l = l.rstrip('\n')
        sp = l.split("=")
        if len(sp) != 2:
            continue
        d[sp[0]] = sp[1]
    return d

with open("/etc/vconsole.conf", 'a+') as f:
    f.seek(0)
    data = f.read()
    if data:
        data = parse_bash(data.split('\n'))
        # Call the appropriate commands.
        if 'FONT' in data:
            subprocess.call(["setfont", data['FONT']])
        if 'KEYMAP' in data:
            subprocess.call(["loadkeys", data['KEYMAP']])