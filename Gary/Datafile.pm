package Gary::Datafile;
use strict;

# Core dependencies
use Fcntl qw(:seek);

=head1 NAME

Gary::Datafile - Iterate through the lines in a UTF-8 text file.

=head1 SYNOPSIS

  use Gary::Datafile;
  
  # Open the data file
  my $dr = Gary::Datafile->load($file_path);
  
  # (Re)start an iteration through the file
  $dr->rewind;
  
  # Get current line number, or 0 if Beginning Of Stream (BOS)
  my $lnum = $dr->line_number;
  
  # Read each file line
  while ($dr->advance) {
    # Get line just read
    my $ltext = $dr->text;
    ...
  }

=head1 DESCRIPTION

Module that opens and allows for iteration through all the lines in a
UTF-8 text file.

See the synopsis for parsing operation.  This module only stores a
single line in memory at a time, so it should handle large data files.

The file should be UTF-8 encoded.  Line breaks may be either LF or
CR+LF.  A UTF-8 Byte Order Mark (BOM) at the start of the file is
ignored.

=head1 CONSTRUCTOR

=over 4

=item B<load(file_path)>

Construct a new file sreader object.  C<file_path> is the path to the
text file you want to read through.

Undefined behavior occurs if the data file changes while this reader
object is opened on it.  The destructor for this object will close the
file handle automatically.

The handle is opened in UTF-8 mode with CR+LF translation mode active.
Any UTF-8 Byte Order Mark (BOM) at the start of the file is skipped.

This constructor does not actually read anything from the file yet.

=cut

sub load {
  
  # Check parameter count
  ($#_ == 1) or die "Wrong number of parameters, stopped";
  
  # Get invocant and parameter
  my $invocant = shift;
  my $class = ref($invocant) || $invocant;
  
  my $data_path = shift;
  (not ref($data_path)) or die "Wrong parameter types, stopped";
  (-f $data_path) or die "Can't find file '$data_path', stopped";
  
  # Define the new object
  my $self = { };
  bless($self, $class);
  
  # The '_fh' property will store the file handle for reading the data
  # file
  open(my $fh, '< :encoding(UTF-8) :crlf', $data_path) or
    die "Failed to open file '$data_path', stopped";
  $self->{'_fh'} = $fh;
  
  # The '_state' property will be -1 for BOS, 0 for record, 1 for EOS
  $self->{'_state'} = -1;
  
  # The '_linenum' property is the line number of the last line that was
  # read (where 1 is the first line), or 0 when BOS
  $self->{'_linenum'} = 0;
  
  # When '_state' is 0, '_rec' stores the line just read, without any
  # line break at the end; else, it is an empty string
  $self->{'_rec'} = '';
  
  # Return the new object
  return $self;
}

=back

=head1 DESTRUCTOR

The destructor for the parser object closes the file handle.

=cut

sub DESTROY {
  # Get self
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  # Close the file handle
  close($self->{'_fh'});
}

=head1 INSTANCE METHODS

=over 4

=item B<rewind()>

Rewind the data file back to the beginning and change the state of this
reader to Beginning Of Stream (BOS).  This is also the initial state of
the reader object after construction.  No record is currently loaded
after calling this function.

=cut

sub rewind {
  
  # Check parameter count
  ($#_ == 0) or die "Wrong number of parameters, stopped";
  
  # Get self
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  # Rewind to beginning of file
  seek($self->{'_fh'}, 0, SEEK_SET) or die "Seek failed, stopped";
  
  # Clear state to BOS
  $self->{'_state'  } = -1;
  $self->{'_linenum'} =  0;
  $self->{'_rec'    } = '';
}

=item B<line_number()>

Get the current line number in the data file.  After construction and
also immediately following a rewind, this function will return zero. 
After an advance operation that returns true, this will return the line
number of the record that was just read (where the first line is 1).
After an advance operation that returns false, the return value of this
function is zero.

=cut

sub line_number {
  
  # Check parameter count
  ($#_ == 0) or die "Wrong number of parameters, stopped";
  
  # Get self
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  # Return line number
  return $self->{'_linenum'};
}

=item B<advance()>

Read the next line from the data file.

Each call to this function loads a new line.  Note that when the reader
object is initially constructed, and also immediately following a rewind
operation, no record is loaded, so you must call this function I<before>
reading the first line.

The return value is 1 if a new record was loaded, 0 if we have reached
End Of Stream (EOS).  Once EOS is reached, subsequent calls to this
function will return EOS until a rewind operation is performed.

=cut

sub advance {
  
  # Check parameter count
  ($#_ == 0) or die "Wrong number of parameters, stopped";
  
  # Get self
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  # Handle special state -- if we are already EOS, then just return
  # false without proceeding further
  if ($self->{'_state'} > 0) {
    # EOS
    return 0;
  }
  
  # Check whether we are now EOF; if we are, then set EOS state and
  # return EOS
  if (eof $self->{'_fh'}) {
    # Set EOS state and return EOS
    $self->{'_state'  } =  1;
    $self->{'_linenum'} =  0;
    $self->{'_rec'    } = '';
    return 0;
  }
  
  # If we got here then data file is not EOF, so read the line
  my $ltext = readline($self->{'_fh'});
  (defined $ltext) or die "I/O error reading file, stopped";
  
  # If this is the very first line read, then drop any leading UTF-8 BOM
  if ($self->{'_linenum'} == 0) {
    $ltext =~ s/\A\x{feff}//;
  }
  
  # Increase the line count
  $self->{'_linenum'} = $self->{'_linenum'} + 1;
  
  # Drop line break
  chomp $ltext;
  
  # Update state and record field, then return true
  $self->{'_state'} = 0;
  $self->{'_rec'  } = $ltext;
  
  return 1;
}

=item B<text()>

Get the line that was just read.

This may only be used after a successful call to the advance function.
A fatal error occurs if this function is called in Beginning Of Stream
(BOS) or End Of Stream (EOS) state.

The returned string may include Unicode codepoints.  Any UTF-8 Byte
Order Mark (BOM) will already be dropped, and any line break characters
at the end of the line will already be dropped also.

=cut

sub text {
  
  # Check parameter count
  ($#_ == 0) or die "Wrong number of parameters, stopped";
  
  # Get self
  my $self = shift;
  (ref($self) and $self->isa(__PACKAGE__)) or
    die "Wrong parameter type, stopped";
  
  # Check state
  ($self->{'_state'} == 0) or die "Invalid state, stopped";
  
  # Return desired information
  return $self->{'_rec'};
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
