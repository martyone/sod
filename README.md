# sod - a digest tracker

Sod is a special-purpose revision control system focused on efficient and transparent large file support at the cost of limited rollback ability.

Motto: What are backups for if you do not review what you back up?

In contrast to total data loss, partial data loss or corruption as the possible result of incidents ranging from user errors to data degradation (bit rot) easily goes unnoticed long enough to propagate into backups and eventually destroy the last available copy of the original data.

Protecting data integrity using conventional means is not always feasible.  Consider a large collection of binary files like media files maintained on a laptop.  Available storage may be too limited for RAID implementation.  Similar is the situation with conventional revision control systems, which usually keep a pristine copy of each managed file, and those that don't may store repository files primarily in a private area and expose them using (symbolic) links, breaking transparency.  Detecting changes by comparing data to (remote) backups may be too slow for regular use and backups may not be always accessible.

Sod approaches this by tracking nothing but cryptographic digests of the actual data (Efficient), keeping the actual data intact (Transparent) and relying on auxiliary data stores for rollback purposes (Limited rollback).

Sod is meant for single-user, single-history use - it provides no means of replicating history between repositories or maintaining alternate histories (Special-purpose).
