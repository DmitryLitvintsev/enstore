import socket

import Trace
import e_errors

# this is done here to have central exception handling.  it cannot be
# done in the erc read routine, because we cannot import Trace in that
# module as Trace imports the erc module
def read_erc(erc, fd=None):
    try:
    	msg = erc.read()
    except socket.error, detail:
	Trace.log (e_errors.ERROR, 
		   "socket error - could not read from erc (%s)"%(detail,))
	return None
    return msg

