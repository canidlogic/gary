#
# gary.py
# =======
#
# Main Gary module.
#
# Note: this requires POSIX/Unix for the fcntl module.  See portalocker
# for platform-independent locking.
#
# You can configure the ISBNdb endpoint address to use below.  The
# default value is appropriate for regular subscribers.  If you have a
# Premium or Pro account at ISBNdb, you can change the access address to
# those special endpoints.
#

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
import time
import urllib.request

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

class AuthFailedError(GaryError):
  def __str__(self):
    return 'Gary API key is not valid!'

class DatabaseIntegrityError(GaryError):
  def __str__(self):
    return 'Database integrity error within Gary database!'

class InvalidISBNError(GaryError):
  def __str__(self):
    return 'ISBN-13 number is not valid or not normalized!'

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

class SQLError(GaryError):
  def __str__(self):
    return 'Error running SQL statements against Gary database!'

#
# Local functions
# ---------------
#

# Check whether the given value is a valid Gary API key.
#
# This returns True only if the given value is a string that has exactly
# 32 characters, and each of these is an ASCII alphanumeric or - or _
#
# This does NOT check whether the key is actually registered in the
# database.  It just checks the format.
#
# Parameters:
#
#   s : str | mixed - the value to check
#
# Return:
#
#   True if the value is a valid Gary API key format, False otherwise
#
def valid_key(s):
  
  # Check type
  if not isinstance(s, str):
    return False
  
  # Check length
  if len(s) != 32:
    return False
  
  # Check each character
  for cc in s:
    c = ord(cc)
    if ((c < ord('A')) or (c > ord('Z'))) and \
        ((c < ord('a')) or (c > ord('z'))) and \
        ((c < ord('0')) or (c > ord('9'))) and \
        (c != ord('-')) and (c != ord('_')):
      return False

  # If we got here, key is in valid format
  return True

# Attempt to authorize the given Gary API key in the given Gary
# database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# s is the key to authorize.  It must pass valid_key().
#
# If successful, this function does nothing.  If there is any problem,
# or if the API key does not validate with the client table in the
# database, some kind of exception is thrown.
#
# If this function returns without exception, then the provided Gary API
# key is valid credentials against the given database.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   s - str : the Gary API key for authorization
#
def auth_key(dbc, s):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Check format of API key
  if not valid_key(s):
    raise LogicError()
  
  # Extract the user ID and password from key
  s_usr = s[0:8]
  s_pswd = s[8:]
  
  # Get the SHA-256 hash of the password encoded in base64
  m = hashlib.sha256()
  m.update(s_pswd.encode(encoding='utf-8'))
  s_pswd = str(base64.b64encode(m.digest()), encoding='utf-8')
  
  # Get a cursor for reading the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors except for
  # AuthFailedError
  try:
    # Begin a deferred transaction because we're only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Attempt to look up the SHA-256 hash of the client password
      cur.execute('SELECT pswd FROM client WHERE tkid=?', (s_usr,))
      
      # Get record -- if no record, authorization failed
      r = cur.fetchone()
      if r is None:
        raise AuthFailedError()
      
      # Compare password hashes with secure comparison function to
      # prevent timing attacks
      if not hmac.compare_digest(r[0], s_pswd):
        raise AuthFailedError()
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except AuthFailedError as afe:
    raise afe
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Check whether the given string is a valid, normalized ISBN-13 number.
#
# This only passes if the given value is a string that has exactly 13
# decimal digits, and the last decimal digit is a proper ISBN-13 check
# digit.
#
# Parameters:
#
#   s : str | mixed - the value to check
#
# Return:
#
#   True if a valid, normalized ISBN-13 number, False otherwise
#
def is_isbn13(s):
  
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

# Given an ISBN-13 number, apply a remapping from the ISBN-13 remapping
# table in the database if necessary.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# The given ISBN-13 must be a normalized ISBN that passes is_isbn13().
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   isbn13 - str : the ISBN-13 number to check for remaps
#
# Return:
#
#   the remapped ISBN-13 number, or the given ISBN-13 number if there
#   are no remappings
#
def apply_remap(dbc, isbn13):
  
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

# Check whether information about the given ISBN-13 is already cached
# within the Gary database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# The given ISBN-13 must be a normalized ISBN that passes is_isbn13().
#
# This does NOT apply ISBN-13 remaps, so do that before checking.
#
# If the optional imode parameter is set to True, the transaction will
# be an immediate transaction instead of a deferred transaction.
#
# Parameters:
#
#   dbc : Connection - the Gary SQLite3 database
#
#   isbn13 : str - the ISBN-13 number to check for in the database cache
#
#   imode : bool - (Optional) True to use an immediate transaction,
#   False to use a deferred transaction
#
# Return:
#
#   True if the information is already cached, False otherwise
#
def isbn_cached(dbc, isbn13, imode=False):
  
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

# Return the checked ISBNdb access information from the given Gary
# database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# If there is an ISBNdb API key and a lockfile in the database, and the
# lockfile is an absolute path that indicates an existing regular file
# that is not a symbolic link, then the return value is a tuple of two
# strings, where the first element is the ISBNdb API key and the second
# element is the absolute file path to the lockfile.  Otherwise, the
# return value is None, indicating that ISBNdb information is not
# present in the Gary database.
#
# Parameters:
#
#   dbc : Connection - the Gary SQLite3 database
#
# Return:
#
#   a tuple pair of strings, the first of which is the ISBNdb API key
#   and the second of which is the lockfile path; or returns None if
#   the ISBNdb information is not in the database
#
def isbndb_param(dbc):
  
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

# Query ISBNdb for JSON information about a book.
#
# Returns the JSON information if successful and None if information
# couldn't be found.  This function does NOT perform retries.  It only
# performs one attempt, without any delays.  Use isbndb_query() for the
# full querying protocol.
#
# IMPORTANT: this function assumes that you have acquired and are
# holding an exclusive lock on the ISBNdb lockfile defined in the Gary
# database keys table.  This ensures that only one Gary instance is
# contacting ISBNdb at a time, and that only one Gary instance is adding
# new book information into the database at a time.
#
# akey is the API key to use with ISBNdb.
#
# isbn13 is the ISBN-13 of the book to query.  This function does NOT
# apply ISBN remapping, so you should use the apply_remap() function on
# ISBN before calling this function.  The ISBN-13 must be normalized and
# pass is_isbn13()
#
# This function does NOT check whether information about the book is
# already in the database.
#
# This uses the global variable ISBNDB_ENDPOINT defined in this module
# to determine where to send queries.  See the documentation of that
# global variable for further information.
#
# If a string is returned, this function will already have verified that
# it can be parsed as JSON that contains an object with a field "book"
# that is also a JSON object.
#
# Parameters:
#
#   akey : str - the ISBNdb API key
#
#   isbn13 : str - the normalized ISBN-13 to look for
#
# Return:
#
#   the JSON information from ISBNdb about the book, or None if the
#   information was not received
#
def json_query(akey, isbn13):
  
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

# Download an image file from a URL.
#
# Returns the bytes object with the raw image data if successful and
# None if image couldn't be downloaded.  This function does NOT perform
# retries.  It only performs one attempt, without any delays.  Use
# isbndb_query() for the full querying protocol.
#
# iurl is the full URL to the image.  This function merely checks that
# the URL is a string without any further validation before attempting
# to request it.
#
# The function will succeed if a 200 OK status code is received.  The
# function does not validate that the data returned is actually a valid
# image file.
#
# Parameters:
#
#   iurl : str - the image URL to query
#
# Return:
#
#   a bytes object containing the raw image bytes, or None if the image
#   file couldn't be downloaded
#
def img_query(iurl):
  
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

# Consult ISBNdb and attempt to load information about a book and cache
# it in the Gary database.
#
# If the book is already in the database, this call just returns True
# without contacting ISBNdb.
#
# IMPORTANT: this function assumes that you have acquired and are
# holding an exclusive lock on the ISBNdb lockfile defined in the Gary
# database keys table.  This ensures that only one Gary instance is
# contacting ISBNdb at a time, and that only one Gary instance is adding
# new book information into the database at a time.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# akey is the API key to use with ISBNdb.
#
# isbn13 is the ISBN-13 of the book to query.  This function does NOT
# apply ISBN remapping, so you should use the apply_remap() function on
# ISBN before calling this function.  The ISBN-13 must be normalized and
# pass is_isbn13()
#
# This function will perform retries and delays if there are problems
# contacting ISBNdb, so there should be no need for clients to do that.
#
# The optional parameters control how many retries are done, how long
# the delays are between retries, and how much the delay is after the
# last query.  Sensible defaults are given.  jretry and jdelay are the
# retry count and delay in seconds for fetching JSON information, iretry
# and idelay are the corresponding parameters for fetching the cover
# image, fdelay is the delay in seconds after the last contact operation
# to ISBNdb.  The retry counts include the first attempt and so they
# must be greater than zero.  They can be a maximum of 8.  The delays
# must be floats or integers that are zero or greater.  Maximum delays
# are 15 seconds, with greater values clamped to 15 seconds.
#
# Parameters:
#
#   dbc : Connection - the Gary SQLite3 database
#
#   akey : str - the ISBNdb API key
#
#   isbn13 : str - the normalized ISBN-13 to look for
#
#   jretry : int - (optional) the number of attempts to make at fetching
#   JSON data for a book, defaults at a total of 3 attempts
#
#   jdelay : int | float - (optional) the number of seconds to delay
#   between attempts to fetch JSON data for a book, defaults at 2
#   seconds
#
#   iretry : int - (optional) the number of attempts to make at fetching
#   a cover image for a book, defaults at a total of 3 attempts
#
#   idelay : int | float - (optional) the number of seconds to delay
#   between attempts to fetch a cover image for a book, defaults at one
#   second
#
#   fdelay : int | float - (optional) the number of seconds to delay
#   after the last call to ISBNdb before returning, defaults at two
#   seconds
#
# Return:
#
#   True if the book is now in the Gary database, False otherwise
# 
def isbndb_query(dbc, akey, isbn13,
                jretry=3, jdelay=2.0, iretry=3, idelay=1.0, fdelay=2.0):
  
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
# Public functions
# ----------------
#

# Attempt to load information about a given book into the Gary database.
#
# dbpath is the path to the Gary database.  You should use the
# gary_createdb.py utility to create a Gary database and the
# gary_admin.py utility to set it up.
#
# gkey is the Gary API key.  This is returned when creating a new client
# using the gary_admin.py utility.
#
# isbn13 is the ISBN-13 number to search for, which must be normalized
# to be exactly 13 ASCII decimal digits.  This function will properly
# apply ISBN-13 remappings.
#
# If information about the book is already in the Gary database, then
# this function returns True.  Otherwise, the function attempts to load
# information about the book from the external ISBNdb database service.
# If this succeeds, the information is cached in the Gary database and
# True is returned.  If the attempt to load information fails, False is
# returned.
#
# The optional db_timeout parameter is an integer or float that must be
# finite and greater than or equal to zero.  It indicates the maximum
# number of seconds to wait for database locks.  (This only applies to
# the SQLite database, not ISBNdb.)
#
# Exceptions are thrown in case of other troubles.
#
# Parameters:
#
#   dbpath : str - the path to the Gary database
#
#   gkey : str - the Gary API key
#
#   isbn13 : str - the normalized ISBN-13 of the book to load
#
#   db_timeout : float | int - (optional) the number of seconds to wait
#   for SQLite locks
#
# Return:
#
#   True if the book is loaded in the database, False if information
#   about the book couldn't be loaded
#
def query(dbpath, gkey, isbn13, db_timeout=5.0):
  
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
      (not isinstance(gkey, str)) or \
      (not isinstance(isbn13, str)):
    raise LogicError()
  
  if not os.path.isfile(dbpath):
    raise NoDatabaseFileError()

  if not valid_key(gkey):
    raise AuthFailedError()
  
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
    # First thing we need to do is check the API key
    auth_key(dbc, gkey)
    
    # Next, remap the ISBN-13 if needed
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

# Get JSON information about a given book in the Gary database.
#
# This function is only able to retrieve information that has already
# been cached in the Gary database.  It is NOT able to query ISBNdb to
# retrieve new book information.  Use the query() function for that.
#
# On the other hand, this function does not require a Gary API key,
# unlike query().  This function is also always available, even if there
# is no ISBNdb API key registered in the Gary database.
#
# dbpath is the path to the Gary database.  You should use the
# gary_createdb.py utility to create a Gary database and the
# gary_admin.py utility to set it up.
#
# isbn13 is the ISBN-13 number to search for, which must be normalized
# to be exactly 13 ASCII decimal digits.  This function will properly
# apply ISBN-13 remappings.
#
# If information about the book is in the Gary database, then this
# function returns a string containing JSON information about the book.
# The JSON information should always be a JSON object that has a field
# called "book", and this field is itself an object that has attributes
# describing the book.
#
# If information about the book is not present in the database, None is
# returned.
#
# The optional db_timeout parameter is an integer or float that must be
# finite and greater than or equal to zero.  It indicates the maximum
# number of seconds to wait for database locks.  (This only applies to
# the SQLite database, not ISBNdb.)
#
# Exceptions are thrown in case of other troubles.
#
# Parameters:
#
#   dbpath : str - the path to the Gary database
#
#   isbn13 : str - the normalized ISBN-13 of the book
#
#   db_timeout : float | int - (optional) the number of seconds to wait
#   for SQLite locks
#
# Return:
#
#   JSON description of the book, or None if the book information is not
#   in the Gary database
#
def info(dbpath, isbn13, db_timeout=5.0):
  
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

# Get a cover image of a given book in the Gary database.
#
# This function is only able to retrieve images that have already been
# cached in the Gary database.  It is NOT able to query ISBNdb to
# retrieve new book information or images.  Use the query() function for
# that.
#
# On the other hand, this function does not require a Gary API key,
# unlike query().  This function is also always available, even if there
# is no ISBNdb API key registered in the Gary database.
#
# dbpath is the path to the Gary database.  You should use the
# gary_createdb.py utility to create a Gary database and the
# gary_admin.py utility to set it up.
#
# isbn13 is the ISBN-13 number to search for, which must be normalized
# to be exactly 13 ASCII decimal digits.  This function will properly
# apply ISBN-13 remappings.
#
# If information about the book is in the Gary database AND the
# information includes a cover image, then this function returns a bytes
# object containing the raw bytes of the stored image file.  This
# function does NOT guarantee that the returned bytes actually form a
# valid image file.
#
# If information about the book is not present in the database, or the
# book information does not include a cover image, None is returned.
#
# The optional db_timeout parameter is an integer or float that must be
# finite and greater than or equal to zero.  It indicates the maximum
# number of seconds to wait for database locks.  (This only applies to
# the SQLite database, not ISBNdb.)
#
# Exceptions are thrown in case of other troubles.
#
# Parameters:
#
#   dbpath : str - the path to the Gary database
#
#   isbn13 : str - the normalized ISBN-13 of the book
#
#   db_timeout : float | int - (optional) the number of seconds to wait
#   for SQLite locks
#
# Return:
#
#   raw bytes for the cover image stored in the database, or None if the
#   book information is not in the Gary database or the book information
#   does not include a cover image
#
def pic(dbpath, isbn13, db_timeout=5.0):

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
