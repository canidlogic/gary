# NAME

Gary::ISBNdb - Query ISBNdb.

# SYNOPSIS

    use Gary::ISBNdb;
    
    # Prepare to query ISBNdb
    my $idb = Gary::ISBNdb->connect($dbc);
    
    # Query an ISBN-13 string of exactly 13 digits
    my $qr = $idb->query($isbn13);
    if (defined $qr) {
      # Successful query; $qr is Unicode string with JSON
      ...
    }

# DESCRIPTION

Module that queries the remote ISBNdb database for information about
books.

To construct an instance, use the `connect` function.  (Despite its
name, this function does not actually connect yet to the ISBNdb
database.)  The constructor requires a Gary database connection from
which the necessary configuration information can be read.  See the
constructor documentation for further information.

Once you have an instance, you can query books with the `query`
function.  This class will make sure the database is not queried too
frequently, according to limits established by the configuration
variables.  To make sure the request throttling is proper, you should
only use one instance to make a sequence of requests.

# CONSTRUCTOR

- **connect(dbc)**

    Construct a new ISBNdb query object.

    You must provide a connection to a Gary database.  This database
    connection is only used during this constructor to read the necessary
    configuration information from the `vars` table.

    The following configuration variables are required in the `vars` table.
    (Use the `gary_config.pl` script to set configuration variables in the
    database.)

    **isbndb\_book\_pattern** is a pattern used for deriving book query URLs.
    This should be a format string that can be used with `sprintf`.  A
    single format parameter will be provided, which is a string containing
    exactly 13 decimal digits and holding the ISBN-13 number to query for.
    Use `%s` in the pattern string at the place where you want the ISBN-13
    to be placed in queries.

    **isbndb\_rest\_key** is the API key to use to authorize requests to the
    ISBNdb service.  You must have an active subscription to ISBNdb to get
    this key.

    **isbndb\_interval** is the number of _microseconds_ that must elapse
    from the end of one request to the start of the next request.  Your
    ISBNdb subscription level determines how frequently you are able to
    query the database.  Must be an unsigned integer string that is greater
    than zero and at most 1999999999.  See the documentation of
    `isbndb_pause` below for further information.

    **isbndb\_pause** is the number of _microseconds_ that the script will
    sleep each time before checking again whether the interval has elapsed.
    When a query operation is requested, a check is made whether the time
    since the last query operation is at least `isbndb_interval`.  If so,
    the query proceeds.  If not, the script will keep sleeping by the amount
    of time specified by `isbndb_pause` until it detects that enough time
    has passed.  Must be an unsigned integer string that is greater than
    zero and at most 1999999999.

# INSTANCE METHODS

- **query(isbn13)**

    Query ISBNdb for a specific book.

    `isbn13` is a string containing exactly 13 decimal digits, representing
    an ISBN-13 number to look for.

    This method will throttle the number of queries according to the
    `isbndb_interval` and `isbndb_pause` configuration variables, as
    explained in the documentation for the constructor.  If this function is
    called but not enough time has passed since the last query (or since
    object construction if this is the first query), the script will block
    until enough time has passed.

    If the query is successful, the return value is the whole JSON response
    returned from ISBNdb, as a Unicode string.  Note that contrary to the
    documentation, the top-level response is a JSON object that has a
    `book` property, and it is _this_ property that has as its value the
    JSON attributes object of the book.

    If the query failed, `undef` is returned.  Note that ISBNdb is not very
    reliable, and queries that fail may succeed if retried later.  This
    function does _not_ perform any retries.

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
