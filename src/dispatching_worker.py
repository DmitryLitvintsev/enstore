###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import errno
import time
import os
import traceback
import checksum
import sys
import socket
import os
import string
import fcntl
import FCNTL
import copy
import types

#enstore imports
import cleanUDP
import Trace
import e_errors

request_dict = {}
#
# Purge entries older than 30 minutes. Dict is a dictionary
#    The first entry, dict[0], is the key
#    The second entry, dict[1], is the message: (client number, ticket, and time)
#        which becomes list[0-2]
def purge_stale_entries(request_dict):
    stale_time = time.time() - 1800
    count = 0
    for entry in request_dict.items():
        list = entry[1]
        if  list[2] < stale_time:
            del request_dict[entry[0]]
            count = count+1
    Trace.trace(20,"purge_stale_entries count=%d",count)

import pdb
def dodebug(a,b):
    pdb.set_trace()

import signal
signal.signal(3,dodebug)

verbose = 0

# check for any children that have exitted (zombies) and collect them
def collect_children():
    try:
        pid, status = os.waitpid(0, os.WNOHANG)
    except os.error, msg:
        if msg.errno != errno.ECHILD:
            Trace.trace(6,"collect_children %s"%(msg,))
            raise os.error, msg

# Generic request response server class, for multiple connections
# Note that the get_request actually read the data from the socket

class DispatchingWorker:

    
    def __init__(self, server_address):
        self.socket_type = socket.SOCK_DGRAM
        self.max_packet_size = 16384
        self.rcv_timeout = 60.   # timeout for get_request in sec.
        self.address_family = socket.AF_INET
        

        self.server_address = server_address
        self.read_fds = []    # fds that the worker/server also wants watched with select
        self.write_fds = []   # fds that the worker/server also wants watched with select
        self.callback = {} #callback functions associated with above

        self.interval_func = None #function to call periodically
        self.last_interval = 0
        
        ## flag for whether we are in a child process
        ## Server loops should be conditional on "self.is_child" rather than 'while 1'
        self.is_child = 0
	self.server_socket = cleanUDP.cleanUDP (self.address_family,
                                    self.socket_type)
        
        # set this socket to be closed in case of an exec
        fcntl.fcntl(self.server_socket.fileno(), FCNTL.F_SETFD, FCNTL.FD_CLOEXEC)
        self.do_collect = 1 # allow clients to override the "collect_children"
        self.server_bind()

    def set_interval_func(self, func, interval):
        self.interval_func = func
        self.interval = interval
        self.rcv_timeout = min(interval, self.rcv_timeout)

    def reset_interval_timer(self):
        self.last_interval = time.time()
    
                             
    def fork(self):
        """Fork off a child process"""
        pid = os.fork()
        
        if pid != 0:  #We're in the parent process
            self.is_child = 0
            return pid
        else:
            self.is_child = 1
            ##Should we close the control socket here?
            return 0
        
        
    def server_bind(self):
        """Called by constructor to bind the socket.

        May be overridden.

        """
        Trace.trace(16,"server_bind add %s"%(self.server_address,))
        self.server_socket.bind(self.server_address)

    
    def serve_forever(self):
        """Handle one request at a time until doomsday, unless we are in a child process"""
        ###XXX should have a global exception handler here
        while not self.is_child:
            self.handle_request()
            if self.do_collect:
                collect_children()
        if self.is_child:
            Trace.trace(6,"server_forever, child process exiting")
            os._exit(0) ## in case the child process doesn't explicitly exit
        else:
            Trace.trace(6,"server_forever, shouldn't get here")

    def handle_request(self):
        """Handle one request, possibly blocking."""
        # request is a "(idn,number,ticket)"
        request, client_address = self.get_request()
        now=time.time()

        if self.interval_func and now-self.last_interval >= self.interval:
            self.last_interval=now
            self.interval_func()

	if request == '':
	    # nothing returned, must be timeout
	    self.handle_timeout()
	    return
	try:
	    self.process_request(request, client_address)
	except KeyboardInterrupt:
	    traceback.print_exc()
	except SystemExit, code:	# processing may fork (forked process will call exit)
	    sys.exit( code )
	except:
	    self.handle_error(request, client_address)



    # a server can add an fd to the server_fds list
    def add_select_fd(self, fd, write=0, callback=None):
        if verbose: print "add fd", fd, ['read','write'][write], callback
        if fd is None:
            return
        if write:
            if fd not in self.write_fds:
                self.write_fds.append(fd)
        else:
            if fd not in self.read_fds:
                self.read_fds.append(fd)
        self.callback[fd]=callback
        ##print "callbacks", self.callback
        
    def remove_select_fd(self, fd):
        if verbose: print "disable fd", fd
        if fd is None:
            return

        if fd in self.write_fds:
            self.write_fds.remove(fd)
        if fd in self.read_fds:
            self.read_fds.remove(fd)
        if self.callback.has_key(fd):
            del self.callback[fd]
        ##print "callbacks", self.callback
        
    def get_request(self):
        # returns  (string, socket address)
        #      string is a stringified ticket, after CRC is removed
        # There are three cases:
        #   read from socket where crc is stripped and return address is valid
        #   read from pipe where there is no crc and no r.a.     
        #   time out where there is no string or r.a.

        gotit = 0
        while not gotit:

            r = self.read_fds + [self.server_socket]
            w = self.write_fds

            rcv_timeout = self.rcv_timeout
            if self.interval_func:
                time_left = self.interval - (time.time()-self.last_interval)
                if time_left<0:
                    time_left=0
                rcv_timeout = min(rcv_timeout, time_left)

            r, w, x, remaining_time = cleanUDP.Select(r, w, r+w, rcv_timeout)

            if not r + w:
                return ('',()) #timeout

            #handle pending I/O operations first
            for fd in r+w:
                if self.callback.has_key(fd) and self.callback[fd]:
                    self.callback[fd](fd)

            for fd in r:
                if fd in self.read_fds and self.callback[fd]==None: #XXX this is special-case code,
                                                        ##for old usage in media_changer
                    msg = os.read(fd, 8)
                    try:
                        bytecount = string.atoi(msg)
                    except:
                        Trace.trace(20,'get_request_select: bad bytecount %s' % (msg,))
                        break
                    msg = ""
                    while len(msg)<bytecount:
                        tmp = os.read(fd, bytecount - len(msg))
                        if not tmp:
                            break
                        msg = msg+tmp
                    request= (msg,())                    #             if so read it
                    self.remove_select_fd(fd)
                    os.close(fd)

                    return request
                elif fd == self.server_socket:
                    req = self.server_socket.recvfrom(self.max_packet_size, self.rcv_timeout)
                    gotit = 1
                    request,inCRC = eval(req[0])
                    # calculate CRC
                    crc = checksum.adler32(0L, request, len(request))
                    if (crc != inCRC) :
                        Trace.trace(6,"handle_request - bad CRC inCRC="+repr(inCRC)+
                                    " calcCRC="+repr(crc))
                        Trace.log(e_errors.INFO, "BAD CRC request: "+request)
                        Trace.log(e_errors.INFO,
                                  "CRC: "+repr(inCRC)+" calculated CRC: "+repr(crc))
                        request=""

        return (request, req[1])

    def handle_timeout(self):
	# override this method for specific timeout hadling
        pass

    def fileno(self):
        """Return socket file number.

        Interface required by select().

        """
        Trace.trace(16,"fileno ="+repr(self.server_socket.fileno()))
        return self.server_socket.fileno()

    # Process the  request that was (generally) sent from UDPClient.send
    def process_request(self, request, client_address):
	# ref udp_client.py (i.e. we may wish to have a udp_client method
	# to get this information)
        idn, number, ticket = eval(request)
        self.reply_address = client_address
        self.client_number = number
        self.current_id = idn

        
        if request_dict.has_key(idn):

            # UDPClient resends messages if it doesn't get a response
            # from us, see it we've already handled this request earlier. We've
            # handled it if we have a record of it in our dict
            lst = request_dict[idn]
            if lst[0] == number:
                Trace.trace(6,"process_request "+repr(idn)+" already handled")
                self.reply_with_list(lst)
                return

            # if the request number is smaller, then there has been a timing
            # race and we've already handled this as much as we are going to.
            elif number < lst[0]: 
                Trace.trace(6,"process_request "+repr(idn)+" old news")
                return #old news, timing race....

        # look in the ticket and figure out what work user wants
        try:
            function_name = ticket["work"]
            function = getattr(self,function_name)
        except (KeyError, AttributeError):
            ticket = {'status' : (e_errors.KEYERROR, 
				  "cannot find requested function `%s'"%(function_name,))}
            Trace.trace(6,"process_request %s %s"%(ticket,function_name))
            self.reply_to_caller(ticket)
            return

        if len(request_dict) > 1000:
            purge_stale_entries(request_dict)

        # call the user function
        Trace.trace(6,"process_request function="+repr(function_name))
        apply(function, (ticket,))
        
    def handle_error(self, request, client_address):
	exc, msg, tb = sys.exc_info()
	Trace.trace(6,"handle_error %s %s"%(exc,msg))
	mode = Trace.mode()
	Trace.mode( mode&~1 ) # freeze circular queue
	Trace.log(e_errors.INFO,'-'*40)
	Trace.log(e_errors.INFO,
                  'Exception during request from %s, request=%s'%
                  (client_address, request))
	e_errors.handle_error(exc, msg, tb)
	Trace.log(e_errors.INFO,'-'*40)
	self.reply_to_caller( {'status':(str(exc),str(msg), 'error'), 
			       'request':request, 
			       'exc_type':str(exc), 
			       'exc_value':str(msg)} )

    def alive(self,ticket):
        ticket['address'] = self.server_address
        ticket['status'] = (e_errors.OK, None)
        ticket['pid'] = os.getpid()
        self.reply_to_caller(ticket)

    # quit instead of being killed
    def quit(self,ticket):
        Trace.trace(10,"quit address="+repr(self.server_address))
        ticket['address'] = self.server_address
        ticket['status'] = (e_errors.OK, None)
        ticket['pid'] = os.getpid()
	Trace.log( e_errors.INFO, 'QUITTING... via sys_exit python call' )
        self.reply_to_caller(ticket)
        sys.exit(0)

    # cleanup if we are done with this unique id
    def done_cleanup(self,ticket):
        try:
            Trace.trace(20,"done_cleanup id="+repr(self.current_id))
            del request_dict[self.current_id]
        except KeyError:
            pass

    # reply to sender with her number and ticket (which has status)
    # generally, the requested user function will send its response through
    # this function - this keeps the request numbers straight
    def reply_to_caller(self, ticket):
        Trace.trace(18,"reply_to_caller number=%s id=%s"%(self.client_number,
                                                          self.current_id))
        reply = (self.client_number, ticket, time.time()) 
        self.reply_with_list(reply)          
        Trace.trace(18,"reply_to_caller number=%s"%(self.client_number,))


    # keep a copy of request to check for later udp retries of same
    # request and then send to the user
    def reply_with_list(self, list):
        Trace.trace(19,"reply_with_list number=%s id=%s"%(self.client_number,
                                                          self.current_id))
        request_dict[self.current_id] = copy.deepcopy(list)
        self.server_socket.sendto(repr(request_dict[self.current_id]), self.reply_address)

    # for requests that are not handled serialy reply_address, current_id, and client_number
    # number must be reset.  In the forking media changer these are in the forked child
    # and passed back to us
    def reply_with_address(self,ticket):
        self.reply_address = ticket["ra"][0] 
        self.client_number = ticket["ra"][1]
        self.current_id    = ticket["ra"][2]
        reply = (self.client_number, ticket, time.time())
        Trace.trace(19,"reply_with_address %s %s %s %s"%( 
            self.reply_address,
            self.current_id,
            self.client_number,
            reply))
        self.reply_to_caller(ticket)
