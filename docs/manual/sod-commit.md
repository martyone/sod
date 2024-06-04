<!-- Automatically generated with dumpdocs.sh -- DO NOT EDIT!!! -->
<pre>
Usage: sod commit [OPTIONS]

  Record changes to the repository.

  When the 'snapshot.command' configuration option is set and the changes
  staged for this commit introduce a new content (new files added or existing
  modified), the shell command denoted by the 'snapshot.command' configuration
  option will be executed unless the '--no-snapshot' option is passed.

Options:
  -m, --message TEXT  Commit message
  --no-snapshot       Suppress automatic snapshot creation
  --help              Show this message and exit.
</pre>
