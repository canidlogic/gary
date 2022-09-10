# NAME

gary\_query.pl - Look up missing book information from ISBNdb.

# SYNOPSIS

    ./gary_query.pl gary.sqlite

# DESCRIPTION

This script performs one pass through a database for every book that
does not yet have any entry in the custom or query tables.

For each of these books, the script will generate a list of ISBN-13
numbers to query for the book, using the remap table.  Then, each of the
ISBN-13 numbers will be tried in order of priority until a successful
result is found in ISBNdb for the book.  If no successful result is
found, the script moves on to the next book in the pass.

This script does not download any associated resource files, such as
cover images.

You must have database configuration variables set up appropriately so
that Gary::ISBNdb can work.

Each book query is handled in its own transaction, so if the script is
interrupted, books that were already queried should remain in the
database.

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
