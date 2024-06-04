<!-- Automatically generated with dumpdocs.sh -- DO NOT EDIT!!! -->
<pre>
Usage: sod diff [OPTIONS] OLD_COMMIT [NEW_COMMIT]

  Show differences between two commits. New commit defaults to 'HEAD'.

  When '--raw' is used, the output format is:

  STATUS_LETTER ' ' OLD_DIGEST '&lt;TAB&gt;' OLD_PATH ['&lt;TAB&gt;' NEW_PATH] '&lt;LF&gt;'

  When '--raw' and '--null-terminated' is used, the output format is:

  STATUS_LETTER ' ' OLD_DIGEST '&lt;NUL&gt;' OLD_PATH ['&lt;NUL&gt;' NEW_PATH] '&lt;NUL&gt;'

  Possible STATUS_LETTER is any of the letters the '--filter' option accepts.

Options:
  --abbrev / --no-abbrev  Abbreviate old content digest
  --raw                   Output in a format suitable for parsing. Implies '--
                          no-abbrev'.
  --null-terminated       Use NULs as output fields terminators. Implies '--
                          raw'.
  --filter TEXT           Limit output to files that were Added (A), Copied
                          (C), Deleted (D), Modified (M) or Renamed (R).
                          Multiple filter characters may be passed.  Pass
                          lower-case characters to select the complement.
  --rename-limit INTEGER  Maximum number of file renames to try to detect
  --help                  Show this message and exit.
</pre>
