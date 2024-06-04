#!/bin/bash

last_modified_from_git()
{
	local file=$1
	git log -1 --date='format:%Y' --pretty='format:%ad' "$file"
}

grep -i -e 'copyright (c)' $(git ls-files) -l \
	|while read file; do
		year=$(last_modified_from_git "$file")
		sed -i -e "/copyright (c) 20/I s/202[0-9,-]\+/$year/" "$file"
	done
