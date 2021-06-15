<?php

////////////////////////////////////////////////////////////////////////
//                                                                    //
//                           test_gary.php                            //
//                                                                    //
//                                                                    //
//                                                                    //
// PHP test script for the Gary PHP wrapper.                          //
//                                                                    //
// Must be placed in the same directory as a gary.php script that has //
// been properly configured.                                          //
//                                                                    //
// The GET parameter "isbn" dictates the arguments to pass through to //
// a JSON invocation.                                                 //
//                                                                    //
////////////////////////////////////////////////////////////////////////

/*
 * Include the Gary PHP bridge.
 */
require_once __DIR__ . DIRECTORY_SEPARATOR . 'gary.php';

/*
 * Request method must be GET or HEAD.
 */
if (($_SERVER['REQUEST_METHOD'] != 'GET') &&
    ($_SERVER['REQUEST_METHOD'] != 'HEAD')) {
  http_response_code(405);
  header('Content-Type: text/plain');
  echo "Request method not supported!\n";
  exit;
}

/*
 * Make sure we got our variable.
 */
if (array_key_exists('isbn', $_GET) !== true) {
  http_response_code(400);
  header('Content-Type: text/plain');
  echo "Missing GET parameter!\n";
  exit;
}

/*
 * Call through.
 */
$result = NULL;
try {
  $result = gary_invoke_python('json', $_GET['isbn']);
  
} catch (Exception $e) {
  http_response_code(500);
  header('Content-Type: text/plain');
  echo "Gary invocation failed!\n";
  exit;
}

/*
 * Write the result.
 */
header('Content-Type: text/plain');
echo $result;
