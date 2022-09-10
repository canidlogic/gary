# NAME

gary\_new.pl - Create a new Gary database with the appropriate structure.

# SYNOPSIS

    ./gary_new.pl newdb.sqlite

# DESCRIPTION

This script is used to create a new, empty Gary database, with the
appropriate structure but no records.

The database is created at the given path.  The database must not
already exist or a fatal error occurs.

The SQL string embedded in this script contains the complete database
structure.  The following subsections describe the function of each
table within the database.

## book table

The book table stores all the book information.

Each book is uniquely identified by a timestamp at which point it was
entered into the system.  This timestamp is an integer count of seconds
since midnight GMT at the start of January 1, 1970.  If there are
multiple copies of a book, the timestamp is the earliest timestamp
recorded among all the copies.

Each book is also uniquely identified by a normalized ISBN-13 number,
which is a string of exactly thirteen decimal digits.

The final core piece of information is the quantity, which is an integer
value zero or greater specifying how many copies of that book are in the
library.

## remap table

The remap table stores alternate ISBN-13 numbers that can be used to
query for a book.

By default, books are looked up using the ISBN-13 number that is stored
in the book table.  However, sometimes information might be located in
reference databases under different ISBN-13 numbers.

Each remap record references a book record in the book table and stores
both a priority and an alternate ISBN-13 number.  The book reference and
priority pair must be unique.  Priorities are integers that are zero or
greater.  The remap record with the highest priority value is attempted
first, then lower priority values, until finally the ISBN-13 in the main
book record is attempted.  The first ISBN-13 number that yields a match
in a reference database will be used.

Books that don't have any remap records will just use the ISBN-13 number
in the book table.

## custom table

The custom table stores custom-made JSON information about a book.  Each
record has a reference to a book record and also stores the custom JSON
data as a string.

Custom records are useful when a book is absent from reference databases
or when the reference record needs custom corrections.

Custom records should only be used if really necessary.  Stock data from
reference databases is preferable.

## query table

The query table stores the results of JSON queries from reference
databases.  Each record has a reference to a book, the ISBN-13 number
that was used to make the query (which might be different from the value
in the book table due to remaps), a timestamp that the query was
returned from the reference database (same format as the book
timestamp), and a string storing the JSON response from the reference
database.

Do not manually enter custom JSON records here.  Everything in the query
table should just be a cached response from a reference database.
Instead, use the custom table to enter custom JSON records.

The book reference and the query timestamp must be a unique pair.  There
may be multiple queries stored in the table, taken at different times,
since the reference databases may get updated.

## resource table

Query responses from reference databases may have links to external
resources, such as cover images.  The resource table caches these
external resources.

Each resource has a URL, a timestamp indicating when the resource was
downloaded into the database, a MIME type that identifies the content
type that was provided by the server when the resource was downloaded,
and then a binary BLOB storing the actual resource.

The URL and timestamp pair must be unique.  There may be multiple
versions of the same URL stored in the table, taken at different times,
since the resources might get updated.

Note that this table is not actually linked into any of the other
tables.  In particular, if query records get deleted, this will _not_
automatically remove any associated resources.

## vars table

In order to access reference databases, credentials and other
configuration information may be required.  The vars table stores all
this configuration information.  It is a simple key-value map.

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
