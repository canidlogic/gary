#
# gary_createdb.py
# ================
#
# Create a new, empty SQLite3 database that has a table structure
# appropriate for use with Gary.
#
# Syntax:
#
#   python3 gary_createdb.py [dbpath]
#
# [dbpath] is the path to the new SQLite database to create.  The given
# path must obey the following format:
#
#   (1) Only the following characters allowed:
#       (A) ASCII alphanumeric
#       (B) Underscore
#       (C) Hyphen
#       (D) Dot
#       (E) os.sep (path component separator)
#       (F) os.altsep if it is not None
#
#   (2) Must not be empty
#
#   (3) Last character may not be a path separator
#
#   (4) No path separator may occur immediately before another path
#   separator
#
#   (5) Dot may not be first character nor last character, nor occur
#   immediately before or after a separator, nor occur immediately after
#   another dot
#
# This script will use os.path.lexists() to check whether the given path
# already exists.  If it does, then an error message will be printed and
# the script will fail.
#
# Otherwise, the script will attempt to open a SQLite database at the
# given path and then perform an exclusive transaction that sets up all
# the tables appropriately for use with Gary.
#

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
# All exceptions defined by this module are subclasses of CreateDBError.
#

class CreateDBError(Exception):
  def __str__(self):
    return 'Unknown error!'

class InvalidPathError(CreateDBError):
  def __str__(self):
    return 'Given database path has invalid format!'

class LogicError(CreateDBError):
  def __str__(self):
    return 'Internal logic error!'

class OpenDBError(CreateDBError):
  def __str__(self):
    return 'Can\'t create SQLite database!'

class PathExistsError(CreateDBError):
  def __str__(self):
    return 'Given database path already exists!'

class SQLError(CreateDBError):
  def __str__(self):
    return 'Error executing SQL statements!'

#
# Local functions
# ---------------
#

# Check whether the given value is a one-character string that matches
# a recognized path separator.
#
# The recognized path separators are os.sep, and os.altsep if it is not
# None.
#
# Parameters:
#
#   s - the value to check
#
# Return:
#
#   True if given value is a recognized separator, False if not
#
def isSep(s):
  
  # Check that it is a string
  if not isinstance(s, str):
    return False
  
  # Check for the main separator
  if s == os.sep:
    return True
  
  # If alternate separator exists, check for it; else, return False
  if os.altsep is not None:
    if s == os.altsep:
      return True
    else:
      return False
  else:
    return False

# Check whether the given value is a proper database path according to
# the restrictions noted at the top of this script.
#
# Parameters:
#
#   s : str | mixed - the value to check
#
# Return:
#
#   True if valid database path, False if not valid
#
def checkPath(s):
  
  # Check that we got a string
  if not isinstance(s, str):
    return False
  
  # Check that not empty
  if len(s) < 1:
    return False
  
  # Check each character
  for i in range(0, len(s)):
    
    # Get current character code
    c = ord(s[i])
    
    # Check that allowed character
    if ((c < ord('A')) or (c > ord('Z'))) and \
        ((c < ord('a')) or (c > ord('z'))) and \
        ((c < ord('0')) or (c > ord('9'))) and \
        (c != ord('_')) and (c != ord('-')) and (c != ord('.')) and \
        (not isSep(s[i])):
      return False
    
    # If path separator, make sure not last character and that next
    # character is not also separator
    if isSep(s[i]):
      if i >= len(s) - 1:
        return False
      if isSep(s[i + 1]):
        return False
    
    # If dot, check various conditions
    if c == ord('.'):
      # Dot may be neither first nor last character
      if (i < 1) or (i >= len(s) - 1):
        return False
      
      # May not occur immediately before or after separator
      if isSep(s[i - 1]) or isSep(s[i + 1]):
        return False
      
      # May not occur immediately after another dot
      if s[i - 1] == '.':
        return False

  # If we got here, path checks out
  return True
  

# The main program function.
#
# Pass in the path to the database.  Exceptions are thrown if there are
# any problems.
#
# The optional parameter is the amount of time in seconds to wait for
# locks in the database.  It must be an integer or float that is finite
# and zero or greater.
#
# Parameters:
#
#   dbpath : str - the path to the database to create
#
#   db_timeout : int | float - the number of seconds to wait for
#   database locks (optional)
#
def createdb_main(dbpath, db_timeout=5.0):
  
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
  
  # Check path
  if not checkPath(dbpath):
    raise InvalidPathError()
  
  # Check that path doesn't exist
  if os.path.lexists(dbpath):
    raise PathExistsError()
  
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
    # Get a cursor
    cur = dbc.cursor()
    
    # Wrap in a try-finally so that cursor gets closed on way out
    try:
      
      # Start an exclusive transaction
      cur.execute('BEGIN EXCLUSIVE TRANSACTION')
      
      # Wrap the rest in a try-catch that rolls back the transaction
      # before rethrowing the exception
      try:
        
        # Run the SQL statements to create the database tables
        cur.execute(
          'CREATE TABLE remap('
          'id INTEGER PRIMARY KEY ASC, '
          'src13 TEXT UNIQUE NOT NULL, '
          'dest13 TEXT NOT NULL)')
        
        cur.execute(
          'CREATE UNIQUE INDEX ix_remap_src '
          'ON remap(src13)')
        
        cur.execute(
          'CREATE INDEX ix_remap_dest '
          'ON remap(dest13)')
        
        cur.execute(
          'CREATE TABLE keys('
          'id INTEGER PRIMARY KEY ASC, '
          'kname TEXT UNIQUE NOT NULL, '
          'kval TEXT NOT NULL)')
        
        cur.execute(
          'CREATE UNIQUE INDEX ix_keys_name '
          'ON keys(kname)')
        
        cur.execute(
          'CREATE TABLE client('
          'id INTEGER PRIMARY KEY ASC, '
          'entry INTEGER NOT NULL, '
          'tkid TEXT UNIQUE NOT NULL, '
          'pswd TEXT NOT NULL, '
          'desc TEXT NOT NULL)')
        
        cur.execute(
          'CREATE UNIQUE INDEX ix_client_tkid '
          'ON client(tkid)')
        
        cur.execute(
          'CREATE INDEX ix_client_entry '
          'ON client(entry)')
        
        cur.execute(
          'CREATE TABLE books('
          'id INTEGER PRIMARY KEY ASC, '
          'isbn13 TEXT UNIQUE NOT NULL, '
          'fetched INTEGER NOT NULL, '
          'json TEXT NOT NULL, '
          'cover BLOB)')
        
        cur.execute(
          'CREATE UNIQUE INDEX ix_books_isbn '
          'ON books(isbn13)')
        
        # If we got here, commit the whole transaction
        cur.execute('COMMIT TRANSACTION')
        
      except Exception as e:
        # Rollback and rethrow as SQLError
        cur.execute('ROLLBACK TRANSACTION')
        raise SQLError() from e
      
    finally:
      cur.close()
  
  finally:
    dbc.close()

#
# Script entrypoint
# -----------------
#

# Should have exactly one argument beyond module name
#
if len(sys.argv) != 2:
  print('Wrong number of program arguments!')
  sys.exit(1)

# Call through to main function and handle exceptions
#
try:
  createdb_main(sys.argv[1])

except OpenDBError as ode:
  print('Script failed:')
  print(ode)
  print('\nTrace information:\n')
  traceback.print_exc()
  sys.exit()

except SQLError as sqe:
  print('Script failed:')
  print(sqe)
  print('\nTrace information:\n')
  traceback.print_exc()
  sys.exit(1)

except CreateDBError as cde:
  print('Script failed:')
  print(cde)
  sys.exit(1)

except:
  print('Script failed due to unexpected error:')
  traceback.print_exc()
  sys.exit(1)
