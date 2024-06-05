# sod - a digest tracker

Sod is a special-purpose revision control system focused on efficient and transparent large file support at the cost of limited rollback ability.

Motto: What are backups for if you do not review what you back up?

In contrast to total data loss, partial data loss or corruption as the possible result of incidents ranging from user errors to data degradation (bit rot) easily goes unnoticed long enough to propagate into backups and eventually destroy the last available copy of the original data.

Protecting data integrity using conventional means is not always feasible.  Consider a large collection of binary files like media files maintained on a laptop.  Available storage may be too limited for RAID implementation.  Similar is the situation with conventional revision control systems, which usually keep a pristine copy of each managed file, and those that don't may store repository files primarily in a private area and expose them using (symbolic) links, breaking transparency.  Detecting changes by comparing data to (remote) backups may be too slow for regular use and backups may not be always accessible.

Sod approaches this by tracking nothing but cryptographic digests of the actual data (Efficient), keeping the actual data intact (Transparent) and relying on auxiliary data stores for rollback purposes (Limited rollback).

Sod is meant for single-user, single-history use - it provides no means of replicating history between repositories or maintaining alternate histories (Special-purpose).

## Installation

Sod has been developed on GNU/Linux and its usability on other platforms has not been verified.

It can be installed directly from the source repository with the command

    pip install git+https://github.com/martyone/sod.git@master

## Usage

Sod is a command line tool. Its main usage resembles the usage of Git.

    sod --help

Check out the [snapshot of the built-in documentation](docs/manual/sod.md) produced by the above command.

## Example use case - maintaining a photo/video collection

Consider the `~/Pictures` directory as the root of a photo/video collection. The content of the collection is organized into albums represented by subdirectories of this directory.

New content is usually imported from the camera in three steps. First it is copied into the directory called "IMPORT", then the pictures are triaged - bad ones deleted - and at last they are moved to their final locations under albums.

Original pristine content from the camera is preserved. Metadata changes are kept in XMP sidecar files.

The collection is located on a BTRFS filesystem and the root directory actually is a BTRFS subvolume for which timeline snapshots are created when the content is touched. This is conveniently done with the help of the [snapper](http://snapper.io/) tool. The respective `snapper` configuration is named `pictures`.

The collection is backed up automatically to a remote machine with the help of [snap-sync](https://github.com/baod-rate/snap-sync). Occassionally a manual backup is done to an external harddrive with the help of `rsync` (cause it uses *another* filesystem).


### The issues

The maintainer of the collection has been worried about the following issues that are either not addressed or imposing an unacceptable maintenance overhead.

- Pictures may get lost unnoticed during triage or when moving to their final locations.
- Pictures may get corrupted or inadvertently modified and unwanted changes may propagate to backups unnoticed.
- When many pictures are moved unchanged (e.g. when albums are renamed), all the data must be copied again to the relatively slow external harddrive
- Remote backup with `snap-sync` handles renames effectively, but unfortunately
  - It failed irrecoverably whenever pictures/albums were moved around a lot (the send/receive feature of BTRFS is to be blamed).
  - The network connection to the remote machine is rather unreliable for `snap-sync` use.
- The consistency of backups cannot be easily verified

All of these and more can be addressed with Sod.


### First steps

Initialize a new Sod repository under the collection.

    $ cd ~/Pictures
    $ sod init

Record all the existing content with Sod (mind the trailing dot denoting the current working directory).

    $ sod add .
    $ sod commit -m "Initial commit"

Adding a new content to the repository is a lengthy process - be patient if your collection is big. All the data needs to be read from disk and cryptographic digests created.

Sod can be configured to automatically trigger BTRFS snapshot creation on commit. Do it now.

    $ sod config snapshot.command='snapper -c pictures create -c number'

### Importing new pictures

Connect your camera, copy new pictures into the `IMPORT` directory and record them with Sod.

    $ sod add IMPORT/
    $ sod commit -m "Import from camera"

You can verify with `snapper` that a snapshot has been created automatically. Since now all your pictures are safe and you can revert any changes to this recorded state as long as the corresponding BTRFS snapshot exists. How to do that with the help of Sod will be described further down.

    $ snapper -c pictures list

Triage the imported photos and move them to their final locations under albums using your favorite tools. After that, review the results with Sod.

    $ sod status

If everything looks good, record the changes.

    $ sod add .
    $ sod commit -m "Organize"

Provided that all you did this time was moving and removing files (no edits, copies or other means of introducing new data), no new snapshot should appear this time. Sod is able to track file moves, so it does not need to create a new snapshot in order to be able to restore a file on a new path in future.

    $ snapper -c pictures list


### Backing-up

Sod can be used in cooperation with good old `rsync` to deal efficiently with file renames when creating incremental backups to filesystems that lack the respective features of BTRFS. These two also perform well where `snap-sync` is available but fails for any of the earlier mentioned reasons.

Check out the [sod-redo-renames](examples/sod-redo-renames) tool that uses Sod to generate a shell script to re-do renames recorded earlier by Sod.

In the following example the backup will be initiated from the backup machine, reffered to as `backup` here. The backed-up machine is reachable via SSH under the name `source`. The `sod-redo-renames` tool is available on `PATH` on the backed-up machine. Sod does not need to be available on the backup machine - just a plain shell with `ssh` and `rsync` is needed there.

Enter the backup directory.

	$ cd /path/to/backup/of/Pictures

Determine the latest backed up Sod commit ID.

	$ SINCE=$(< .sod/refs/heads/master)

Generate the script to re-do renames since then.

	$ ssh source "cd ~/Pictures && sod-redo-renames '$SINCE'" >rename.sh

Review what would be done.

	$ less rename.sh

Re-do renames.

	$ bash rename.sh

Finally transfer other changes.

	$ rsync -av --delete source:Pictures/ .

Similarly can be performed backup to the external harddrive.


### Restoring files from backups

If a particular revision of a file needs to be restored, the digest recorded by Sod can be used to locate an exact copy of that file revision e.g. on a backup.  Sod can assist that with the `sod restore` command, accompanied by the `sod aux` group of commands for management of the so called auxiliary data stores, the possible sources of older file revisions.

Let sod know about your backups.  First of all register the local BTRFS snapshots. Mind the use of quotes to avoid shell expansion of the asterisk.

    $ sod aux add local "file://$HOME/Pictures/.snapshots/*/snapshot"

Then the remote backup (reachable via SSH under the name "remote").

    $ sod aux add remote "ssh://remote/path/to/backup/of/Pictures/*/snapshot"

And the backups on the harddrive too.

    $ sod aux add exthdd "file:///media/exthdd/backup/Pictures/*/snapshot"

Now update the cached information about these backups

    $ sod aux update --all

In the commit log, you can see commits annotated with the names of all corresponding snapshots (if any).

    $ sod log
    ...
    commit 60cbdf92b224b835d229ce1737eab3a83acc957e (local/180, remote/180)
    Date: Sun Dec 17 09:57:28 2023

        Import from camera

      added:         -           IMPORT/DSC_0667.JPG
      added:         -           IMPORT/DSC_0667.NEF
      added:         -           IMPORT/DSC_0668.JPG
    ...

In the easy case, the latest recorded revision of a file can be restored simply by giving its path. Sod will try to figure out itself which of the available snapshots provide it.

    $ sod restore IMPORT/DSC_0667.JPG


### Detecting data corruption

In order to speed up normal operations, Sod works with cached data digests. This way it can search for regular changes among hundreds of gigabytes of picture data in few seconds. In order to detect data corruption caused by silent disk errors or so, the caches must be baypassed. This is achieved with the `--rehash` option.

    sod status --rehash

This operation takes as long as an initial scan would do. All the data will be re-read from disk and cryptographic digests recreated - be patient.

This can be used equally for consistency checking of the backups. Just run Sod with current working directory under a backup tree.
