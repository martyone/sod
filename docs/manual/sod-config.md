<!-- Automatically generated with dumpdocs.sh -- DO NOT EDIT!!! -->
<pre>
Usage: sod config [OPTIONS] [NAME[=[VALUE]]]

  Show or set configuration options.

  When invoked without argument, list all options with their values. When
  invoked with NAME only, show the particular option value.  When just the
  VALUE is omitted, clear the option value. Otherwise assign the VALUE.

  The list of configuration options follows:

  snapshot.command STRING

      Use the command STRING as a system command to automatically create a
      file system snapshot whenever a new content is comitted (new files
      added or existing modified). The command STRING will be executed as is
      in a subshell.

Options:
  --help  Show this message and exit.
</pre>
