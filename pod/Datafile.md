# NAME

Gary::Datafile - Iterate through the lines in a UTF-8 text file.

# SYNOPSIS

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

# DESCRIPTION

Module that opens and allows for iteration through all the lines in a
UTF-8 text file.

See the synopsis for parsing operation.  This module only stores a
single line in memory at a time, so it should handle large data files.

The file should be UTF-8 encoded.  Line breaks may be either LF or
CR+LF.  A UTF-8 Byte Order Mark (BOM) at the start of the file is
ignored.

# CONSTRUCTOR

- **load(file\_path)**

    Construct a new file sreader object.  `file_path` is the path to the
    text file you want to read through.

    Undefined behavior occurs if the data file changes while this reader
    object is opened on it.  The destructor for this object will close the
    file handle automatically.

    The handle is opened in UTF-8 mode with CR+LF translation mode active.
    Any UTF-8 Byte Order Mark (BOM) at the start of the file is skipped.

    This constructor does not actually read anything from the file yet.

# DESTRUCTOR

The destructor for the parser object closes the file handle.

# INSTANCE METHODS

- **rewind()**

    Rewind the data file back to the beginning and change the state of this
    reader to Beginning Of Stream (BOS).  This is also the initial state of
    the reader object after construction.  No record is currently loaded
    after calling this function.

- **line\_number()**

    Get the current line number in the data file.  After construction and
    also immediately following a rewind, this function will return zero. 
    After an advance operation that returns true, this will return the line
    number of the record that was just read (where the first line is 1).
    After an advance operation that returns false, the return value of this
    function is zero.

- **advance()**

    Read the next line from the data file.

    Each call to this function loads a new line.  Note that when the reader
    object is initially constructed, and also immediately following a rewind
    operation, no record is loaded, so you must call this function _before_
    reading the first line.

    The return value is 1 if a new record was loaded, 0 if we have reached
    End Of Stream (EOS).  Once EOS is reached, subsequent calls to this
    function will return EOS until a rewind operation is performed.

- **text()**

    Get the line that was just read.

    This may only be used after a successful call to the advance function.
    A fatal error occurs if this function is called in Beginning Of Stream
    (BOS) or End Of Stream (EOS) state.

    The returned string may include Unicode codepoints.  Any UTF-8 Byte
    Order Mark (BOM) will already be dropped, and any line break characters
    at the end of the line will already be dropped also.

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
