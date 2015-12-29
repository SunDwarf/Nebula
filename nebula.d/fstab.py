#!/usr/bin/env python3
#
# Mount file systems according to fstab.
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


# Load fstab.
import subprocess

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
