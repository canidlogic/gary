# Gary
*A proxy cache for ISBNdb*

Gary is a Python script (with an optional PHP wrapper) that manages a SQLite database to serve as a proxy cache for ISBNdb (https://isbndb.com).  You will need an account at ISBNdb and an API key for that account in order to use Gary.

As of the time of writing, API requests to ISBNdb frequently fail due to ISBNdb being under heavy load.  It is therefore not reliable enough by itself to serve as an on-demand database for book information.  Gary solves this problem by implementing a local cache of data from ISBNdb that is always available.

Gary also includes a query with retries system so that failed queries can be retried after delays.  However, practical tests indicate that even this is sometimes not enough.  The best way to get reliable queries from ISBNdb is to have client-side JavaScript retry Gary queries with a delay of ten seconds or so between retries (because Gary performs retries itself on each invocation).

Once book information is cached within Gary, Gary can safely be used as a reliable on-demand source for book information because all necessary JSON and cover image data is stored in the local SQLite database.

See the specification in the `doc` directory for more information about Gary.

## Python system

The core of Gary is written in Python.

`gary_createdb.py` is used to create a new Gary SQLite database.

`gary_admin.py` is used for administration functions on that Gary SQLite database.

`gary.py` is the main script for querying and retrieving book information.

See the documentation within those scripts for further information.

## PHP wrapper

In order to access the Gary script from PHP, a PHP wrapper is provided in `gary.php`

The PHP script must be configured before use by setting a few configuration variables.  See the documentation in the script for further information.

The PHP wrapper simply creates a Python interpreter instance and runs the `gary.py` script in a separate process.

The `test_gary.php` script is provided to test the Gary PHP wrapper.  See the documentation in that script for further information.

## Contact

This project is maintained by **Noah Johnson**

Email: noah.johnson@loupmail.com
