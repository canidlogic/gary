#!/usr/bin/env perl
use strict;
use warnings;

# Gary imports
use Gary::DB;

=head1 NAME

gary_new.pl - Create a new Gary database with the appropriate structure.

=head1 SYNOPSIS

  ./gary_new.pl newdb.sqlite

=head1 DESCRIPTION

This script is used to create a new, empty Gary database, with the
appropriate structure but no records.

The database is created at the given path.  The database must not
already exist or a fatal error occurs.

The SQL string embedded in this script contains the complete database
structure.  The following subsections describe the function of each
table within the database.

=head2 book table

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

=head2 remap table

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

=head2 custom table

The custom table stores custom-made JSON information about a book.  Each
record has a reference to a book record and also stores the custom JSON
data as a string.

Custom records are useful when a book is absent from reference databases
or when the reference record needs custom corrections.

Custom records should only be used if really necessary.  Stock data from
reference databases is preferable.

=head2 query table

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

=head2 resource table

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
tables.  In particular, if query records get deleted, this will I<not>
automatically remove any associated resources.

=head2 vars table

In order to access reference databases, credentials and other
configuration information may be required.  The vars table stores all
this configuration information.  It is a simple key-value map.

=cut

# Define a string holding the whole SQL script for creating the
# structure of the database, with semicolons used as the termination
# character for each statement and nowhere else
#
my $sql_script = q{

CREATE TABLE book (
  bookid    INTEGER PRIMARY KEY ASC,
  booktime  INTEGER UNIQUE NOT NULL,
  bookisbn  TEXT UNIQUE NOT NULL,
  bookcount INTEGER NOT NULL
);

CREATE UNIQUE INDEX ix_book_time
  ON book(booktime);

CREATE UNIQUE INDEX ix_book_isbn
  ON book(bookisbn);

CREATE TABLE remap (
  remapid   INTEGER PRIMARY KEY ASC,
  bookid    INTEGER NOT NULL,
  remapord  INTEGER NOT NULL,
  remapisbn TEXT NOT NULL,
  UNIQUE    (bookid, remapord)
);

CREATE UNIQUE INDEX ix_remap_rec
  ON remap(bookid, remapord);

CREATE INDEX ix_remap_book
  ON remap(bookid);

CREATE INDEX ix_remap_isbn
  ON remap(remapisbn);

CREATE TABLE custom (
  customid  INTEGER PRIMARY KEY ASC,
  bookid    INTEGER UNIQUE NOT NULL,
  customtxt TEXT NOT NULL
);

CREATE UNIQUE INDEX ix_custom_book
  ON custom(bookid);

CREATE TABLE query (
  queryid   INTEGER PRIMARY KEY ASC,
  bookid    INTEGER NOT NULL,
  queryisbn TEXT NOT NULL,
  querytime INTEGER NOT NULL,
  querytxt  TEXT NOT NULL,
  UNIQUE    (bookid, querytime)
);

CREATE UNIQUE INDEX ix_query_rec
  ON query(bookid, querytime);

CREATE INDEX ix_query_book
  ON query(bookid);

CREATE INDEX ix_query_time
  ON query(querytime);

CREATE TABLE resource (
  resourceid    INTEGER PRIMARY KEY ASC,
  resourceurl   TEXT NOT NULL,
  resourcetime  INTEGER NOT NULL,
  resourcemime  TEXT NOT NULL,
  resourceblob  BLOB NOT NULL,
  UNIQUE        (resourceurl, resourcetime)   
);

CREATE UNIQUE INDEX ix_resource_rec
  ON resource(resourceurl, resourcetime);

CREATE INDEX ix_resource_url
  ON resource(resourceurl);

CREATE INDEX ix_resource_time
  ON resource(resourcetime);

CREATE INDEX ix_resource_mime
  ON resource(resourcemime);

CREATE TABLE vars (
  varsid    INTEGER PRIMARY KEY ASC,
  varskey   TEXT UNIQUE NOT NULL,
  varsval   TEXT NOT NULL
);

CREATE UNIQUE INDEX ix_vars_key
  ON vars(varskey);

};

# ==================
# Program entrypoint
# ==================

# Check that we got one arguments
#
($#ARGV == 0) or die "Expecting one database path argument, stopped";

# Open database connection to a new database
#
my $dbc = Gary::DB->connect($ARGV[0], 1);

# Begin r/w transaction and get handle
#
my $dbh = $dbc->beginWork('rw');

# Parse our SQL script into a sequence of statements, each ending with
# a semicolon
#
my @sql_list;
@sql_list = $sql_script =~ m/(.*?);/gs
  or die "Failed to parse SQL script, stopped";

# Run all the SQL statements needed to build the the database structure
#
for my $sql (@sql_list) {
  $dbh->do($sql);
}
  
# Commit the transaction
#
$dbc->finishWork;

=head1 AUTHOR

Noah Johnson, C<noah.johnson@loupmail.com>

=head1 COPYRIGHT AND LICENSE

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

=cut
