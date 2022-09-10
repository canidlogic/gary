#!/usr/bin/env perl
use strict;
use warnings;

# Gary imports
use Gary::DB;
use Gary::ISBNdb;

=head1 NAME

gary_query.pl - Look up missing book information from ISBNdb.

=head1 SYNOPSIS

  ./gary_query.pl gary.sqlite

=head1 DESCRIPTION

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

=cut

# ==================
# Program entrypoint
# ==================

# Check that we got one argument
#
($#ARGV == 0) or die "Expecting one database path argument, stopped";

# Get and check argument
#
my $gary_path = $ARGV[0];
(-f $gary_path ) or die "Can't find file '$gary_path', stopped";

# Open database connection to Gary database
#
my $dbc = Gary::DB->connect($gary_path, 0);

# Add a temporary table that stores all the ISBN numbers we will need to
# query for, setting each of their flags to zero to begin with
#
my $dbh = $dbc->beginWork('rw');
$dbh->do(
  'CREATE TEMPORARY TABLE temp.pass ( '
  . 'passid   INTEGER PRIMARY KEY ASC, '
  . 'passbook INTEGER NOT NULL, '
  . 'passflag INTEGER NOT NULL )'
);
$dbh->do(
  'CREATE INDEX temp.ix_flag ON pass(passflag)'
);
$dbh->do(
  'CREATE INDEX temp.ix_book ON pass(passbook)'
);
$dbh->do(
  'INSERT INTO temp.pass AS t1 (passbook, passflag) '
  . 'SELECT t2.bookid, 0 '
  . 'FROM main.book AS t2 '
  . 'LEFT OUTER JOIN main.custom AS t3 ON t2.bookid = t3.bookid '
  . 'WHERE t3.customid ISNULL '
    . 'AND t2.bookid NOT IN (SELECT t4.bookid FROM query AS t4)'
);
$dbc->finishWork;

# Get an ISBNdb query object
#
my $idb = Gary::ISBNdb->connect($dbc);

# Now go through the whole pass, with one transaction per book
#
while(1) {
  # Begin transaction
  my $dh = $dbc->beginWork('rw');
  
  # Get a record from temp.pass that hasn't been handled yet
  my $qr = $dh->selectrow_arrayref(
            'SELECT passbook FROM temp.pass '
            . 'WHERE passflag = 0 '
            . 'ORDER BY passbook ASC');
  
  # If no more records remain, finish the transaction and leave the loop
  if (not defined $qr) {
    $dbc->finishWork;
    last;
  }
  
  # If we got here, then get the bookid we are handling this time around
  my $bookid = $qr->[0];
  
  # Now update the temp.pass table to set the flag on this book so we
  # won't try it again
  $dh->do(
    'UPDATE temp.pass SET passflag = 1 WHERE passbook = ?',
    undef,
    $bookid);
  
  # Start the ISBN query list empty
  my @isbnqa;
  
  # Add any remap ISBNs in order of priority
  $qr = $dh->selectall_arrayref(
          'SELECT remapisbn '
          . 'FROM remap '
          . 'WHERE bookid = ? '
          . 'ORDER BY remapord DESC',
          undef,
          $bookid);
  if (defined $qr) {
    for my $r (@$qr) {
      push @isbnqa, (Gary::DB->db_to_string($r->[0]));
    }
  }
  
  # Finally, add the ISBN number in the book record; also check here
  # that the book record is still defined; if it is not, then end
  # transaction and loop around again
  $qr = $dh->selectrow_arrayref(
          'SELECT bookisbn FROM book WHERE bookid = ?',
          undef,
          $bookid);
  if (not defined $qr) {
    # Book record got deleted in the meantime, so end transaction and
    # loop around again
    $dbc->finishWork;
    next;
  }
  
  push @isbnqa, ($qr->[0]);
  
  # We now know all the ISBN numbers we are querying for; the query may
  # take a while, so let's finish the transaction here
  $dbc->finishWork;
  
  # Go through the ISBN list and look for the first match
  my $result = undef;
  my $query_isbn = undef;
  
  for my $isbn (@isbnqa) {
    # Try to query for this ISBN number
    $result = $idb->query($isbn);
    if (defined $result) {
      $query_isbn = $isbn;
      last;
    }
  }
  
  # If query failed, then report this to output and loop to next element
  # in pass
  if (not defined $result) {
    print "Book $bookid FAILED!\n";
    next;
  }
  
  # We now got our query result, so start a transaction to update the
  # database again
  $dh = $dbc->beginWork('rw');
  
  # Check that the book is still defined in the database; if it is not,
  # finish transaction and loop around again, discarding the result we
  # just got
  $qr = $dh->selectrow_arrayref(
          'SELECT bookid FROM book WHERE bookid = ?',
          undef,
          $bookid);
  if (not defined $qr) {
    $dbc->finishWork;
    next;
  }
  
  # Get the current timestamp for use in the query record
  my $tstamp = int(time);
  
  # If query already defined for this timestamp and this book, then
  # finish transaction and loop around again, discarding the result we
  # just got
  $qr = $dh->selectrow_arrayref(
          'SELECT queryid FROM query WHERE bookid=? AND querytime=?',
          undef,
          $bookid, $tstamp);
  if (defined $qr) {
    $dbc->finishWork;
    next;
  }
  
  # We are now clear to store our result in the database
  $dh->do(
    'INSERT INTO query (bookid, queryisbn, querytime, querytxt) '
    . 'VALUES (?, ?, ?, ?)',
    undef,
    $bookid,
    Gary::DB->string_to_db($query_isbn),
    $tstamp,
    Gary::DB->string_to_db($result));
  
  # Finish updating database for this item
  $dbc->finishWork;
  
  # Report success
  print "Book $bookid found.\n";
}

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
