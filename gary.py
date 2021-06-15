#
# gary.py
# =======
#

"""
Gary proxy program for ISBNdb.

Syntax
------

  python gary.py [dbpath] json [isbn]
  python gary.py [dbpath] pic [isbn]
  python gary.py [dbpath] query [isbn]
  python gary.py [dbpath] sync

[dbpath] is the path to the Gary database.  You can use the
gary_createdb.py script to create a new database and gary_admin.py to
administer a Gary database.

[isbn] is an ISBN-10 or ISBN-13 number for the book.  It does not need
to be normalized.  This script will automatically normalize it to an
ISBN-13.

Standard input is not used for all modes except "sync" and may be set to
/dev/null

For "sync" mode, standard input contains a text file listing ISBN
numbers, one per line.  They can be either ISBN-10 or ISBN-13 and they
do not need to be normalized.  Gary will attempt to use query to
successfully load information for ALL these ISBN numbers, calling the
function in a loop for each ISBN until it succeeds.  The operation only
succeeds if ALL ISBN numbers are loaded into the database.  Note that
this operation may take a long time, so don't call from a CGI script.
Also note that if any of the ISBNs aren't in ISBNdb, this function will
keep retrying for many times, so be sure to keep an eye on the script
when using this function.  If interrupted, any ISBN numbers loaded so
far are kept, so you can retry this multiple times if it is taking too
long.

Standard error may be ignored and set to /dev/null  For "sync" mode,
each ISBN number successfully queried is written.

Standard output for "json" mode returns either the same JSON that was
returned from ISBNdb, or it returns the string "false" which decodes to
a JSON value of false if information on the book couldn't be retrieved.

Standard output for "pic" mode returns the raw binary data of the image,
or a line of text reading "false" if no picture is available.

Both the "json" and "pic" will query ISBNdb if necessary to retrieve the
book information.

Standard output for "query" mode returns either JSON "true" or "false"
indicating whether information about the book was successfully cached in
the local Gary database.  If the book is already in the database, this
simply returns true without anything further.  Else, it attempts to
contact ISBNdb for the information.

Standard output for "sync" mode is either JSON "true" or "false"
indicating whether the operation succeeded.

Importing a list of ISBNs from a SQLite database
------------------------------------------------

Use sqlite3 tool to open the database.  Use:

  .output isbn_list.txt

To redirect query output to a text file.  Then, run a query that selects
only the ISBN column.  Once you close the sqlite3 tool, you'll have a
text file with ISBN numbers that you can use with the "sync" mode on
Gary to make sure Gary has all the books.

Important notes
---------------

This script requires POSIX/Unix for the fcntl module.  See portalocker
for platform-independent locking, but you will need to adapt the script
to use that.

You can configure the ISBNdb endpoint address to use below.  The default
value is appropriate for regular subscribers.  If you have a Premium or
Pro account at ISBNdb, you can change the access address to those
special endpoints.
"""

import base64
import datetime
import fcntl
import hashlib
import hmac
import json
import math
import os
import os.path
import sqlite3
import sys
import time
import traceback
import urllib.request

# Don't export anything
#
__all__ = []

#
# Module name
# -----------
#
# Used for error reporting.  This is the name of the executable program
# module passed in through argv.  A default value is used if it can't be
# read from argv.
#
# pModule is the string, with a colon added to the end of it so it can
# easily be used in print statements.  Include a file=sys.stderr
# parameter in print error statements so they get printed to stderr.
#

pModule = 'gary:'
if len(sys.argv) > 0:
  if isinstance(sys.argv[0], str):
    pModule = sys.argv[0] + ':'

#
# ISBNdb endpoint address
# -----------------------
#
# Set this to the URL to send book ISBN queries to, with everything in
# the address except for the ISBN number.
#
# You should change this to a different domain if you have a Premium or
# Pro account.
#

ISBNDB_ENDPOINT = 'https://api2.isbndb.com/book/'

#
# Long retry count
# ----------------
#
# This is the number of times that query() is retried in a loop during
# the "sync" mode.  It is not used in any other mode.
#

LONG_RETRY_COUNT = 20

#
# Exception classes
# -----------------
#
# Each exception overloads the __str__ operator so that it can be
# printed as a user-friendly error message.  It has punctuation at the
# end, but it does NOT have a line break at the end.
#
# All exceptions defined by this module are subclasses of GaryError.
#

class GaryError(Exception):
  def __str__(self):
    return 'Unknown error!'

class BadSyncListError(GaryError):
  def __str__(self):
    return 'Provided sync list contains invalid ISBN numbers!'

class DatabaseIntegrityError(GaryError):
  def __str__(self):
    return 'Database integrity error within Gary database!'

class InvalidISBNError(GaryError):
  def __str__(self):
    return 'ISBN-13 number is not valid or not normalized!'

class ISBNParamError(GaryError):
  def __str__(self):
    return 'Provided ISBN number is not valid!'

class LockError(GaryError):
  def __str__(self):
    return 'Error with file locking!'

class LogicError(GaryError):
  def __str__(self):
    return 'Internal logic error!'

class NoDatabaseFileError(GaryError):
  def __str__(self):
    return 'Requested Gary database file not found!'

class OpenCursorError(GaryError):
  def __str__(self):
    return 'Can\'t open Gary database cursor!'

class OpenDBError(GaryError):
  def __str__(self):
    return 'Can\'t open Gary database!'

class OpenLockfileError(GaryError):
  def __str__(self):
    return 'Can\'t open lockfile!'

class ProgramModeError(GaryError):
  def __str__(self):
    return 'Unrecognized program mode!'

class ProgramParamError(GaryError):
  def __str__(self):
    return 'Wrong number of parameters for program mode!'

class SQLError(GaryError):
  def __str__(self):
    return 'Error running SQL statements against Gary database!'

class SyncError(GaryError):
  def __str__(self):
    return 'Sync operation failed!'

#
# Local functions
# ---------------
#

def norm_isbn_str(s):
  """
  Given an ISBN string, normalize the string so that it only contains 
  the relevant digits.
   
  This function drops all ASCII whitespace characters (tab, space,
  carriage return, line feed) and all ASCII characters that are not
  alphanumeric.
   
  It also converts all ASCII letters to uppercase.  Note that ISBN-10
  numbers may have an "X" as their check digit!
   
  This function does NOT guarantee that the value it returns is a valid
  ISBN.
   
  Passing a non-string as the parameter is equivalent to passing an 
  empty string.
   
  Parameters:
   
    s : str | mixed - the ISBN number string to normalize
   
  Return:
   
    the normalized ISBN string, which is NOT guaranteed to be valid
  """
  
  # If non-string passed, replace with empty string
  if not isinstance(s, str):
    s = ''
  
  # Begin with an empty result
  isbn = ''
  
  # Go through each character of the string
  for cc in s:
    
    # Get current character code
    c = ord(cc)
    
    # Handle based on character type
    if (c >= ord('a')) and (c <= ord('z')):
      # Lowercase letter, so transfer uppercase to normalized ISBN
      isbn = isbn + chr(c - 0x20)
    
    elif (c >= ord('A')) and (c <= ord('Z')):
      # Uppercase letter, so transfer to normalized ISBN
      isbn = isbn + chr(c)
    
    elif (c >= ord('0')) and (c <= ord('9')):
      # Digit, so transfer to normalized ISBN
      isbn = isbn + chr(c)
    
    elif (c >= 0x21) and (c <= 0x7e):
      # Non-alphanumeric symbol, so don't transfer
      pass
    
    elif (c == ord('\t')) or (c == ord('\r')) or \
          (c == ord('\n')) or (c == ord(' ')):
      # Whitespace, so don't transfer
      pass
    
    else:
      # Control or extended character, so transfer to normalized
      isbn = isbn + chr(c)

  # Return normalized string
  return isbn

def compute_isbn_check(s):
  """
  Given the first 9 digits of an ISBN-10 or the first 12 digits of an
  ISBN-13, return a one-character string that holds the check digit.
   
  For ISBN-13, the check digit string is always an ASCII decimal digit
  in range 0-9.
   
  For ISBN-10, the check digit might also be an uppercase letter X!
   
  If the given parameter is not a string, it does not have a valid
  length, or it contains invalid digits, then False is returned.
   
  Parameters:
   
    s : str | mixed - the string of digits to check
   
  Return:
   
    a one-character string with the check digit, or False if given
    parameter is not valid
  """
  
  # Check type of parameter
  if not isinstance(s, str):
    return False
  
  # Check that all digits are valid
  for cc in s:
    
    # Get current character code
    c = ord(cc)
    
    # Character must be decimal digit
    if (c < ord('0')) or (c > ord('9')):
      return False
  
  # Handle ISBN-13 and ISBN-10 separately
  result = False
  if len(s) == 9:
    # ISBN-10 number, so compute the weighted sum of the non-check
    # digits
    wsum = 0
    for i in range(0, 9):
      wsum = wsum + ((10 - i) * (ord(s[i]) - ord('0')))
    
    # Get the remainder of the weighted sum divided by 11
    r = wsum % 11
    
    # If remainder is zero, check value is also zero; else, check value
    # is 11 subtracted by remainder
    checkv = 0
    if r > 0:
      checkv = 11 - r
    
    # Convert the check value to either a decimal digit or X
    if (checkv >= 0) and (checkv < 10):
      result = chr(ord('0')  + checkv)
    elif checkv == 10:
      result = 'X'
    else:
      # Shouldn't happen
      raise LogicError()
    
  elif len(s) == 12:
    # ISBN-13 number, so compute the weighted sum of the non-check
    # digits
    wsum = 0
    for i in range(0, 12):
      
      # Get current digit value
      d = ord(s[i]) - ord('0')
      
      # If zero-based character index mod 2 is one, then weight is 3;
      # else, it is one 
      r = 1
      if (i % 2) == 1:
        r = 3
      
      # Update weighted sum
      wsum = wsum + (r * d)
    
    # Get the remainder of the weighted sum divided by 10
    r = wsum % 10
    
    # If the remainder is zero, check value is also zero; else, check
    # value is 10 subtracted by remainder
    checkv = 0
    if r > 0:
      checkv = 10 - r
    
    # Convert the check value to a decimal digit
    if (checkv >= 0) and (checkv < 10):
      result = chr(ord('0') + checkv)
    else:
      # Shouldn't happen
      raise LogicError()
    
  else:
    # Not a recognized length, so return false
    result = False
  
  # Return result
  return result

def norm_isbn(s):
  """
  Given an ISBN-10 or ISBN-13 string, normalize it to an ISBN-13 string.
   
  ISBN-10 numbers are converted to ISBN-13.
   
  If the given variable is not a string, or it is a string but not in a
  valid ISBN format, or it is a ISBN-10 or ISBN-13 string but the check
  digit is incorrect, the function returns false.
   
  Normalizing the same value more than once has no effect, so you can
  safely normalize multiple times.
   
  You can check whether an ISBN is valid by normalizing it with this
  function.  If normalization returns an ISBN, it is valid; otherwise,
  False is returned, indicating that the given ISBN was not valid.
   
  Parameters:
   
    s : str | mixed - the ISBN-10 or ISBN-13 text to normalize
   
  Return:
   
    the normalized ISBN-13 number, or False if there was a problem with
    the given parameter
  """
  
  # Normalize ISBN text
  s = norm_isbn_str(s)
  
  # Handle either ISBN-10 or ISBN-13
  result = False
  if len(s) == 10:
    # ISBN-10, so part into main digits and check digit
    md = s[0:9]
    cd = s[9]
    
    # Compute what check digit should be
    cds = compute_isbn_check(md)
    
    # Only proceed if computation was successful; else, ISBN number is
    # not valid and return false
    if cds != False:
      
      # Only proceed if computed check digit matches given check digit;
      # else, ISBN number is not valid and return false
      if cds == cd:
        # Convert ISBN-10 to ISBN-13 first by prefixing 978 to the main
        # digits
        md = '978' + md
        
        # Next, recompute check digit for ISBN-13
        cd = compute_isbn_check(md)
        if cd == False:
          # Shouldn't happen
          raise LogicError()
        
        # Form the result as the ISBN-13 conversion
        result = md + cd
      
      else:
        # Check digit was not correct
        result = False
      
    else:
      # ISBN-10 was not valid
      result = False
    
  elif len(s) == 13:
    # ISBN-13 number, so part into main digits and check digit
    md = s[0:12]
    cd = s[12]
    
    # Compute what the check digit should be
    cds = compute_isbn_check(md)
    
    # Only proceed if computation was successful; else, ISBN number is
    # not valid and return false
    if cds != False:
      
      # Only proceed if computed check digit matches given check digit;
      # else, ISBN number is not valid and return False
      if cds == cd:
        # Check digit was correct, so we can use the normalized ISBN-13
        # string as our result
        result = s
      
      else:
        # Check digit was not correct
        result = False
    
    else:
      # ISBN-13 was not valid
      result = False
    
  else:
    # Not a valid ISBN string
    result = False
  
  # Return result
  return result

def is_isbn13(s):
  """
  Check whether the given string is a valid, normalized ISBN-13 number.

  This only passes if the given value is a string that has exactly 13
  decimal digits, and the last decimal digit is a proper ISBN-13 check
  digit.

  Parameters:

    s : str | mixed - the value to check

  Return:

    True if a valid, normalized ISBN-13 number, False otherwise
  """
  
  # Fail if not a string
  if not isinstance(s, str):
    return False
  
  # Fail if not exactly 13 characters
  if len(s) != 13:
    return False
  
  # Check that each character is a decimal digit and compute the
  # weighted sum as we go along
  wsum = 0
  for x in range(0, 13):
    
    # Get current character code
    c = ord(s[x])
    
    # Fail if not a decimal digit
    if (c < ord('0')) or (c > ord('9')):
      return False
    
    # Get proper weight for this digit
    w = 1
    if (x & 0x1) == 1:
      w = 3
    
    # Update weighted sum
    wsum = wsum + (w * (c - ord('0')))
  
  # If weighted sum mod 10 is zero, then check passes; otherwise, check
  # fails
  if (wsum % 10) == 0:
    return True
  else:
    return False

def apply_remap(dbc, isbn13):
  """
  Given an ISBN-13 number, apply a remapping from the ISBN-13 remapping
  table in the database if necessary.

  dbc is the open connection to the Gary database.  It must be open in
  auto-commit mode (isolation_level is None).

  The given ISBN-13 must be a normalized ISBN that passes is_isbn13().

  Parameters:

    dbc - Connection : the Gary SQLite3 database

    isbn13 - str : the ISBN-13 number to check for remaps

  Return:

    the remapped ISBN-13 number, or the given ISBN-13 number if there
    are no remappings
  """
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Check ISBN-13 number
  if not is_isbn13(isbn13):
    raise LogicError()
  
  # Get a cursor for reading the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors, except
  # for DatabaseIntegrityError
  try:
    # Begin a deferred transaction because we're only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      
      # Look up the ISBN-13 in the remap
      cur.execute('SELECT dest13 FROM remap WHERE src13=?', (isbn13,))
      
      # If we found a remap record, remap the ISBN-13
      r = cur.fetchone()
      if r is not None:
        isbn13 = r[0]
        if not is_isbn13(isbn13):
          raise DatabaseIntegrityError()
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except DatabaseIntegrityError as dbe:
    raise dbe
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()
  
  # If we got here, return the (possibly remapped) ISBN-13
  return isbn13

def isbn_cached(dbc, isbn13, imode=False):
  """
  Check whether information about the given ISBN-13 is already cached
  within the Gary database.

  dbc is the open connection to the Gary database.  It must be open in
  auto-commit mode (isolation_level is None).

  The given ISBN-13 must be a normalized ISBN that passes is_isbn13().

  This does NOT apply ISBN-13 remaps, so do that before checking.

  If the optional imode parameter is set to True, the transaction will
  be an immediate transaction instead of a deferred transaction.

  Parameters:

    dbc : Connection - the Gary SQLite3 database

    isbn13 : str - the ISBN-13 number to check for in the database cache

    imode : bool - (Optional) True to use an immediate transaction,
    False to use a deferred transaction

  Return:

    True if the information is already cached, False otherwise
  """
  
  # Check imode
  if not isinstance(imode, bool):
    raise LogicError()
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Check ISBN-13 number
  if not is_isbn13(isbn13):
    raise LogicError()
  
  # Get a cursor for reading the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  result = False
  try:
    # Begin a deferred or immediate transaction
    if imode:
      cur.execute('BEGIN IMMEDIATE TRANSACTION')
    else:
      cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      
      # Look up the ISBN-13 in the books table
      cur.execute('SELECT id FROM books WHERE isbn13=?', (isbn13,))
      
      # If we found a record, set result to True, else set to False
      r = cur.fetchone()
      if r is not None:
        result = True
      else:
        result = False
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()
  
  # If we got here, return the result
  return result

def isbndb_param(dbc):
  """
  Return the checked ISBNdb access information from the given Gary
  database.

  dbc is the open connection to the Gary database.  It must be open in
  auto-commit mode (isolation_level is None).

  If there is an ISBNdb API key and a lockfile in the database, and the
  lockfile is an absolute path that indicates an existing regular file
  that is not a symbolic link, then the return value is a tuple of two
  strings, where the first element is the ISBNdb API key and the second
  element is the absolute file path to the lockfile.  Otherwise, the
  return value is None, indicating that ISBNdb information is not
  present in the Gary database.

  Parameters:

    dbc : Connection - the Gary SQLite3 database

  Return:

    a tuple pair of strings, the first of which is the ISBNdb API key
    and the second of which is the lockfile path; or returns None if
    the ISBNdb information is not in the database
  """
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Get a cursor for reading the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  r_key = None
  r_path = None
  try:
    # Begin a deferred transaction since we are only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Look up the ISBNdb API key
      cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb\'')
      r = cur.fetchone()
      if r is not None:
        r_key = r[0]
      
      # If we got an API key, look up lockfile path
      if r_key is not None:
        cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb_lock\'')
        r = cur.fetchone()
        if r is not None:
          r_path = r[0]
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()
  
  # If we got both a key and a path, then proceed further; else, set
  # result to None
  result = None
  if (r_key is not None) and (r_path is not None):
    # Only proceed if path is absolute and to an existing regular file
    # that is not a link
    if os.path.isabs(r_path):
      if os.path.isfile(r_path):
        if not os.path.islink(r_path):
          # Set result
          result = (r_key, r_path)
  
  # Return result
  return result

def json_query(akey, isbn13):
  """
  Query ISBNdb for JSON information about a book.

  Returns the JSON information if successful and None if information
  couldn't be found.  This function does NOT perform retries.  It only
  performs one attempt, without any delays.  Use isbndb_query() for the
  full querying protocol.

  IMPORTANT: this function assumes that you have acquired and are
  holding an exclusive lock on the ISBNdb lockfile defined in the Gary
  database keys table.  This ensures that only one Gary instance is
  contacting ISBNdb at a time, and that only one Gary instance is adding
  new book information into the database at a time.

  akey is the API key to use with ISBNdb.

  isbn13 is the ISBN-13 of the book to query.  This function does NOT
  apply ISBN remapping, so you should use the apply_remap() function on
  ISBN before calling this function.  The ISBN-13 must be normalized and
  pass is_isbn13()

  This function does NOT check whether information about the book is
  already in the database.

  This uses the global variable ISBNDB_ENDPOINT defined in this module
  to determine where to send queries.  See the documentation of that
  global variable for further information.

  If a string is returned, this function will already have verified that
  it can be parsed as JSON that contains an object with a field "book"
  that is also a JSON object.

  Parameters:

    akey : str - the ISBNdb API key

    isbn13 : str - the normalized ISBN-13 to look for

  Return:

    the JSON information from ISBNdb about the book, or None if the
    information was not received
  """
  
  global ISBNDB_ENDPOINT
  
  # Check API key
  if not isinstance(akey, str):
    raise LogicError()
  
  # Check ISBN-13
  if not is_isbn13(isbn13):
    raise LogicError()
  
  # Attempt to build a request object, returning None if this fails
  rq = None
  try:
    rq = urllib.request.Request(ISBNDB_ENDPOINT + isbn13)
    rq.add_header('Authorization', akey)
  except:
    return None
  
  # Attempt to query ISBNdb, returning None if this fails or if the
  # status code is not 200 or if the response isn't UTF-8 text
  rtxt = None
  try:
    with urllib.request.urlopen(rq) as f:
      # Check for OK status return
      if f.status != 200:
        return None
      
      # Attempt to read the response as UTF-8 text
      rtxt = f.read().decode('utf-8')
      
  except:
    return None
  
  # Check that the string returned from server decodes to a JSON object
  # that has a "book" field which is itself a JSON object
  try:
    j = json.loads(rtxt)
    if not isinstance(j, dict):
      return None
    if 'book' not in j:
      return None
    if not isinstance(j['book'], dict):
      return None
    
  except:
    return None
  
  # If we got all the way here, rtxt appears to be a valid JSON response
  # with book information, so return it
  return rtxt

def img_query(iurl):
  """
  Download an image file from a URL.

  Returns the bytes object with the raw image data if successful and
  None if image couldn't be downloaded.  This function does NOT perform
  retries.  It only performs one attempt, without any delays.  Use
  isbndb_query() for the full querying protocol.

  iurl is the full URL to the image.  This function merely checks that
  the URL is a string without any further validation before attempting
  to request it.

  The function will succeed if a 200 OK status code is received.  The
  function does not validate that the data returned is actually a valid
  image file.

  Parameters:

    iurl : str - the image URL to query

  Return:

    a bytes object containing the raw image bytes, or None if the image
    file couldn't be downloaded
  """
  
  # Check parameter type
  if not isinstance(iurl, str):
    raise LogicError()
  
  # Attempt to download file, returning None if this fails or if the
  # status code is not 200
  rs = None
  try:
    with urllib.request.urlopen(iurl) as f:
      # Check for OK status return
      if f.status != 200:
        return None
      
      # Attempt to read the response as binary data
      rs = f.read()
      
  except:
    return None
  
  # Return downloaded image
  return rs

def isbndb_query(dbc, akey, isbn13,
                jretry=3, jdelay=2.0, iretry=3, idelay=1.0, fdelay=2.0):
  """
  Consult ISBNdb and attempt to load information about a book and cache
  it in the Gary database.

  If the book is already in the database, this call just returns True
  without contacting ISBNdb.

  IMPORTANT: this function assumes that you have acquired and are
  holding an exclusive lock on the ISBNdb lockfile defined in the Gary
  database keys table.  This ensures that only one Gary instance is
  contacting ISBNdb at a time, and that only one Gary instance is adding
  new book information into the database at a time.

  dbc is the open connection to the Gary database.  It must be open in
  auto-commit mode (isolation_level is None).

  akey is the API key to use with ISBNdb.

  isbn13 is the ISBN-13 of the book to query.  This function does NOT
  apply ISBN remapping, so you should use the apply_remap() function on
  ISBN before calling this function.  The ISBN-13 must be normalized and
  pass is_isbn13()

  This function will perform retries and delays if there are problems
  contacting ISBNdb, so there should be no need for clients to do that.

  The optional parameters control how many retries are done, how long
  the delays are between retries, and how much the delay is after the
  last query.  Sensible defaults are given.  jretry and jdelay are the
  retry count and delay in seconds for fetching JSON information, iretry
  and idelay are the corresponding parameters for fetching the cover
  image, fdelay is the delay in seconds after the last contact operation
  to ISBNdb.  The retry counts include the first attempt and so they
  must be greater than zero.  They can be a maximum of 8.  The delays
  must be floats or integers that are zero or greater.  Maximum delays
  are 15 seconds, with greater values clamped to 15 seconds.

  Parameters:

    dbc : Connection - the Gary SQLite3 database

    akey : str - the ISBNdb API key

    isbn13 : str - the normalized ISBN-13 to look for

    jretry : int - (optional) the number of attempts to make at fetching
    JSON data for a book, defaults at a total of 3 attempts

    jdelay : int | float - (optional) the number of seconds to delay
    between attempts to fetch JSON data for a book, defaults at 2
    seconds

    iretry : int - (optional) the number of attempts to make at fetching
    a cover image for a book, defaults at a total of 3 attempts

    idelay : int | float - (optional) the number of seconds to delay
    between attempts to fetch a cover image for a book, defaults at one
    second

    fdelay : int | float - (optional) the number of seconds to delay
    after the last call to ISBNdb before returning, defaults at two
    seconds

  Return:

    True if the book is now in the Gary database, False otherwise
  """
  
  # Check optional variables
  if (not isinstance(jretry, int)) or (not isinstance(iretry, int)):
    raise LogicError()
  if (jretry < 1) or (jretry > 8) or (iretry < 1) or (iretry > 8):
    raise LogicError()
  
  if isinstance(jdelay, int):
    jdelay = float(jdelay)
  if isinstance(idelay, int):
    idelay = float(idelay)
  if isinstance(fdelay, int):
    fdelay = float(fdelay)
  
  if (not isinstance(jdelay, float)) or \
      (not isinstance(idelay, float)) or \
      (not isinstance(fdelay, float)):
    raise LogicError()
  
  if (not math.isfinite(jdelay)) or \
      (not math.isfinite(idelay)) or \
      (not math.isfinite(fdelay)):
    raise LogicError()
    
  if (not (jdelay >= 0.0)) or (not (idelay >= 0.0)) or \
      (not (fdelay >= 0.0)):
    raise LogicError()
  
  if jdelay > 15.0:
    jdelay = 15.0
  if idelay > 15.0:
    idelay = 15.0
  if fdelay > 15.0:
    fdelay = 15.0
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Check API key
  if not isinstance(akey, str):
    raise LogicError()
  
  # Check ISBN-13
  if not is_isbn13(isbn13):
    raise LogicError()
  
  # Since we have an exclusive lock on the ISBNdb lockfile, check once
  # again whether someone has already entered the book in the database
  # using an immediate transaction and return True without proceeding
  # further if this is case -- if not, then we know with certainty that
  # it is up to us to get the book information because we have the
  # exclusive lock
  if isbn_cached(dbc, isbn13, imode=True):
    return True
  
  # OK, time to get the book information for real; set up a retry loop
  # for the JSON information
  jinfo = None
  for i in range(0, jretry):
    # If this isn't the first attempt, insert a delay before retrying
    # the query
    if i > 0:
      time.sleep(jdelay)
    
    # Make an attempt at reading the JSON data
    jinfo = json_query(akey, isbn13)
    
    # If we got the information, leave the loop
    if jinfo is not None:
      break
  
  # If we couldn't get JSON information even after retries, then we
  # can't get information about the book at the moment
  if jinfo is None:
    time.sleep(fdelay)
    return False
  
  # Parse the JSON information, and look for the "image" attribute of
  # the "book" object within the response, to see if there is a cover
  # image that we can fetch
  imgurl = None
  j = json.loads(jinfo)
  if 'image' in j['book']:
    imgurl = j['book']['image']
  del j
  
  # If there is a cover image, try to download that
  imgdata = None
  if imgurl is not None:
    for i in range(0, iretry):
      # If this isn't the first attempt, insert a delay before retrying
      # the image fetch
      if i > 0:
        time.sleep(idelay)
      
      # Make an attempt at downloading the image
      imgdata = img_query(imgurl)
      
      # If we got the information, leave the loop
      if imgdata is not None:
        break
    
    # If we failed to get the image after retries, then we can't get
    # information about the book at the moment
    if imgdata is None:
      time.sleep(fdelay)
      return False
  
  # If we got here, we got all our book data, so open the book database
  # to add it in -- get a cursor for writing the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  result = False
  try:
    # Begin an immediate transaction
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:

      # Get the current timestamp for storing in the database
      ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

      # Insert all the information in the table, including the full
      # image as a binary BLOB if there was one, or NULL if the there
      # was no image
      cur.execute(
          'INSERT INTO books(isbn13, fetched, json, cover) '
          'VALUES (?, ?, ?, ?)', (isbn13, ts, jinfo, imgdata))

      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()
  
  # If we got all the way here, all the data about the book has
  # successfully been added to the Gary database, so just add the final
  # delay before returning True
  time.sleep(fdelay)
  return True

#
# Core functions
# --------------
#

def query(dbpath, isbn13, db_timeout=5.0):
  """
  Attempt to load information about a given book into the Gary database.

  dbpath is the path to the Gary database.  You should use the
  gary_createdb.py utility to create a Gary database and the
  gary_admin.py utility to set it up.

  isbn13 is the ISBN-13 number to search for, which must be normalized
  to be exactly 13 ASCII decimal digits.  This function will properly
  apply ISBN-13 remappings.

  If information about the book is already in the Gary database, then
  this function returns True.  Otherwise, the function attempts to load
  information about the book from the external ISBNdb database service.
  If this succeeds, the information is cached in the Gary database and
  True is returned.  If the attempt to load information fails, False is
  returned.

  The optional db_timeout parameter is an integer or float that must be
  finite and greater than or equal to zero.  It indicates the maximum
  number of seconds to wait for database locks.  (This only applies to
  the SQLite database, not ISBNdb.)

  Exceptions are thrown in case of other troubles.

  Parameters:

    dbpath : str - the path to the Gary database

    isbn13 : str - the normalized ISBN-13 of the book to load

    db_timeout : float | int - (optional) the number of seconds to wait
    for SQLite locks

  Return:

    True if the book is loaded in the database, False if information
    about the book couldn't be loaded
  """
  
  # If timeout is int, convert to float
  if isinstance(db_timeout, int):
    db_timeout = float(db_timeout)
  
  # Timeout must now be a float that is finite and zero or greater
  if not isinstance(db_timeout, float):
    raise LogicError()
  if not math.isfinite(db_timeout):
    raise LogicError()
  if not (db_timeout >= 0.0):
    raise LogicError()
  
  # Check parameters
  if (not isinstance(dbpath, str)) or \
      (not isinstance(isbn13, str)):
    raise LogicError()
  
  if not os.path.isfile(dbpath):
    raise NoDatabaseFileError()

  if not is_isbn13(isbn13):
    raise InvalidISBNError()

  # Now attempt to connect to database, and set to autocommit mode
  # because we will handle transactions manually
  dbc = None
  try:
    dbc = sqlite3.connect(dbpath, db_timeout, 0, None)
  except Exception as e:
    raise OpenDBError from e

  # Wrap the rest in a try-finally that always closes the database on
  # the way out
  result = False
  try:
    # First thing we need to do is remap the ISBN-13 if needed
    isbn13 = apply_remap(dbc, isbn13)
    
    # Next steps depend on whether the ISBN-13 is already cached in the
    # database
    if isbn_cached(dbc, isbn13):
      # ISBN-13 is already cached, so we can set the result to True
      # without doing anything further
      result = True
      
    else:
      # We don't have the information, so get the ISBNdb access
      # information from the database
      iparam = isbndb_param(dbc)
      
      # Only proceed if we have the ISBNdb access parameters, otherwise
      # result is False
      if iparam is not None:
        # We have access information for ISBNdb, so our next step is to
        # acquire an exclusive lock on the lockfile so that we are the
        # only ones connecting with ISBNdb -- first, open the lockfile
        # descriptor using the low-level function since we are just
        # using the file for locking
        lfd = None
        try:
          lfd = os.open(iparam[1], os.O_RDWR)
        except Exception as oe:
          raise OpenLockfileError() from oe
        
        # Wrap the rest in a try-finally that always closes the lockfile
        # descriptor on the way out
        try:
          # Opened the lockfile, so now use Unix file locking to get an
          # exclusive lock on the whole file -- note that this only
          # works on Unix platforms!
          try:
            fcntl.lockf(lfd, fcntl.LOCK_EX)
          except Exception as le:
            raise LockError from le
          
          # Wrap the rest in a try-finally that always releases the file
          # lock on the way out
          try:
            
            # We have the database connection and now an exclusive lock
            # on the ISBNdb lockfile, so call through to the query
            # function for ISBNdb
            result = isbndb_query(dbc, iparam[0], isbn13)
            
          finally:
            fcntl.lockf(lfd, fcntl.LOCK_UN)
          
        finally:
          os.close(lfd)
        
      else:
        # Information isn't cached and database doesn't have access
        # information for ISBNdb, so result must be False
        result = False

  finally:
    dbc.close()
  
  # Return the result
  return result

def info(dbpath, isbn13, db_timeout=5.0):
  """
  Get JSON information about a given book in the Gary database.

  This function is only able to retrieve information that has already
  been cached in the Gary database.  It is NOT able to query ISBNdb to
  retrieve new book information.  Use the query() function for that.
 
  dbpath is the path to the Gary database.  You should use the
  gary_createdb.py utility to create a Gary database and the
  gary_admin.py utility to set it up.

  isbn13 is the ISBN-13 number to search for, which must be normalized
  to be exactly 13 ASCII decimal digits.  This function will properly
  apply ISBN-13 remappings.

  If information about the book is in the Gary database, then this
  function returns a string containing JSON information about the book.
  The JSON information should always be a JSON object that has a field
  called "book", and this field is itself an object that has attributes
  describing the book.

  If information about the book is not present in the database, None is
  returned.

  The optional db_timeout parameter is an integer or float that must be
  finite and greater than or equal to zero.  It indicates the maximum
  number of seconds to wait for database locks.  (This only applies to
  the SQLite database, not ISBNdb.)

  Exceptions are thrown in case of other troubles.

  Parameters:

    dbpath : str - the path to the Gary database

    isbn13 : str - the normalized ISBN-13 of the book

    db_timeout : float | int - (optional) the number of seconds to wait
    for SQLite locks

  Return:

    JSON description of the book, or None if the book information is not
    in the Gary database
  """
  
  # If timeout is int, convert to float
  if isinstance(db_timeout, int):
    db_timeout = float(db_timeout)
  
  # Timeout must now be a float that is finite and zero or greater
  if not isinstance(db_timeout, float):
    raise LogicError()
  if not math.isfinite(db_timeout):
    raise LogicError()
  if not (db_timeout >= 0.0):
    raise LogicError()
  
  # Check parameters
  if (not isinstance(dbpath, str)) or \
      (not isinstance(isbn13, str)):
    raise LogicError()
  
  if not os.path.isfile(dbpath):
    raise NoDatabaseFileError()

  if not is_isbn13(isbn13):
    raise InvalidISBNError()
  
  # Now attempt to connect to database, and set to autocommit mode
  # because we will handle transactions manually
  dbc = None
  try:
    dbc = sqlite3.connect(dbpath, db_timeout, 0, None)
  except Exception as e:
    raise OpenDBError from e

  # Wrap the rest in a try-finally that always closes the database on
  # the way out
  result = None
  try:
    
    # Remap the ISBN-13 if needed
    isbn13 = apply_remap(dbc, isbn13)
    
    # Get a cursor for reading the database
    cur = None
    try:
      cur = dbc.cursor()
    except Exception as e:
      raise OpenCursorError() from e
    
    # Wrap in a try-finally so that the cursor is always closed on the
    # way out, and also rethrow exceptions as SQL exceptions
    try:
    
      # Begin a deferred transaction since we're only reading
      cur.execute('BEGIN DEFERRED TRANSACTION')
      
      # Wrap the rest in a try-catch so that in case of any error, the
      # transaction is rolled back before the exception is rethrown
      try:
        
        # Get the JSON from the database
        cur.execute('SELECT json FROM books WHERE isbn13=?', (isbn13,))
        
        # Fetch the record and set the result, if there is a record
        r = cur.fetchone()
        
        if r is not None:
          result = r[0]
        
        # Commit the transaction to update the database all at once
        cur.execute('COMMIT TRANSACTION')
        
      except Exception as f:
        cur.execute('ROLLBACK TRANSACTION')
        raise f

    except Exception as e:
      raise SQLError() from e
    
    finally:
      cur.close()
      
  finally:
    dbc.close()

  # Return result or None
  return result

def pic(dbpath, isbn13, db_timeout=5.0):
  """
  Get a cover image of a given book in the Gary database.

  This function is only able to retrieve images that have already been
  cached in the Gary database.  It is NOT able to query ISBNdb to
  retrieve new book information or images.  Use the query() function for
  that.

  dbpath is the path to the Gary database.  You should use the
  gary_createdb.py utility to create a Gary database and the
  gary_admin.py utility to set it up.

  isbn13 is the ISBN-13 number to search for, which must be normalized
  to be exactly 13 ASCII decimal digits.  This function will properly
  apply ISBN-13 remappings.

  If information about the book is in the Gary database AND the
  information includes a cover image, then this function returns a bytes
  object containing the raw bytes of the stored image file.  This
  function does NOT guarantee that the returned bytes actually form a
  valid image file.

  If information about the book is not present in the database, or the
  book information does not include a cover image, None is returned.

  The optional db_timeout parameter is an integer or float that must be
  finite and greater than or equal to zero.  It indicates the maximum
  number of seconds to wait for database locks.  (This only applies to
  the SQLite database, not ISBNdb.)

  Exceptions are thrown in case of other troubles.

  Parameters:

    dbpath : str - the path to the Gary database

    isbn13 : str - the normalized ISBN-13 of the book

    db_timeout : float | int - (optional) the number of seconds to wait
    for SQLite locks

  Return:

    raw bytes for the cover image stored in the database, or None if the
    book information is not in the Gary database or the book information
    does not include a cover image
  """

  # If timeout is int, convert to float
  if isinstance(db_timeout, int):
    db_timeout = float(db_timeout)
  
  # Timeout must now be a float that is finite and zero or greater
  if not isinstance(db_timeout, float):
    raise LogicError()
  if not math.isfinite(db_timeout):
    raise LogicError()
  if not (db_timeout >= 0.0):
    raise LogicError()
  
  # Check parameters
  if (not isinstance(dbpath, str)) or \
      (not isinstance(isbn13, str)):
    raise LogicError()
  
  if not os.path.isfile(dbpath):
    raise NoDatabaseFileError()

  if not is_isbn13(isbn13):
    raise InvalidISBNError()
  
  # Now attempt to connect to database, and set to autocommit mode
  # because we will handle transactions manually
  dbc = None
  try:
    dbc = sqlite3.connect(dbpath, db_timeout, 0, None)
  except Exception as e:
    raise OpenDBError from e

  # Wrap the rest in a try-finally that always closes the database on
  # the way out
  result = None
  try:
    
    # Remap the ISBN-13 if needed
    isbn13 = apply_remap(dbc, isbn13)
    
    # Get a cursor for reading the database
    cur = None
    try:
      cur = dbc.cursor()
    except Exception as e:
      raise OpenCursorError() from e
    
    # Wrap in a try-finally so that the cursor is always closed on the
    # way out, and also rethrow exceptions as SQL exceptions
    try:
    
      # Begin a deferred transaction since we're only reading
      cur.execute('BEGIN DEFERRED TRANSACTION')
      
      # Wrap the rest in a try-catch so that in case of any error, the
      # transaction is rolled back before the exception is rethrown
      try:
        
        # Get the image data from the database
        cur.execute('SELECT cover FROM books WHERE isbn13=?', (isbn13,))
        
        # Fetch the record and set the result, if there is a record;
        # even if there is a record, the cover field might still be NULL
        # if there is no image, in which case the SQL NULL will be
        # mapped to a Python None value
        r = cur.fetchone()
        
        if r is not None:
          result = r[0]
        
        # Commit the transaction to update the database all at once
        cur.execute('COMMIT TRANSACTION')
        
      except Exception as f:
        cur.execute('ROLLBACK TRANSACTION')
        raise f

    except Exception as e:
      raise SQLError() from e
    
    finally:
      cur.close()
      
  finally:
    dbc.close()

  # Return result or None
  return result

#
# Main program functions
# ----------------------
#

def main_json(dbpath, isbn):
  """
  Perform the "json" program mode.
  
  Parameters:
  
    dbpath : str - the path to the Gary database
    
    isbn : str - the ISBN number
  """
  
  # Check parameters
  if (not isinstance(dbpath, str)) or (not isinstance(isbn, str)):
    raise LogicError()
  
  # Normalize ISBN to ISBN-13
  isbn = norm_isbn(isbn)
  if isbn == False:
    raise ISBNParamError()
  
  # Attempt to get information about book in database if necessary
  if not query(dbpath, isbn):
    # Couldn't get information about book
    print('false')
    return
  
  # Get JSON result
  result = info(dbpath, isbn)
  if result == None:
    # Someone must have deleted our records since the query call above
    print('false')
    return
  
  # If we got here, we have the result, so print it
  print(result)

def main_pic(dbpath, isbn):
  """
  Perform the "pic" program mode.
  
  Parameters:
  
    dbpath : str - the path to the Gary database
    
    isbn : str - the ISBN number
  """
  
  # Check parameters
  if (not isinstance(dbpath, str)) or (not isinstance(isbn, str)):
    raise LogicError()
  
  # Normalize ISBN to ISBN-13
  isbn = norm_isbn(isbn)
  if isbn == False:
    raise ISBNParamError()
  
  # Attempt to get information about book in database if necessary
  if not query(dbpath, isbn):
    # Couldn't get information about book
    print('false')
    return
  
  # Get binary result
  result = pic(dbpath, isbn)
  if result == None:
    # No picture available
    print('false')
    return
  
  # If we got here, we have the result, so print it -- but since it's a
  # binary file, we have to do a binary write
  sys.stdout.buffer.write(result)

def main_query(dbpath, isbn):
  """
  Perform the "query" program mode.
  
  Parameters:
  
    dbpath : str - the path to the Gary database
    
    isbn : str - the ISBN number
  """
  
  # Check parameters
  if (not isinstance(dbpath, str)) or (not isinstance(isbn, str)):
    raise LogicError()
  
  # Normalize ISBN to ISBN-13
  isbn = norm_isbn(isbn)
  if isbn == False:
    raise ISBNParamError()
  
  # Attempt to get information about book in database if necessary
  if query(dbpath, isbn):
    # Could get information about book
    print('true')
    
  else:
    # Couldn't get information about book
    print('false')

def main_sync(dbpath):
  """
  Perform the "sync" program mode.
  
  Parameters:
  
    dbpath : str - the path to the Gary database
  """
  
  global LONG_RETRY_COUNT
  
  # Check parameter
  if not isinstance(dbpath, str):
    raise LogicError()
  
  # Read all lines of standard input
  for line in sys.stdin:
    
    # Strip leading and trailing whitespace
    line = line.strip()
    
    # If line now empty, skip it
    if len(line) < 1:
      continue
    
    # Get a normalized ISBN for the line
    isbn = norm_isbn(line)
    if isbn == False:
      raise BadSyncListError()
    
    # Keep trying until we download information about book or our long
    # retry count expires
    attempt_success = False
    for i in range(0, LONG_RETRY_COUNT):
      # Make an attempt
      if query(dbpath, isbn):
        # Got information about the book
        attempt_success = True
        break
    
    # If we couldn't get information about the book even after looping,
    # fail
    if not attempt_success:
      print(pModule, 'Can\'t load ISBN:', isbn, file=sys.stderr)
      raise SyncError()
    
    # If we got here, report the book we just loaded
    print(pModule, 'Loaded info for ISBN:', isbn, file=sys.stderr)

#
# Program entrypoint
# ------------------
#

# Make sure at least two arguments beyond module name
#
if len(sys.argv) < 3:
  print(pModule, 'Too few program arguments!', file=sys.stderr)
  sys.exit(1)

# Call through to appropriate main function and handle reporting any
# exceptions that are thrown
#
try:
  mode_name = sys.argv[2]
  if mode_name == 'json':
    # Check number of parameters
    if len(sys.argv) != 4:
      raise ProgramParamError()
    
    # Call through
    main_json(sys.argv[1], sys.argv[3])
    
  elif mode_name == 'pic':
    # Check number of parameters
    if len(sys.argv) != 4:
      raise ProgramParamError()
    
    # Call through
    main_pic(sys.argv[1], sys.argv[3])
    
  elif mode_name == 'query':
    # Check number of parameters
    if len(sys.argv) != 4:
      raise ProgramParamError()
    
    # Call through
    main_query(sys.argv[1], sys.argv[3])
    
  elif mode_name == 'sync':
    # Check number of parameters
    if len(sys.argv) != 3:
      raise ProgramParamError()
    
    # Call through
    main_sync(sys.argv[1])
    
  else:
    # Unrecognized mode
    raise ProgramModeError()

except GaryError as ge:
  print(pModule, ge, file=sys.stderr)
  print('false')
  sys.exit(1)

except:
  print(pModule, 'Unexpected error!', file=sys.stderr)
  traceback.print_exc(file=sys.stderr)
  print('false')
  sys.exit(1)
