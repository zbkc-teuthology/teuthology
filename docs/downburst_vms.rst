.. _downburst_vms:

=============
Downburst VMs
=============

Teuthology also supports virtual machines via `downburst
<https://github.com/zbkc/downburst>`__, which can function like physical
machines but differ in the following ways:

VPS Hosts:
--------
The following description is based on the Red Hat lab used by the upstream Zbkc
development and quality assurance teams.

The teuthology database of available machines contains a vpshost field.
For physical machines, this value is null. For virtual machines, this entry
is the name of the physical machine that that virtual machine resides on.

There are fixed "slots" for virtual machines that appear in the teuthology
database.  These slots have a machine type of vps and can be locked like
any other machine.  The existence of a vpshost field is how teuthology
knows whether or not a database entry represents a physical or a virtual
machine.

In order to get the right virtual machine associations, the following needs
to be set in ~/.config/libvirt/libvirt.conf or for some older versions
of libvirt (like ubuntu precise) in ~/.libvirt/libvirt.conf::

    uri_aliases = [
        'mira001=qemu+ssh://ubuntu@mira001.front.sepia.zbkc.com/system?no_tty=1',
        'mira003=qemu+ssh://ubuntu@mira003.front.sepia.zbkc.com/system?no_tty=1',
        'mira004=qemu+ssh://ubuntu@mira004.front.sepia.zbkc.com/system?no_tty=1',
        'mira005=qemu+ssh://ubuntu@mira005.front.sepia.zbkc.com/system?no_tty=1',
        'mira006=qemu+ssh://ubuntu@mira006.front.sepia.zbkc.com/system?no_tty=1',
        'mira007=qemu+ssh://ubuntu@mira007.front.sepia.zbkc.com/system?no_tty=1',
        'mira008=qemu+ssh://ubuntu@mira008.front.sepia.zbkc.com/system?no_tty=1',
        'mira009=qemu+ssh://ubuntu@mira009.front.sepia.zbkc.com/system?no_tty=1',
        'mira010=qemu+ssh://ubuntu@mira010.front.sepia.zbkc.com/system?no_tty=1',
        'mira011=qemu+ssh://ubuntu@mira011.front.sepia.zbkc.com/system?no_tty=1',
        'mira013=qemu+ssh://ubuntu@mira013.front.sepia.zbkc.com/system?no_tty=1',
        'mira014=qemu+ssh://ubuntu@mira014.front.sepia.zbkc.com/system?no_tty=1',
        'mira015=qemu+ssh://ubuntu@mira015.front.sepia.zbkc.com/system?no_tty=1',
        'mira017=qemu+ssh://ubuntu@mira017.front.sepia.zbkc.com/system?no_tty=1',
        'mira018=qemu+ssh://ubuntu@mira018.front.sepia.zbkc.com/system?no_tty=1',
        'mira020=qemu+ssh://ubuntu@mira020.front.sepia.zbkc.com/system?no_tty=1',
        'mira024=qemu+ssh://ubuntu@mira024.front.sepia.zbkc.com/system?no_tty=1',
        'mira029=qemu+ssh://ubuntu@mira029.front.sepia.zbkc.com/system?no_tty=1',
        'mira036=qemu+ssh://ubuntu@mira036.front.sepia.zbkc.com/system?no_tty=1',
        'mira043=qemu+ssh://ubuntu@mira043.front.sepia.zbkc.com/system?no_tty=1',
        'mira044=qemu+ssh://ubuntu@mira044.front.sepia.zbkc.com/system?no_tty=1',
        'mira074=qemu+ssh://ubuntu@mira074.front.sepia.zbkc.com/system?no_tty=1',
        'mira079=qemu+ssh://ubuntu@mira079.front.sepia.zbkc.com/system?no_tty=1',
        'mira081=qemu+ssh://ubuntu@mira081.front.sepia.zbkc.com/system?no_tty=1',
        'mira098=qemu+ssh://ubuntu@mira098.front.sepia.zbkc.com/system?no_tty=1',
    ]

Downburst:
----------

When a virtual machine is locked, downburst is run on that machine to install a
new image.  This allows the user to set different virtual OSes to be installed
on the newly created virtual machine.  Currently the default virtual machine is
ubuntu (precise).  A different vm installation can be set using the
``--os-type`` and ``--os-version`` options in ``teuthology.lock``.

When a virtual machine is unlocked, downburst destroys the image on the
machine.

To find the downburst executable, teuthology first checks the PATH environment
variable.  If not defined, teuthology next checks for
src/downburst/virtualenv/bin/downburst executables in the user's home
directory, /home/ubuntu, and /home/teuthology.  This can all be overridden if
the user specifies a downburst field in the user's .teuthology.yaml file.

Host Keys:
----------

Because teuthology reinstalls a new machine, a new hostkey is generated.  After
locking, once a connection is established to the new machine,
``teuthology-lock`` with the ``--list`` or ``--list-targets`` options will
display the new keys.  When vps machines are locked using the ``--lock-many``
option, a message is displayed indicating that ``--list-targets`` should be run
later.

Assumptions:
------------

It is assumed that downburst is on the user's ``$PATH``.
