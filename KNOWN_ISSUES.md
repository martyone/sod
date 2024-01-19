# Known Issues

## Corner cases with file names including special characters

In some cases arguments of type file path are treated as glob patterns.

This happens e.g. when staging file removal. This behavior allows to stage
removal of multiple files matching a pattern. The files do not exist anymore on
the file system, so the shell path expansion provided by shell would be of no
help here. This may have some unwanted effects though, like when a file name
looks like a glob pattern and another file exists matched by the glob pattern.

Consider the following example where the 'foo1.txt' file is staged for deletion
accidentally:

    $ touch 'foo?.txt'
    $ sod add 'foo?.txt'
    $ touch 'foo1.txt'
    $ sod add 'foo1.txt'
    $ sod commit -m "Add ugly named files"
    $ rm 'foo?.txt'
    $ sod add 'foo?.txt'
    $ sod status
    Changes staged for commit:
      deleted:       da39a3ee5e  foo1.txt
      deleted:       da39a3ee5e  foo?.txt

    Changes not staged for commit:
      added:         -           foo1.txt

It is necessary to escape the special characters in the path passed to Sod in
this case:

    $ sod reset
    $ sod add 'foo\?.txt'
    $ sod status
    Changes staged for commit:
      deleted:       da39a3ee5e  foo?.txt

    Changes not staged for commit:

