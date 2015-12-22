#!/usr/bin/env bash
#
# /usr/lib/initscripts/arch-modules
#
# Configure kernel modules to load at boot following
# http://0pointer.de/public/systemd-man/modules-load.d.html
#

shopt -s nullglob

declare -a modules_d
# files given has argv supersede config files
if (( $# > 0 )); then
	for arg; do [[ -r "$arg" ]] && modules_d+=("$arg"); done
else
	modules_d=(
		/usr/lib/modules-load.d/*.conf
		/etc/modules-load.d/*.conf
		/run/modules-load.d/*.conf
	)
fi

# check there is file to load
(( ${#modules_d[@]} > 0 )) || exit 0

# files declared later in the modules_d array will override earlier
# Example: `/etc/modules-load.d/foo.conf' supersedes `/usr/lib/modules-load.d/foo.conf'.
declare -A fragments
for path in "${modules_d[@]}"; do
	[[ -f $path ]] && fragments[${path##*/}]=$path
done

for path in "${fragments[@]}"; do
	while read -r line; do
		[[ ${line:0:1} == [\#\;] ]] && continue
		modprobe -ab "$line"
	done < "$path"
done

:

# vim: set ts=2 sw=2 noet: