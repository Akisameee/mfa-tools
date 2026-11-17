/* Internal error protocol. English wording belongs to Python messages.py. */
'use strict';
const operations = {};

function gameError(code, details = {}, cause = null) {
    const error = new Error(code);
    error.code = code;
    error.details = details;
    error.cause = cause;
    return error;
}

function rpcFailure(error) {
    return {error: {
        code: error.code || 'INTERNAL_ERROR', details: error.details || {},
        diagnostic: String(error.stack || error) + (error.cause ? '\nCaused by: ' + String(error.cause.stack || error.cause) : ''),
    }};
}
