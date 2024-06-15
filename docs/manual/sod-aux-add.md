<!-- Automatically generated with dumpdocs.sh -- DO NOT EDIT!!! -->
<pre>
Usage: sod aux add [OPTIONS] NAME URL

  Add an auxiliary data store.

  Available types:

      plain

          A plain copy of the original Sod repository. It may be a local copy
          or a remote one, in the latter case accessed via SSH.

          Examples:

              sod add --type plain local 'file:///path/to/backup'
              sod add --type plain remote 'ssh://backup.local/path/to/backup'

          Single store may provide multiple snapshots of the original Sod
          repository, stored as a set of adjacent directories. For that case
          it is possible to use single '*' (asterisk) wildcard character
          anywhere in the path component of the URL to denote the whole group
          of snapshots.

          Example: the 'snapper' tool creates snapshots under the
          '.snapshots' subdirectory of the repository. The following command
          can be used to register these.

              sod add --type plain local \
                  'file:///path/to/my/repo/.snapshots/*/snapshot'

          Example: the 'snap-sync' tool can be used to copy the snapshots
          created by 'snapper' to another machine. The following command can
          be used to register these.

              sod add --type plain remote \
                  'ssh://backup.local/path/to/my/backup/*/snapshot'

Options:
  --type TYPE  Store type
  --help       Show this message and exit.
</pre>
