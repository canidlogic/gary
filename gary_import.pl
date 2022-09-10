#!/usr/bin/env perl
use strict;
use warnings;

# Gary imports
use Gary::DB;

=head1 NAME

gary_import.pl - Import ZScan data into a Gary database.

=head1 SYNOPSIS

  ./gary_import.pl gary.sqlite zscan.sqlite

=head1 DESCRIPTION

This script is used to import books from a ZScan database into a Gary
database.

The first argument is the Gary database into which books will be
imported.  The second argument is the ZScan database to read the book
scanning information from.

=cut

# ==================
# Program entrypoint
# ==================

# Check that we got two arguments
#
($#ARGV == 1) or die "Expecting one database path argument, stopped";

# Get and check arguments
#
my $gary_path  = $ARGV[0];
my $zscan_path = $ARGV[1];

(-f $gary_path ) or die "Can't find file '$gary_path', stopped";
(-f $zscan_path) or die "Can't find file '$zscan_path', stopped";

# Open database connection to Gary database and attach ZScan database as
# schema "zscan"
#
my $dbc = Gary::DB->connect($gary_path, 0);
$dbc->attach($zscan_path, 'zscan');

# Begin r/w transaction and get handle
#
my $dbh = $dbc->beginWork('rw');

# Check that no timestamp in the Gary database book table matches any
# timestamp in the ZScan database
#
my $qr = $dbh->selectrow_arrayref(
  'SELECT t1.bookid '
  . 'FROM main.book AS t1, zscan.scan AS t2 '
  . 'WHERE t1.booktime = t2.scantime');
(not defined $qr) or
  die "ZScan timestamp already exists in Gary database, stopped";

# Check that no ISBN-13 in the Gary database book table matches any
# ISBN-13 in the ZScan database
#
$qr = $dbh->selectrow_arrayref(
  'SELECT t1.bookid '
  . 'FROM main.book AS t1, zscan.scan AS t2 '
  . 'WHERE t1.bookisbn = t2.scanisbn');
(not defined $qr) or
  die "ZScan ISBN-13 already exists in Gary database, stopped";

# Now import everything, aggregrating scanning rows into book records
#
$qr = $dbh->do(
  'INSERT INTO main.book (booktime, bookisbn, bookcount) '
  . 'SELECT '
  . 'min(t1.scantime) AS gscan, '
  . 't1.scanisbn, '
  . 'count(t1.scanid) AS gcount '
  . 'FROM zscan.scan AS t1 '
  . 'GROUP BY t1.scanisbn '
  . 'ORDER BY gscan ASC');

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
