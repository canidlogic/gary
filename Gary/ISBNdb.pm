package Gary::ISBNdb;
use strict;

# Gary imports
use Gary::DB;

# ======================================================================
# IMPORTANT:  Also need to install LWP::Protocol::https in order to get
# HTTPS access!  This in turn depends on Net::SSLeay.  Installation of
# the Net::SSLeay package may fail unless you have installed the
# *development* package for libssl on your machine.  Install libssl
# development package before attempting to get LWP::Protocol::https
# ======================================================================

# Non-core imports
use HTTP::Request;
use JSON::Tiny qw( decode_json );
use LWP::UserAgent;

# Core imports
use Time::HiRes qw( usleep gettimeofday );

=head1 NAME

Gary::ISBNdb - Query ISBNdb.

=head1 SYNOPSIS

  use Gary::ISBNdb;
  
  # Prepare to query ISBNdb
  my $idb = Gary::ISBNdb->connect($dbc);
  
  # Query an ISBN-13 string of exactly 13 digits
  my $qr = $idb->query($isbn13);
  if (defined $qr) {
    # Successful query; $qr is Unicode string with JSON
    ...
  }

=head1 DESCRIPTION

Module that queries the remote ISBNdb database for information about
books.

To construct an instance, use the C<connect> function.  (Despite its
name, this function does not actually connect yet to the ISBNdb
database.)  The constructor requires a Gary database connection from
which the necessary configuration information can be read.  See the
constructor documentation for further information.

Once you have an instance, you can query books with the C<query>
function.  This class will make sure the database is not queried too
frequently, according to limits established by the configuration
variables.  To make sure the request throttling is proper, you should
only use one instance to make a sequence of requests.

=head1 CONSTRUCTOR

=over 4

=item B<connect(dbc)>

Construct a new ISBNdb query object.

You must provide a connection to a Gary database.  This database
connection is only used during this constructor to read the necessary
configuration information from the C<vars> table.

The following configuration variables are required in the C<vars> table.
(Use the C<gary_config.pl> script to set configuration variables in the
database.)

B<isbndb_book_pattern> is a pattern used for deriving book query URLs.
This should be a format string that can be used with C<sprintf>.  A
single format parameter will be provided, which is a string containing
exactly 13 decimal digits and holding the ISBN-13 number to query for.
Use C<%s> in the pattern string at the place where you want the ISBN-13
to be placed in queries.

B<isbndb_rest_key> is the API key to use to authorize requests to the
ISBNdb service.  You must have an active subscription to ISBNdb to get
this key.

B<isbndb_interval> is the number of I<microseconds> that must elapse
from the end of one request to the start of the next request.  Your
ISBNdb subscription level determines how frequently you are able to
query the database.  Must be an unsigned integer string that is greater
than zero and at most 1999999999.  See the documentation of
C<isbndb_pause> below for further information.

B<isbndb_pause> is the number of I<microseconds> that the script will
sleep each time before checking again whether the interval has elapsed.
When a query operation is requested, a check is made whether the time
since the last query operation is at least C<isbndb_interval>.  If so,
the query proceeds.  If not, the script will keep sleeping by the amount
of time specified by C<isbndb_pause> until it detects that enough time
has passed.  Must be an unsigned integer string that is greater than
zero and at most 1999999999.

=cut

sub connect {
  
  # Check parameter count
  ($#_ == 1) or die "Wrong number of parameters, stopped";
  
  # Get invocant and parameters
  my $invocant = shift;
  my $class = ref($invocant) || $invocant;
  
  my $dbc = shift;
  
  (ref($dbc) and $dbc->isa("Gary::DB")) or
    die "Wrong parameter type, stopped";
  
  # Start read operation
  my $dbh = $dbc->beginWork('r');
  
  # Get all the ISBNdb configuration variables
  my $qr = $dbh->selectall_arrayref(
    "SELECT varskey, varsval FROM vars WHERE varskey GLOB 'isbndb_*'");
  my %cvars;
  if (defined $qr) {
    for my $r (@$qr) {
      $cvars{Gary::DB->db_to_string($r->[0])} = 
        Gary::DB->db_to_string($r->[1]);
    }
  }
  
  # Finish read operation
  $dbc->finishWork;
  
  # Check we got the necessary configuration variables
  for my $vname ('isbndb_book_pattern', 'isbndb_rest_key',
                  'isbndb_interval', 'isbndb_pause') {
    (defined $cvars{$vname}) or
      die "Missing database configuration variable '$vname', stopped"; 
  }
  
  # Get the relevant configuration variables
  my $book_pattern = $cvars{'isbndb_book_pattern'};
  my $rest_key     = $cvars{'isbndb_rest_key'    };
  my $interval     = $cvars{'isbndb_interval'    };
  my $pause        = $cvars{'isbndb_pause'       };
  
  # Convert the integer variables to integer
  for(my $x = 0; $x < 2; $x++) {
    # Get relevant variable
    my $str;
    my $vname;
    
    if ($x == 0) {
      $str = $interval;
      $vname = 'isbndb_interval';
      
    } elsif ($x == 1) {
      $str = $pause;
      $vname = 'isbndb_pause';
      
    } else {
      die "Unexpected";
    }
    
    # Check format
    ($str =~ /\A1?[0-9]{1,9}\z/) or
      die "Can't parse configuration variable '$vname', stopped";
    
    # Parse as integer
    my $val = int($str);
    
    # Check range
    ($val > 0) or
      die "Configuration variable '$vname' may not be zero, stopped";
    
    # Update relevant variable
    if ($x == 0) {
      $interval = $val;
    } elsif ($x == 1) {
      $pause = $val;
    } else {
      die "Unexpected";
    }
  }
  
  # Define the new object
  my $self = { };
  bless($self, $class);
  
  # _book_pattern, _rest_key, _interval, and _pause will store copies of
  # the configuration variables
  $self->{'_book_pattern'} = $book_pattern;
  $self->{'_rest_key'    } = $rest_key;
  $self->{'_interval'    } = $interval;
  $self->{'_pause'       } = $pause;
  
  # _tsec and _tmsec define the seconds and microseconds of the last
  # query; since we don't know this at construction, we'll just use the
  # current time
  ($self->{'_tsec'}, $self->{'_msec'}) = gettimeofday;
  
  # Return the new object
  return $self;
}

=back

=head1 INSTANCE METHODS

=over 4

=item B<query(isbn13)>

Query ISBNdb for a specific book.

C<isbn13> is a string containing exactly 13 decimal digits, representing
an ISBN-13 number to look for.

This method will throttle the number of queries according to the
C<isbndb_interval> and C<isbndb_pause> configuration variables, as
explained in the documentation for the constructor.  If this function is
called but not enough time has passed since the last query (or since
object construction if this is the first query), the script will block
until enough time has passed.

If the query is successful, the return value is the whole JSON response
returned from ISBNdb, as a Unicode string.  Note that contrary to the
documentation, the top-level response is a JSON object that has a
C<book> property, and it is I<this> property that has as its value the
JSON attributes object of the book.

If the query failed, C<undef> is returned.  Note that ISBNdb is not very
reliable, and queries that fail may succeed if retried later.  This
function does I<not> perform any retries.

=cut

sub query {
  
  # Check parameter count
  ($#_ == 1) or die "Wrong number of parameters, stopped";
  
  # Get self and parameters
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  my $isbn13 = shift;
  (not ref($isbn13)) or die "Invalid parameter type, stopped";
  ($isbn13 =~ /\A[0-9]{13}\z/) or die "Invalid ISBN-13, stopped";
  
  # Keep waiting if necessary until enough time has passed for us to be
  # able to make another query
  while (1) {
    # Get current time and check that it is not earlier in time than the
    # currently recorded time
    my ($sec, $msec) = gettimeofday;
    (($sec > $self->{'_tsec'}) or
        (($sec == $self->{'_tsec'}) and
            ($msec >= $self->{'_msec'}))) or
      die "System timer error, stopped";
    
    # Adjust current time so that it is an offset of the past recorded
    # time
    if ($msec >= $self->{'_msec'}) {
      # Current microsecond count greater than or equal to past
      # microsecond count, so decrease current count by the past count
      $msec = $msec - $self->{'_msec'};
    } else {
      # Current microsecond count less than pass microsecond count, so
      # transfer one of the current seconds to the microsecond count and
      # then decrease by past count
      $sec  = $sec - 1;
      $msec = $msec + 1000000;
      $msec = $msec - $self->{'_msec'};
    }
    
    # We now have adjusted current time and past time so that the
    # microseconds of the adjusted past time is zero and the current
    # time still is the same distance in the future; now adjust the
    # seconds to get the full offset
    $sec = $sec - $self->{'_tsec'};
    
    # If we are at least 2,000 seconds past the previous time, we have
    # definitely waited long enough because our microsecond count can't
    # go that far without overflowing; in this case, leave the loop
    if ($sec >= 2000) {
      last;
    }
    
    # If we got here, we are less than 2,000 seconds past the previous
    # time so we can safely compute the total number of microseconds
    # without overflow
    my $moffs = ($sec * 1000000) + $msec;
    
    # If enough time has elapsed, leave loop
    if ($moffs >= $self->{'_interval'}) {
      last;
    }
    
    # If we got here, we have to wait a while still
    usleep($self->{'_pause'});
  }
  
  # We throttled the query appropriately so we are now ready to perform
  # it; now define our HTTP request
  my $hreq = HTTP::Request->new(
              'GET',
              sprintf($self->{'_book_pattern'}, "$isbn13"),
              ['Authorization', $self->{'_rest_key'}]);

  # Create an HTTP client, and set the agent name to GaryBot/1.0 along
  # with a space at the end of it so that libwww will append itself too
  my $ua = LWP::UserAgent->new;
  $ua->agent("GaryBot/1.0 ");
  
  # Send the request and receive a response
  my $resp = $ua->request($hreq);
  
  # Update query time to current time
  ($self->{'_tsec'}, $self->{'_msec'}) = gettimeofday;

  # Check whether we got a successful response, failing if not
  (defined $resp) or return undef;
  ($resp->is_success) or return undef;

  # Get the response as a raw binary string
  my $rbin = $resp->decoded_content('charset' => 'none');
  (defined $rbin) or return undef;

  # Try to decode the response as JSON and verify that it is a JSON
  # object that has a "book" property which has a value that is a JSON
  # object; if this fails, then failure
  eval {
    # Decode as JSON
    my $json = decode_json($rbin);
    
    # Check we got a JSON object with a "book" property
    (ref($json) eq 'HASH') or die "Invalid";
    (defined $json->{'book'}) or die "Invalid";
    
    # Check that "book property has hashref value
    (ref($json->{'book'}) eq 'HASH') or die "Invalid";
    
  };
  if ($@) {
    # Verification failed
    return undef;
  }

  # If we got here successfully, then we have an appropriate response,
  # but it is still a binary string; we return the Unicode string by
  # using the database string decoding function
  return Gary::DB->db_to_string($rbin);
}

=back

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

# End with something that evaluates to true
#
1;
