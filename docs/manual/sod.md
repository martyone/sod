<!-- Automatically generated with dumpdocs.sh -- DO NOT EDIT!!! -->
<pre>
Usage: sod [OPTIONS] COMMAND [ARGS]...

  sod - a digest tracker

  Sod is a special-purpose revision control system focused on efficient and
  transparent large file support at the cost of limited rollback ability.

  Motto: What are backups for if you do not review what you back up?

  In contrast to total data loss, partial data loss or corruption as the
  possible result of incidents ranging from user errors to data degradation
  (bit rot) easily goes unnoticed long enough to propagate into backups and
  eventually destroy the last available copy of the original data.

  Protecting data integrity using conventional means is not always feasible.
  Consider a large collection of binary files like media files maintained on a
  laptop.  Available storage may be too limited for RAID implementation.
  Similar is the situation with conventional revision control systems, which
  usually keep a pristine copy of each managed file, and those that don't may
  store repository files primarily in a private area and expose them using
  (symbolic) links, breaking transparency.  Detecting changes by comparing
  data to (remote) backups may be too slow for regular use and backups may not
  be always accessible.

  Sod approaches this by tracking nothing but cryptographic digests of the
  actual data (Efficient), keeping the actual data intact (Transparent) and
  relying on auxiliary data stores for rollback purposes (Limited rollback).

  Sod is meant for single-user, single-history use - it provides no means of
  replicating history between repositories or maintaining alternate histories
  (Special-purpose).

  INITIALIZATION

  Sod repository can be initialized with the 'sod init' command executed under
  an existing directory.  Sod will store its data under a subdirectory named
  '.sod'.  Initially, a Sod repository has no history.  Any pre-existing files
  found under the repository at initialization time are treated equally as
  files appearing later after initialization.

  RECORDING CHANGES

  Changes since the last commit, as well as the initially untracked content
  under a freshly initialized repository, can be listed with the 'sod status'
  command.

  Recording changes is a two phase process.  First the changes to be recorded
  with the next commit are prepared (staged) with the 'sod add' command.
  Changes can be added step-by-step with multiple 'sod add' invocations and
  any change previously staged can be unstaged with the 'sod reset' command
  during this preparation phase.  The 'sod status' command lists changes that
  are staged for next commit separately from those that are not staged.

  Once finished, the staged changes can be recorded with the 'sod commit'
  command.  All commits in repository history can be listed with the 'sod log'
  command.

  UNDOING CHANGES

  If a particular revision of a file is to be restored, the digest recorded by
  Sod can be used to locate an exact copy of that file revision e.g. on a
  backup.  Sod can assist that with the 'sod restore' command, accompanied by
  the 'sod aux' group of commands for management of the so called auxiliary
  data stores, the possible sources of older file revisions.

  An auxiliary data store provides one or more snapshots of the original Sod
  repository together with an information on which revision the snapshot was
  taken at (or more correctly "taken after" - a snapshot taken while
  uncommitted changes existed does not fully match the said revision).

  In the output of the 'sod log' command, each revision with snapshots
  available is annotated with the snapshots listed as '&lt;aux-name&gt;[/&lt;snapshot-
  id&gt;]', omitting the optional part for stores providing just single snapshot.

  The simplest form of an auxiliary data store is a plain copy of the original
  Sod repository. It may be a local copy or a remote one, in the latter case
  accessed via SSH. Use 'sox aux add --help-types' to learn about the possible
  auxiliary data store types.

  The 'snapshot.command' configuration option can be used to let Sod trigger
  snapshot creation automatically whenever a new content is committed. See the
  'sod config' and 'sod commit' commands for more information.

  IGNORED PATHS

  Sod automatically ignores any directory that looks like a Git repository,
  SVN repository or snapper's snapshot directory. Additionally, any directory
  which contains a file named '.sodignore' is ignored. Ignoring individual
  files is not possible. Use the 'sod status --ignored' command to see the
  list of ignored files.

Options:
  --debug  Enable debugging output
  --help   Show this message and exit.

Commands:
  <a href="sod-add.md">add</a>      Stage changes for recording with next commit.
  <a href="sod-aux.md">aux</a>      Manage auxiliary data stores.
  <a href="sod-commit.md">commit</a>   Record changes to the repository.
  <a href="sod-config.md">config</a>   Show or set configuration options.
  <a href="sod-diff.md">diff</a>     Show differences between two commits.
  <a href="sod-init.md">init</a>     Initialize a sod repository under the current working directory.
  <a href="sod-log.md">log</a>      Show commit log.
  <a href="sod-reset.md">reset</a>    Reset changes staged for recording with next commit.
  <a href="sod-restore.md">restore</a>  Restore data from an auxiliary data store.
  <a href="sod-status.md">status</a>   Summarize changes since last commit.
</pre>
