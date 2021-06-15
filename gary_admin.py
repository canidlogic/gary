#
# gary_admin.py
# =============
#
# Basic administration tools for working with a Gary database.
#
# Syntax:
#
#   python3 gary_admin.py [dbpath] remap [src13] ([dest13])
#   python3 gary_admin.py [dbpath] remap_list
#
#   python3 gary_admin.py [dbpath] isbndb ([api_key] [lockfile_path]) 
#   python3 gary_admin.py [dbpath] isbndb_status
#
#   python3 gary_admin.py [dbpath] client_add [desc]
#   python3 gary_admin.py [dbpath] client_drop [tkid]
#   python3 gary_admin.py [dbpath] client_list
#
# [dbpath] is always the path to the existing Gary SQLite database to
# open.  It must pass os.path.isfile(), indicating that it is a regular
# file that exists.  You can use gary_createdb.py to create a new, empty
# Gary database.
#
# The next parameter after the database path is the administration
# command.  The syntax listing above gives the different commands.  Each
# of the commands is described in detail below.
#
# remap
# -----
#
# The "remap" command takes a [src13] parameter and, optionally, a
# [dest13] parameter.  If a [dest13] parameter is provided, the command
# adds a new ISBN remapping or modifies an existing one.  If no [dest13]
# parameter is provided, the command deletes the mapping for [src13] if
# such a mapping exists.
#
# The [src13] and [dest13] parameters are both normalized by dropping
# hyphens, spaces, and tab characters.  After normalization, they must
# both contain exactly 13 decimal digits, and the last digit must be a
# proper ISBN-13 check digit value.  If [dest13] is given, it may not be
# the same ISBN-13 number as [src13].
#
# It is possible to have ISBN-13 "A" remap to ISBN-13 "B", and ISBN-13
# "B" remap to ISBN-13 "A".  ISBN-13 remapping is not recursive, so no
# infinite loop will be set up.  Instead, this scenario would swap the
# two ISBN-13 numbers.
#
# When Gary receives a request for an ISBN-13 that is one of the source
# keys in the remap table, then Gary will act as if the client had
# instead provided the destination ISBN-13.  If ISBNdb has records for a
# book under a different ISBN-13, remapping allows a quick fix for this
# problem.
#
# remap_list
# ----------
#
# Use the "remap_list" command to print out a list of all the ISBN-13
# remappings that are present in the Gary database.
#
# isbndb
# ------
#
# The "isbndb" command manages the ISBNdb API key and lockfile path that
# is stored in the database.
#
# If [api_key] is provided, it must be a string of visible, printing
# US-ASCII characters after it is normalized by trimming leading and
# trailing whitespace.  It may also not be empty.
#
# When [api_key] is provided, you must also provide [lockfile_path].
# This must be an absolute path (os.path.isabs() passes), and it must
# refer to a regular file (os.path.isfile() passes) that is not a
# symbolic link (os.path.islink() must be False).
#
# Providing both parameters registers a new API key and lockfile path
# for ISBNdb in the Gary database, overwriting any API key and lockfile
# records that are currently there.  If neither parameter is provided,
# then any ISBNdb key and lockfile records that are currently in the
# database will be erased.
#
# You get ISBNdb API keys by registering for the ISBNdb service at
# isbndb.com  The lockfile can be any file, and it can be empty.  It
# justs needs to be useable for fcntl file locking to control access to
# the external ISBNdb database.
#
# If the database does not have a valid ISBNdb API key and lockfile
# path, then it will only be able to serve cached data that is already
# in the database.  Otherwise, it will be able to query ISBNdb for new
# book records.
#
# The ISBNdb API key is stored in plain text in the database, because
# Gary needs to be able to send the plain-text API key to ISBNdb.
#
# Multiple Gary databases can share the same lockfile path.  In this
# case, access to ISBNdb will be synchronized across all Gary databases
# that share the lockfile path.  This is recommended when multiple Gary
# databases share the same API key.
#
# isbndb_status
# -------------
#
# The "isbndb_status" command checks whether the Gary database is
# currently set up for querying an ISBNdb database.
#
# In order to be set up for querying an ISBNdb database, the keys table
# must have records for both isbndb and isbndb_lock.  Furthermore, the
# file path stored in isbndb_lock must refer to a regular file that is
# not a symbolic link (os.path.isfile() must be True, os.path.islink()
# must be False) and the path must be absolute (os.path.isabs() passes).
#
# client_add
# ----------
#
# The "client_add" command adds a new client access key to the Gary
# database.  This allows you to register new clients to use Gary.
#
# The [desc] parameter is a string that may only contain US-ASCII
# printing characters, including the space.  It may not be empty after
# trimming leading and trailing whitespace.  It is used only for giving
# a description of who the client is in the "client_list" function.
#
# The function will print out an API key of 32 base-64 digits in URL
# encoding with no padding.  The first eight digits are the client ID
# and the last 24 digits are the API key.  This API key is NOT stored in
# plain text in the database, so if you forget the full API key that is
# output by this function, there is no way to recover the key.
#
# This full API key is all that is needed to authenticate a Gary client.
# It remains valid so long as the client remains in the client table.
#
# client_drop
# -----------
#
# The "client_drop" command drops a client from the Gary database.  The
# API keys of dropped clients will no longer work after the client is
# dropped.
#
# The [tkid] parameter must be eight base-64 digits in URL encoding that
# identify the specific client to drop.  You can get the client ID
# either from the first eight characters of an API key, or by using the
# client_list command.
#
# client_list
# -----------
#
# The "client_list" command prints a list of all the clients that are
# registered in the database, in ascending chronological order of the
# time that they were added to the database.
#
# For each client, the unique client ID, the date they were added, and
# the description they were added with is printed.
#
# There is no way to determine the API key of a client with this
# function because the API keys are not stored in plain text and can not
# be recovered in any way.
#

import base64
import datetime
import hashlib
import math
import os
import os.path
import sqlite3
import sys
import traceback

#
# Exception classes
# -----------------
#
# Each exception overloads the __str__ operator so that it can be
# printed as a user-friendly error message.  It has punctuation at the
# end, but it does NOT have a line break at the end.
#
# All exceptions defined by this module are subclasses of AdminDBError.
#

class AdminDBError(Exception):
  def __str__(self):
    return 'Unknown error!'

class BadCommandError(AdminDBError):
  def __str__(self):
    return 'Unknown admin command requested!'

class BadLockfileError(AdminDBError):
  def __str__(self):
    return 'Lockfile must exist as regular file and not symbolic link!'

class BadParamError(AdminDBError):
  def __str__(self):
    return 'Wrong number of parameters for admin command!'

class EmptyDescError(AdminDBError):
  def __str__(self):
    return 'Client description may not be empty!'

class InvalidAPIKeyError(AdminDBError):
  def __str__(self):
    return 'Invalid API key!'

class InvalidClientIDError(AdminDBError):
  def __str__(self):
    return 'Invalid unique client ID code!'

class InvalidISBNError(AdminDBError):
  def __str__(self):
    return 'Invalid ISBN-13 number!'

class InvalidLockfilePathError(AdminDBError):
  def __str__(self):
    return 'Lockfile path must be absolute!'

class LogicError(AdminDBError):
  def __str__(self):
    return 'Internal logic error!'

class NotFoundError(AdminDBError):
  def __str__(self):
    return 'Database file not found!'

class NotUniqueError(AdminDBError):
  def __str__(self):
    return 'Can\'t generate unique ID!'

class OpenCursorError(AdminDBError):
  def __str__(self):
    return 'Can\'t open SQL cursor!'

class OpenDBError(AdminDBError):
  def __str__(self):
    return 'Can\'t open SQLite database!'

class SameISBNError(AdminDBError):
  def __str__(self):
    return 'Can\'t remap an ISBN number to itself!'

class SQLError(AdminDBError):
  def __str__(self):
    return 'Error running SQL statements!'

#
# Local functions
# ---------------
#

# Normalize a given ISBN-13 string.
#
# This drops all space, horizontal tabs, and hyphens from the string.
#
# If a non-string is passed, an empty string is returned, which will not
# validate.
#
# There is no guarantee that the normalized string is a valid ISBN-13.
#
# Parameters:
#
#   s : str | mixed - the value to normalize
#
# Return:
#
#   the normalized ISBN-13 code, which is not guaranteed to be valid
#
def norm_isbn13(s):
  
  # If not a string, return empty string
  if not isinstance(s, str):
    return ''
  
  # Start result out as empty string
  result = ''
  
  # Transfer everything to result except space, tab, and hyphen
  for c in s:
    if (c != '-') and (c != ' ') and (c != '\t'):
      result = result + c
  
  # Return result
  return result

# Check whether the given string is a valid, normalized ISBN-13 number.
#
# This only passes if the given value is a string that has exactly 13
# decimal digits, and the last decimal digit is a proper ISBN-13 check
# digit.
#
# Use norm_isbn13() before this function to make sure the value is
# normalized correctly.
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

# Add a new ISBN-13 remapping to the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# src is the source ISBN-13 to remap, dest i the destination ISBN-13 to
# remap.  This function will normalize and validate the ISBN-13 codes.
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   src - str | mixed : the source ISBN-13 to remap
#
#   dest - str | mixed : the destination ISBN-13 to remap to
#
def addRemap(dbc, src, dest):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Normalize ISBN parameters and check them
  src = norm_isbn13(src)
  dest = norm_isbn13(dest)
  
  if (not is_isbn13(src)) or (not is_isbn13(dest)):
    raise InvalidISBNError()
  
  if src == dest:
    raise SameISBNError()
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # First figure out whether there is already a remapping for this
      # source ISBN; if so, determine what it maps to
      cur.execute('SELECT dest13 FROM remap WHERE src13=?', (src,))
      r = cur.fetchone()
      
      # Check the result of the query to determine how to handle -- if
      # the exact remapping is already in the database, don't do
      # anything here
      if r is None:
        # The mapping is not in the table, so we need to add it
        cur.execute('INSERT INTO remap(src13, dest13) '
                    'VALUES (?, ?)', (src, dest))
      
      elif r[0] != dest:
        # The key is in the remap table, but the destination needs to
        # be updated
        cur.execute('UPDATE remap SET dest13=? WHERE src13=?',
                      (dest, src))
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Drop an ISBN-13 remapping from the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# src is the source ISBN-13 of the remapping to drop.  This function
# will normalize and validate the ISBN-13 code.
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   src - str | mixed : the source ISBN-13 to remap
#
def dropRemap(dbc, src):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Normalize ISBN parameter and check it
  src = norm_isbn13(src)
  
  if not is_isbn13(src):
    raise InvalidISBNError()
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Delete the record from the table
      cur.execute('DELETE FROM remap WHERE src13=?', (src,))
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# List all the ISBN-13 remappings in the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
def listRemap(dbc):
  
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
  try:
    # Begin a deferred transaction because we're only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Select all mappings, sorted by increasing source ISBN-13
      cur.execute('SELECT src13, dest13 FROM remap ORDER BY src13 ASC')
      
      # Get first record, if there is one
      r = cur.fetchone()
      
      # If no remappings at all, report it; otherwise, print all
      # remappings
      if r is None:
        print('No ISBN remappings are defined.')
        
      else:
        while r is not None:
          # Print this remapping
          print(r[0], '->', r[1])
          
          # Get next record, if there is one
          r = cur.fetchone()
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Set the ISBNdb API key and lockfile path in the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# akey is the API key.  It will be normalized by this function by
# trimming leading and trailing whitespace.  After normalization, it may
# only contain visible, printing US-ASCII characters and it may not be
# empty.
#
# lfp is the path to the lockfile to use to synchronize access to
# ISBNdb.  It must be an absolute path (os.path.isabs()) and refer to an
# existing regular file (os.path.isfile()) but is must not be a symbolic
# link (not os.path.islink()).
#
# If an ISBNdb API key and lockfile path are already present in the
# database, they are overwritten by the new key.
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   akey - str | mixed : the ISBNdb API key to store
#
#   lfp - str : the lockfile path to use for synchronizing 
#
def setAPIKey(dbc, akey, lfp):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Normalize API key and check it
  if not isinstance(akey, str):
    akey = ''
  akey = akey.strip()
  if len(akey) < 1:
    raise InvalidAPIKeyError()
  for cc in akey:
    c = ord(cc)
    if (c < 0x21) or (c > 0x7e):
      raise InvalidAPIKeyError()
  
  # Check the lockfile path
  if not isinstance(lfp, str):
    raise LogicError()
  if not os.path.isabs(lfp):
    raise InvalidLockfilePathError()
  if not os.path.isfile(lfp):
    raise BadLockfileError()
  if os.path.islink(lfp):
    raise BadLockfileError()
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # First figure out whether there is already an API key; if so,
      # determine what it is
      cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb\'')
      r = cur.fetchone()
      
      # Check the result of the query to determine how to handle -- if
      # the exact API key is already in the database, don't do anything
      # here
      if r is None:
        # No API key is in the table, so we need to add it
        cur.execute('INSERT INTO keys(kname, kval) '
                    'VALUES (\'isbndb\', ?)', (akey,))
      
      elif r[0] != akey:
        # There is a different API key that needs to be updated
        cur.execute('UPDATE keys SET kval=? WHERE kname=\'isbndb\'',
                      (akey,))
      
      # Second determine whether there is already a lockfile path; if
      # so, determine what it is
      cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb_lock\'')
      r = cur.fetchone()
      
      # Check the result of the query to determine how to handle -- if
      # the exact lockfile path is already in the database, don't do
      # anything here
      if r is None:
        # No lockfile key is in the table, so we need to add it
        cur.execute('INSERT INTO keys(kname, kval) '
                    'VALUES (\'isbndb_lock\', ?)', (lfp,))
      
      elif r[0] != lfp:
        # There is a different lockfile path that needs to be updated
        cur.execute(
          'UPDATE keys SET kval=? WHERE kname=\'isbndb_lock\'',
          (lfp,))
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Drop any stored ISBNdb API key and lockfile path from the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
def dropAPIKey(dbc):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Delete any API key from the table
      cur.execute('DELETE FROM keys WHERE kname=\'isbndb\'')
      
      # Delete any lockfile path from the table
      cur.execute('DELETE FROM keys WHERE kname=\'isbndb_lock\'')
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Report on the status of any stored ISBNdb API key and lockfile path in
# the database to determine whether there is a connection to ISBNdb.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
def statusAPIKey(dbc):

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
  try:
    # Begin a deferred transaction since we are only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Query for API key and lockfile path
      akey = None
      lfp = None
      
      cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb\'')
      r = cur.fetchone()
      if r is not None:
        akey = r[0]
      
      cur.execute('SELECT kval FROM keys WHERE kname=\'isbndb_lock\'')
      r = cur.fetchone()
      if r is not None:
        lfp = r[0]
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
      # Check which records were present
      if (akey is not None) and (lfp is not None):
        # Check whether lockfile path is proper
        lfp_ok = False
        if os.path.isabs(lfp):
          if os.path.isfile(lfp):
            if not os.path.islink(lfp):
              lfp_ok = True
        
        # Report status
        print('Key and lockfile path registered in database.')
        print('Lockfile path:', lfp)
        if lfp_ok:
          print('Lockfile path is OK.')
        else:
          print('Lockfile path is INVALID.')
        
      elif (akey is None) and (lfp is None):
        print('No ISBNdb key or lockfile is registered in database.')
        
      else:
        print('Invalid key state in Gary database.')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Add a new client for the Gary database and print the API key.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# desc is the description of the client.  This is only used in client
# listings so that the administrator can identify what each database
# client is.
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   desc - str | mixed : the description of the client
#
#   id_retry - int: (optional) the maximum number of times to retry
#   unique ID regeneration
#
def addClient(dbc, desc, id_retry=16):
  
  # Check optional parameter
  if not isinstance(id_retry, int):
    raise LogicError()
  if id_retry < 1:
    raise LogicError()
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Normalize and check description
  if not isinstance(desc, str):
    desc = ''
  desc = desc.strip()
  if len(desc) < 1:
    raise EmptyDescError()
  
  # Get the current time for the timestamp
  ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Keep generating IDs and passwords until we find a unique one
      rs = None
      rs_user = None
      rs_pswd = None
      for i in range(0, id_retry):
        # Generate 32 random URL-safe base-64 digits from 24 random bytes
        rs = base64.urlsafe_b64encode(os.urandom(24))
        
        # Extract random username and random password
        rs_str = str(rs, encoding='utf-8')
        rs_user = rs_str[0:8]
        rs_pswd = rs[8:]
        
        # Check if random username already in use
        cur.execute('SELECT tkid FROM client WHERE tkid=?', (rs_user,))
        if cur.fetchone() is None:
          # ID is unique, so leave loop because we got an ID
          break
        else:
          # ID is not unique, so reset and try again
          rs = None
          rs_user = None
          rs_pswd = None
      
      # If we didn't manage to generate a unique ID, error
      if rs is None:
        raise NotUniqueError()
      
      # Take the SHA-256 digest of the password -- since the password is
      # completely random, we shouldn't have to worry about salts, and
      # password-specific hashing seems unnecessary -- and then get a
      # normal base-64 encoding of it
      m = hashlib.sha256()
      m.update(rs_pswd)
      rs_pswd = str(base64.b64encode(m.digest()), encoding='utf-8')
      
      # Convert the full API key to a string
      rs = str(rs, encoding='utf-8')
      
      # Add the new database record
      cur.execute('INSERT INTO client(entry, tkid, pswd, desc) '
                  'VALUES (?, ?, ?, ?)',
                  (ts, rs_user, rs_pswd, desc))
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
      
      # Print the API key for the new client
      print('Gary API key for new client:')
      print(rs)
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
  
  except NotUniqueError as nue:
    raise nue
  
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# Drop a client from the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# tkid is unique ID of the client to drop.  This is the first eight
# characters of the Gary API key, or it can be determined by the client
# list function.  The given ID will be normalized by trimming leading
# and trailing whitespace.
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
#   tkid - str : the unique client ID to drop
#
def dropClient(dbc, tkid):
  
  # Check database connection
  if not isinstance(dbc, sqlite3.Connection):
    raise LogicError()
  if dbc.isolation_level != None:
    raise LogicError()
  
  # Check and normalize unique ID parameter
  if not isinstance(tkid, str):
    raise LogicError()
  tkid = tkid.strip()
  if len(tkid) != 8:
    raise InvalidClientIDError()
  for cc in tkid:
    c = ord(cc)
    if ((c < ord('A')) or (c > ord('Z'))) and \
        ((c < ord('a')) or (c > ord('z'))) and \
        ((c < ord('0')) or (c > ord('9'))) and \
        (c != ord('-')) and (c != ord('_')):
      raise InvalidClientIDError()
  
  # Get a cursor for modifying the database
  cur = None
  try:
    cur = dbc.cursor()
  except Exception as e:
    raise OpenCursorError() from e
  
  # Wrap the rest in a try-finally so that the cursor is always closed
  # on the way out; also, rethrow any exceptions as SQLErrors
  try:
    # Begin an immediate transaction so the whole operation is performed
    # in one go
    cur.execute('BEGIN IMMEDIATE TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Delete the client record from the table
      cur.execute('DELETE FROM client WHERE tkid=?', (tkid,))
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# List all the registered clients in the database.
#
# dbc is the open connection to the Gary database.  It must be open in
# auto-commit mode (isolation_level is None).
#
# Exceptions are raised if there are any problems.
#
# The database connection is NOT closed on the way out.
#
# Parameters:
#
#   dbc - Connection : the Gary SQLite3 database
#
def listClient(dbc):
  
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
  try:
    # Begin a deferred transaction because we're only reading
    cur.execute('BEGIN DEFERRED TRANSACTION')
    
    # Wrap the rest in a try-catch so that in case of any error, the
    # transaction is rolled back before the exception is rethrown
    try:
      # Select all clients, sorted by increasing entry timestamp
      cur.execute(
        'SELECT entry, tkid, desc FROM client ORDER BY entry ASC')
      
      # Get first record, if there is one
      r = cur.fetchone()
      
      # If no clients at all, report it; otherwise, print all clients
      if r is None:
        print('No clients are registered.')
        
      else:
        first_rec = True
        while r is not None:
          # Get the parameters of this client
          entry = r[0]
          tkid = r[1]
          desc = r[2]
          
          # Reformat the entry timestamp as a date
          entry = datetime.date.fromtimestamp(entry)
          entry = entry.isoformat()
          
          # Print blank line if necessary
          if first_rec:
            first_rec = False
          else:
            print()
          
          # Print this client information
          print('Client', tkid, 'entered', entry)
          print(desc)
          
          # Get next record, if there is one
          r = cur.fetchone()
      
      # Commit the transaction to update the database all at once
      cur.execute('COMMIT TRANSACTION')
    
    except Exception as f:
      cur.execute('ROLLBACK TRANSACTION')
      raise f
    
  except Exception as e:
    raise SQLError() from e
  
  finally:
    cur.close()

# The main program function.
#
# Pass in the path to the database and the command and argument list.
# The command and argument list should be all command-line parameters
# after the database path in the command line.
#
# Exceptions are thrown if there are any problems.
#
# The optional parameter is the amount of time in seconds to wait for
# locks in the database.  It must be an integer or float that is finite
# and zero or greater.
#
# Parameters:
#
#   dbpath : str - the path to the database to create
#
#   cmdarg : list of str - the command any any arguments
#
#   db_timeout : int | float - the number of seconds to wait for
#   database locks (optional)
#
def admin_main(dbpath, cmdarg, db_timeout=5.0):
  
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
  
  # Check command argument list
  if not isinstance(cmdarg, list):
    raise LogicError()
  for cla in cmdarg:
    if not isinstance(cla, str):
      raise LogicError()
  
  # Check path
  if not isinstance(dbpath, str):
    raise LogicError()
  
  # Check that path is to a regular file that exists
  if not os.path.isfile(dbpath):
    raise NotFoundError()
  
  # Now attempt to connect to database, and set to autocommit mode
  # because we will handle transactions manually
  dbc = None
  try:
    dbc = sqlite3.connect(dbpath, db_timeout, 0, None)
  except Exception as e:
    raise OpenDBError from e
  
  # Wrap the rest in a try-finally that always closes the database on
  # the way out
  try:
    # Must be at least one element in cmdarg list
    if len(cmdarg) < 1:
      raise BadCommandError()
    
    # Get the first element and route to the different command handlers
    cmd = cmdarg[0]
    if cmd == 'remap':
      # Remap must have two additional parameters for adding a remap and
      # one additional parameters for clearing a remap
      if len(cmdarg) == 3:
        addRemap(dbc, cmdarg[1], cmdarg[2])
      
      elif len(cmdarg) == 2:
        dropRemap(dbc, cmdarg[1])
      
      else:
        raise BadParamError()
      
    elif cmd == 'remap_list':
      # Remap list must have no additional parameters
      if len(cmdarg) == 1:
        listRemap(dbc)
      
      else:
        raise BadParamError()
    
    elif cmd == 'isbndb':
      # ISBNdb command must have two additional parameter to set the
      # API key and lockfile and no additional parameters to clear the
      # API key and lockfile
      if len(cmdarg) == 3:
        setAPIKey(dbc, cmdarg[1], cmdarg[2])
      
      elif len(cmdarg) == 1:
        dropAPIKey(dbc)
        
      else:
        raise BadParamError()
    
    elif cmd == 'isbndb_status':
      # ISBNdb status command must have no additional parameters
      if len(cmdarg) == 1:
        statusAPIKey(dbc)
      
      else:
        raise BadParamError()
    
    elif cmd == 'client_add':
      # Add client command must have exactly one additional parameter
      if len(cmdarg) == 2:
        addClient(dbc, cmdarg[1])
        
      else:
        raise BadParamError()
    
    elif cmd == 'client_drop':
      # Drop client command must have exactly one additional parameter
      if len(cmdarg) == 2:
        dropClient(dbc, cmdarg[1])
        
      else:
        raise BadParamError()
    
    elif cmd == 'client_list':
      # List clients command must have no additional parameters
      if len(cmdarg) == 1:
        listClient(dbc)
        pass
        
      else:
        raise BadParamError()
    
    else:
      # Unrecognized command
      raise BadCommandError()
  
  finally:
    dbc.close()

#
# Script entrypoint
# -----------------
#

# Should have at least two arguments beyond module name
#
if len(sys.argv) < 3:
  print('Wrong number of program arguments!')
  sys.exit(1)

# Call through to main function and handle exceptions
#
try:
  admin_main(sys.argv[1], sys.argv[2:])

except OpenCursorError as oce:
  print('Script failed:')
  print(oce)
  print('\nTrace information:\n')
  traceback.print_exc()
  sys.exit(1)

except OpenDBError as ode:
  print('Script failed:')
  print(ode)
  print('\nTrace information:\n')
  traceback.print_exc()
  sys.exit(1)

except SQLError as sqe:
  print('Script failed:')
  print(sqe)
  print('\nTrace information:\n')
  traceback.print_exc()
  sys.exit(1)

except AdminDBError as ade:
  print('Script failed:')
  print(ade)
  sys.exit(1)

except:
  print('Script failed due to unexpected error:')
  traceback.print_exc()
  sys.exit(1)
