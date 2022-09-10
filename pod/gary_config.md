# NAME

gary\_config.pl - Set the configuration variables in a Gary database.

# SYNOPSIS

    ./gary_config.pl gary.sqlite config.txt

# DESCRIPTION

This script is used to set configuration variables in the `vars` table
of the given Gary database.

Since the content of these variables might contain sensitive credentials
for accessing reference databases, the data is read from a text file so
that no record of the values is written to the console log.

The first argument is the Gary database to configure.  The second
argument is the path to a text file to use to configure the database.
See below for the format of the text file.

## Configuration file format

The configuration file is a UTF-8 plain-text file.  Line breaks may be
LF or CR+LF, and there may be an optional UTF-8 Byte Order Mark (BOM) at
the start of the file.

Each line is either blank, or a comment, or a record.  Blank lines are
either empty or contain only whitespace.  Comment lines begin
immediately with a `#` character.  Record lines begin immediately with
a US-ASCII alphabetic or underscore character.

Blank lines and comment lines are ignored.

Record lines must have the following format:

    1. Variable name
    2. Equals sign
    3. Variable value

The variable name may be any sequence of one or more US-ASCII
alphanumerics and underscores, with the only limitation being that the
first character must be alphabetic or underscore and the length of the
variable name must be in range \[1, 31\].

No whitespace is allowed to preceded or follow the equals sign, unless
the value is an empty string, in which case whitespace might follow the
equals sign.

The variable value may be any sequence of Unicode characters.  The
record line is trimmed of trailing whitespace, so it is not possible for
the variable value to end in a whitespace character.  If there is
nothing after the equals sign except possibly for whitespace characters,
then the value will be an empty string.

Record lines are processed in the order they appear in the configuration
file.  A record line is processed by either adding a new configuration
variable if one with the given name does not already exist or else
updating the value of an existing configuration variable, overwriting
the current value with the new one.

# AUTHOR

Noah Johnson, `noah.johnson@loupmail.com`

# COPYRIGHT AND LICENSE

Copyright (C) 2022 Multimedia Data Technology Inc.

MIT License:

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files
(the "Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
