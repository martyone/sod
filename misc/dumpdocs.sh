#!/bin/bash
#
# Dump the built-in help for online viewing.

OUT_DIR=docs/manual

full_name=()
process_command()
{
	local name=$1

	full_name+=("$name")

	local help=
	help=$("${full_name[@]}" --help) || return

	local dashed_name=$(IFS=-; echo "${full_name[*]}")
	local ofile=$OUT_DIR/$dashed_name.md

	local inside_commands_section=

	{
		printf '<!-- Automatically generated with %s -- DO NOT EDIT!!! -->\n' \
			"$(basename "$0")"
		printf '<pre>\n'

		while IFS='' read line; do
			line=${line//</"&lt;"}
			line=${line//>/"&gt;"}

			if [[ $inside_commands_section ]]; then
				local sub_name= sub_description= sub_ofile=
				read sub_name sub_description <<<"$line"

				sub_ofile=$(process_command "$sub_name") || return

				local sub_link=$(printf '<a href="%s">%s</a>' \
					"$(basename "$sub_ofile")" \
					"$sub_name")

				line=${line/$sub_name/"$sub_link"}
				printf '%s\n' "$line"
				continue
			fi

			if [[ $line == Commands: ]]; then
				inside_commands_section=1
			fi

			printf '%s\n' "$line"
		done <<<"$help"

		printf '</pre>\n'
	} >"$ofile"

	printf '%s\n' "$ofile"
}

if [[ $* ]]; then
	printf '%s: Unexpected argument: %s\n' "$0" "$1" >&2
	exit 1
fi

mkdir -p "$OUT_DIR" || exit
process_command sod
