<?php

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                              gary.php                              //
//                                                                    //
//                                                                    //
//                                                                    //
// PHP wrapper around the Gary Python script.                         //
//                                                                    //
// You must configure the script by setting the configuration         //
// variables below.                                                   //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * If this script was invoked directly by a client browser, return a 404
 * error to hide it.
 * 
 * This script may only be used when included from other PHP scripts.
 */
if (__FILE__ === $_SERVER['SCRIPT_FILENAME']) {
  http_response_code(404);
  header('Content-Type: text/plain');
  echo "Error 404: Not Found\n";
  exit;
}

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                       Configuration variables                      //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * Define the command to invoke the Python interpreter as well as any
 * Python interpreter options that may need to be present before the
 * script name.
 */
// define("GARY_PYTHON_INVOKE", "/path/to/python");

/*
 * Define the path to the gary.py script on the server.
 * 
 * You do not need to do any quoting or escaping; escapeshellarg() will
 * be applied to this during invocation.
 */
// define("GARY_PYTHON_SCRIPT", "/path/to/gary.py");

/*
 * Define the path to the Gary database to use.
 * 
 * You do not need to do any quoting or escaping; escapeshellarg() will
 * be applied to this during invocation.
 */
// define("GARY_DB_PATH", "/path/to/gary.sqlite");

/*
 * Check that configuration constants have been defined.
 */
if ((defined('GARY_PYTHON_INVOKE') !== true) ||
    (defined('GARY_PYTHON_SCRIPT') !== true) ||
    (defined('GARY_DB_PATH') !== true)) {
  http_response_code(500);
  header('Content-Type: text/plain');
  echo "gary.php hasn't been configured yet!\n";
  exit;
}

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                         Custom exceptions                          //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * Thrown when there is a problem invoking the Gary Python script.
 */
class GaryInvokeException extends Exception{ }

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                          Local functions                           //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * Given an ISBN string, normalize the string so that it only contains
 * the relevant digits.
 * 
 * This function drops all ASCII whitespace characters (tab, space,
 * carriage return, line feed) and all ASCII characters that are not
 * alphanumeric.
 * 
 * It also converts all ASCII letters to uppercase.  Note that ISBN-10
 * numbers may have an "X" as their check digit!
 * 
 * This function does NOT guarantee that the value it returns is a valid
 * ISBN.
 * 
 * Passing a non-string as the parameter is equivalent to passing an
 * empty string.
 * 
 * Parameters:
 * 
 *   $str : string | mixed - the ISBN number string to normalize
 * 
 * Return:
 * 
 *   the normalized ISBN string, which is NOT guaranteed to be valid
 */
function gary_normISBNStr($str) {

  // If non-string passed, replace with empty string
  if (is_string($str) !== true) {
    $str = '';
  }

  // Begin with empty result
  $isbn = '';
  
  // Go through each character of string
  $slen = strlen($str);
  for($i = 0; $i < $slen; $i++) {
    
    // Get current character code
    $c = ord($str[$i]);
    
    // Handle based on character type
    if (($c >= ord('a')) && ($c <= ord('z'))) {
      // Lowercase letter, so transfer uppercase to normalized isbn
      $isbn = $isbn . chr($c - 0x20);
    
    } else if (($c >= ord('A')) && ($c <= ord('Z'))) {
      // Uppercase letter, so transfer to normalized isbn
      $isbn = $isbn . chr($c);
    
    } else if (($c >= ord('0')) && ($c <= ord('9'))) {
      // Digit, so transfer to new isbn
      $isbn = $isbn . chr($c);
    
    } else if (($c >= 0x21) && ($c <= 0x7e)) {
      // Non-alphanumeric symbol, so don't transfer
      continue;
    
    } else if (($c === ord("\t")) || ($c === ord("\r")) ||
                ($c === ord("\n")) || ($c === ord(' '))) {
      // Whitespace, so don't transfer
      continue;
    
    } else {
      // Control or extended character so transter to normalized
      $isbn = $isbn . chr($c);
    }
  }
  
  // Return normalized string
  return $isbn;
}

/*
 * Given the first 9 digits of an ISBN-10 or the first 12 digits of an
 * ISBN-13, return a one-character string that holds the check digit.
 * 
 * For ISBN-13, the check digit string is always an ASCII decimal digit
 * in range 0-9.
 * 
 * For ISBN-10, the check digit might also be an uppercase letter X!
 * 
 * If the given parameter is not a string, it does not have a valid 
 * length, or it contains invalid digits, then false is returned.
 * 
 * Parameters:
 * 
 *   $str : string | mixed - the string of digits to check
 * 
 * Return:
 * 
 *   a one-character string with the check digit, or false if given 
 *   parameter is not valid
 */
function gary_computeCheckDigit($str) {
  
  // Check type of parameter
  if (is_string($str) !== true) {
    return false;
  }
  
  // Get length and check that all digits are valid
  $slen = strlen($str);
  for($x = 0; $x < $slen; $x++) {
    
    // Get current character code
    $c = ord($str[$x]);
    
    // Character must be a decimal digit
    if (($c < ord('0')) || ($c > ord('9'))) {
      return false;
    }
  }
  
  // Handle ISBN-10 and ISBN-13 separately
  $result = false;
  if ($slen === 9) {
    // ISBN-10 number, so compute the weighted sum of the non-check
    // digits
    $wsum = 0;
    for($i = 0; $i < 9; $i++) {
      $wsum = $wsum + ((10 - $i) * (ord($str[$i]) - ord('0')));
    }
    
    // Get the remainder of the weighted sum divided by 11
    $r = $wsum % 11;
    
    // If the remainder is zero, check value is also zero; else, check
    // value is 11 subtracted by remainder
    $checkv = 0;
    if ($r > 0) {
      $checkv = 11 - $r;
    }
    
    // Convert the check value to either a decimal digit or X
    if (($checkv >= 0) && ($checkv < 10)) {
      $result = chr(ord('0') + $checkv);
    } else if ($checkv === 10) {
      $result = 'X';
    } else {
      // Shouldn't happen
      throw new Exception("gary-" . strval(__LINE__));
    }
    
  } else if ($slen === 12) {
    // ISBN-13 number, so compute the weighted sum of the non-check
    // digits
    $wsum = 0;
    for($i = 0; $i < 12; $i++) {
      // Get current digit value
      $d = ord($str[$i]) - ord('0');
      
      // If zero-based character index mod 2 is one, then weight is 3;
      // else, it is one
      $r = 1;
      if (($i % 2) === 1) {
        $r = 3;
      }

      // Update weighted sum
      $wsum += ($r * $d);
    }
    
    // Get the remainder of the weighted sum divided by 10
    $r = $wsum % 10;
    
    // If the remainder is zero, check value is also zero; else, check
    // value is 10 subtracted by remainder
    $checkv = 0;
    if ($r > 0) {
      $checkv = 10 - $r;
    }
    
    // Convert the check value to a decimal digit
    if (($checkv >= 0) && ($checkv < 10)) {
      $result = chr(ord('0') + $checkv);
    } else {
      // Shouldn't happen
      throw new Exception("gary-" . strval(__LINE__));
    }
    
  } else {
    // Not a recognized length, so return false
    $result = false;
  }
  
  // Return result
  return $result;
}

/*
 * Given an ISBN-10 or ISBN-13 string, normalize it to an ISBN-13
 * string.
 * 
 * ISBN-10 numbers are converted to ISBN-13.
 * 
 * If the given variable is not a string, or it is a string but not in
 * a valid ISBN format, or it is a ISBN-10 or ISBN-13 string but the
 * check digit is incorrect, the function returns false.
 * 
 * Normalizing the same value more than once has no effect, so you can
 * safely normalize multiple times.
 * 
 * You can check whether an ISBN is valid by normalizing it with this
 * function.  If normalization returns an ISBN, it is valid; otherwise,
 * false is returned, indicating that the given ISBN was not valid.
 * 
 * Parameters:
 * 
 *   $str : string | mixed - the ISBN-10 or ISBN-13 text to normalize
 * 
 * Return:
 * 
 *   the normalized ISBN-13 number, or false if there was a problem with
 *   the given parameter
 */
function gary_normISBN($str) {
  
  // Normalize ISBN text
  $str = gary_normISBNStr($str);
  
  // Handle either ISBN-10 or ISBN-13
  $result = false;
  $slen = strlen($str);
  if ($slen === 10) {
    // ISBN-10 number, so part into main digits and check digit
    $md = substr($str, 0, 9);
    $cd = $str[9];
    
    // Compute what check digit should be
    $cds = gary_computeCheckDigit($md);
    
    // Only proceed if computation was successful; else, ISBN number
    // is not valid and return false
    if ($cds !== false) {
      
      // Only proceed if computed check digit matches given check
      // digit; else, ISBN number is not valid and return false
      if ($cds === $cd) {
        // Convert ISBN-10 to ISBN-13 first by prefixing 978 to the
        // main digits
        $md = '978' . $md;
        
        // Next, recompute check digit for ISBN-13
        $cd = gary_computeCheckDigit($md);
        if ($cd === false) {
          // Shouldn't happen
          throw new Exception("gary-" . strval(__LINE__));
        }
        
        // Form the result as the ISBN-13 conversion
        $result = $md . $cd;
        
      } else {
        // Check digit was not correct
        $result = false;
      }
      
    } else {
      // ISBN-10 was not valid
      $result = false;
    }
    
  } else if ($slen === 13) {
    // ISBN-13 number, so part into main digits and check digit
    $md = substr($str, 0, 12);
    $cd = $str[12];
    
    // Compute what check digit should be
    $cds = gary_computeCheckDigit($md);
    
    // Only proceed if computation was successful; else, ISBN number
    // is not valid and return false
    if ($cds !== false) {
      
      // Only proceed if computed check digit matches given check
      // digit; else, ISBN number is not valid and return false
      if ($cds === $cd) {
        // Check digit was correct, so we can use the normalized
        // ISBN-13 string as our result
        $result = $str;
        
      } else {
        // Check digit was not correct
        $result = false;
      }
      
    } else {
      // ISBN-13 was not valid
      $result = false;
    }
    
  } else {
    // Not a valid ISBN string
    $result = false;
  }
  
  // Return result
  return $result;
}

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                     Python invocation function                     //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * Wrapper function that calls through to the Python Gary script.
 * 
 * gary_mode must be either "json" "pic" or "query"  (The "sync" mode is
 * not supported through the PHP wrapper since it may have a long
 * running time incompatible with CGI scripts.)
 * 
 * isbn is the ISBN-10 or ISBN-13 number to query, which does not need
 * to be normalized.  This function will normalize it to ISBN-13 before
 * invoking the Python script.  If normalization fails, this function
 * will just return "false" as if it called the Python script, even
 * though it doesn't actually invoke Python in that case.
 * 
 * The return value is the output received from the program over
 * standard output.
 * 
 * Exceptions are thrown in case of invocation error.  However, if the
 * Python Gary script has an error, the return value is the JSON string
 * "false"
 * 
 * In the case of a "pic" invocation, successful return will be a binary
 * string.
 * 
 * Parameters:
 * 
 *   $gary_mode : str - the mode of the Gary script to invoke
 * 
 *   $isbn : str - the ISBN string
 * 
 * Return:
 * 
 *   the string result of the Python invocation
 */
function gary_invoke_python($gary_mode, $isbn) {
  
  // Check parameters
  if ((is_string($gary_mode) !== true) || (is_string($isbn) !== true)) {
    throw new Exception("gary-" . strval(__LINE__));
  }
  
  if (($gary_mode != 'json') &&
      ($gary_mode != 'pic') &&
      ($gary_mode != 'query')) {
    throw new Exception("gary-" . strval(__LINE__));
  }
  
  // Normalize to ISBN-13
  $isbn = gary_normISBN($isbn);
  if ($isbn === false) {
    return 'false';
  }
  
  // Build command line for Python invocation
  $cmdline = GARY_PYTHON_INVOKE . ' ' .
              escapeshellarg(GARY_PYTHON_SCRIPT) . ' ' .
              escapeshellarg(GARY_DB_PATH) . ' ' .
              $gary_mode . ' ' .
              $isbn;
  
  // Run the command
  $result = shell_exec($cmdline);
  if (is_null($result)) {
    throw GaryInvokeException();
  }
  
  // If we got here, return the result
  return $result;
}
