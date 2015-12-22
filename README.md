## Nebula - An Alternative Init System

*Nebula* is an alternative PID 1 daemon inspired by the likes of sysvinit. It is written in Python 3 and is designed 
with a single-file architecture in mind.


 - [Requirements](#requirements)
 - [Setup](#setup)

### Requirements

Nebula's only requirements are Python >=3.5 and PyYAML. It can be run on any Linux system that meets these requirements
. However, your system will be nigh-useless with just these.

There are some recommended requirements:

 - `eudev` allows you to actually manage your system's devices.
 - A `getty` such as `agetty` allows you to login to your system.


### Setup

Nebula has a very simple setup:

 1. Install Python 3. This has to be Python 3.5 or above, due to the async features used.
 2. Install PyYAML. Yaml is used for the unit files as a simple human-readable syntax.
 3. Install your unit files into /etc/nebula. 
 4. Install nebula.py and nebi.py into /sbin/init and /sbin/nebi respectively.
