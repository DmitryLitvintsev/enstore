###############################################################################
#
# $Id$
#
###############################################################################

# system imports
import errno
import time
import os
import traceback
import checksum
import sys
#import socket
import signal
#import string
import copy
#import types

#enstore imports
import udp_server
import hostaddr
import cleanUDP
import Trace
import e_errors
import enstore_constants

MAX_CHILDREN = 32 #Do not allow forking more than this many child processes
DEFAULT_TTL = 60 #One minute lifetime for child processes

# Generic request response server class, for multiple connections
# Note that the get_request actually read the data from the socket

class DispatchingWorker(udp_server.UDPServer):
    
    def __init__(self, server_address, use_raw=None):
        self.use_raw = use_raw
        udp_server.UDPServer.__init__(self, server_address,
                                      receive_timeout=60.0,
                                      use_raw=use_raw)
        #If the UDPServer socket failed to open, stop the server.
        if self.server_socket == None:
            msg = "The udp server socket failed to open.  Aborting.\n"
            sys.stdout.write(msg)
            sys.exit(1)
            
        #Deal with multiple interfaces.

        # fds that the worker/server also wants watched with select
        self.read_fds = []    
        self.write_fds = []
        # callback functions associated with above
        self.callback = {}
        # functions to call periodically -
        #  key is function, value is [interval, last_called]
        self.interval_funcs = {} 

        ## Flag for whether we are in a child process.
        ## Server loops should be conditional on "self.is_child"
        ## rather than 'while 1'.
        self.is_child = 0
        self.n_children = 0
        self.kill_list = []
        
        self.custom_error_handler = None

    def add_interval_func(self, func, interval, one_shot=0,
                          align_interval = None):
        now = time.time()
        if align_interval:
            #Set this so that we start the intervals at prealigned times.
            # For example: if we want the interval to be 15 minutes and
            # the current time is 16:11::41; then set last_called to be
            # 11 minutes and 41 seconds ago.
            (year, month, day, hour, minutes, seconds, unsed, unused, unused) \
                   = time.localtime(now)
            day_begin = time.mktime((year, month, day, 0, 0, 0, -1 , -1 , -1))
            day_now = now - day_begin

            last_called = day_now + day_begin - \
                 (((day_now / interval) - int(day_now / interval)) * interval)
            
        else:
            last_called = now
        self.interval_funcs[func] = [interval, last_called, one_shot]

    def set_interval_func(self, func,interval):
        #Backwards-compatibilty
        self.add_interval_func(func, interval)
        
    def remove_interval_func(self, func):
        del self.interval_funcs[func]
        
    def reset_interval_timer(self, func):
        self.interval_funcs[func][1] = time.time()

    def reset_interval(self, func, interval):
        self.interval_funcs[func][0] = interval
        self.interval_funcs[func][1] = time.time()

    def set_error_handler(self, handler):
        self.custom_error_handler = handler

    # check for any children that have exited (zombies) and collect them
    def collect_children(self):
        while self.n_children > 0:
            try:
                pid, status = os.waitpid(0, os.WNOHANG)
                if pid==0:
                    break
                self.n_children = self.n_children - 1
                if pid in self.kill_list:
                    self.kill_list.remove(pid)
                Trace.trace(6, "collect_children: collected %d, nchildren = %d"
                            % (pid, self.n_children))
            except os.error, msg:
                if msg.errno == errno.ECHILD: #No children to collect right now
                    break
                else: #Some other exception
                    Trace.trace(6,"collect_children %s"%(msg,))
                    raise os.error, msg

    def kill(self, pid, signal):
        if pid not in self.kill_list:
            return
        Trace.trace(6, "killing process %d with signal %d" % (pid,signal))
        try:
            os.kill(pid, signal)
        except os.error, msg:
            Trace.log(e_errors.ERROR, "kill %d: %s" %(pid, msg))
        
    def fork(self, ttl=DEFAULT_TTL):
        """Fork off a child process.  Use this instead of os.fork for safety"""
        if self.n_children >= MAX_CHILDREN:
            Trace.log(e_errors.ERROR, "Too many child processes!")
            return os.getpid()
        if self.is_child: #Don't allow double-forking
            Trace.log(e_errors.ERROR, "Cannot fork from child process!")
            return os.getpid()
        
        pid = os.fork()
        ### The incrementing of the number of childern should occur after
        ### the os.fork() call.  If it is before and os.fork() throws
        ### an execption, then we have a discrepencey.
        self.n_children = self.n_children + 1
        Trace.trace(6,"fork: n_children = %d"%(self.n_children,))

        if pid != 0:  #We're in the parent process
            if ttl is not None:
                self.kill_list.append(pid)
                self.add_interval_func(lambda self=self,pid=pid,sig=signal.SIGTERM: self.kill(pid,sig), ttl, one_shot=1)
                self.add_interval_func(lambda self=self,pid=pid,sig=signal.SIGKILL: self.kill(pid,sig), ttl+5, one_shot=1)
            self.is_child = 0
            return pid
        else:
            self.is_child = 1
            ##Should we close the control socket here?
            return 0
        
        
    def serve_forever(self):
        """Handle one request at a time until doomsday, unless we are in a child process"""
        ###XXX should have a global exception handler here
        count = 0
        if self.use_raw:
            self.set_out_file()
            # start receiver thread or process
            self.raw_requests.receiver()
        while not self.is_child:
            self.do_one_request()
            self.collect_children()
            count = count + 1
            #if count > 100:
            if count > 20:
                self.purge_stale_entries()
                count = 0
                
        if self.is_child:
            Trace.trace(6,"serve_forever, child process exiting")
            os._exit(0) ## in case the child process doesn't explicitly exit
        else:
            Trace.trace(6,"serve_forever, shouldn't get here")

    def do_one_request(self):
        """Receive and process one request, possibly blocking."""
        # request is a "(idn,number,ticket)"
        request = None
        try:
            request, client_address = self.get_request()
        except:
            exc, msg = sys.exc_info()[:2]
             
        now=time.time()

        for func, time_data in self.interval_funcs.items():
            interval, last_called, one_shot = time_data
            if now - last_called > interval:
                if one_shot:
                    del self.interval_funcs[func]
                else: #record last call time
                    self.interval_funcs[func][1] =  now
                Trace.trace(6, "do_one_request: calling interval_function %s"%(func,))
                func()

        if request is None: #Invalid request sent in
            return
        
        if request == '':
            # nothing returned, must be timeout
            self.handle_timeout()
            return
        try:
            self.process_request(request, client_address)
        except KeyboardInterrupt:
            traceback.print_exc()
        except SystemExit, code:
            # processing may fork (forked process will call exit)
            sys.exit( code )
        except:
            self.handle_error(request, client_address)

    # a server can add an fd to the server_fds list
    def add_select_fd(self, fd, write=0, callback=None):
        if fd is None:
            return
        if write:
            if fd not in self.write_fds:
                self.write_fds.append(fd)
        else:
            if fd not in self.read_fds:
                self.read_fds.append(fd)
        self.callback[fd]=callback
        
    def remove_select_fd(self, fd):
        if fd is None:
            return

        while fd in self.write_fds:
            self.write_fds.remove(fd)
        while fd in self.read_fds:
            self.read_fds.remove(fd)
        if self.callback.has_key(fd):
            del self.callback[fd]

    def read_fd(self, fd):
        
            raw_bytecount = os.read(fd, 8)

            #Read on the number of bytes in the message.
            try:
                bytecount = int(raw_bytecount)
            except ValueError:
                Trace.trace(20,
                            'get_request_select: bad bytecount %s %s'
                            % (raw_bytecount, len(raw_bytecount)))
                bytecount = 0

            #Read in the message.
            msg = ""
            while len(msg)<bytecount:
                tmp = os.read(fd, bytecount - len(msg))
                if not tmp:
                    break
                msg = msg+tmp

            #Finish off the communication.
            self.remove_select_fd(fd)
            os.close(fd)

            #Return the request and an empty address.
            addr = ()
            return (msg, addr)

    def get_request(self):
        # returns  (string, socket address)
        #      string is a stringified ticket, after CRC is removed
        # There are three cases:
        #   read from socket where crc is stripped and return address is valid
        #   read from pipe where there is no crc and no r.a.
        #   time out where there is no string or r.a.

        gotit = 0
        t0 = time.time()

        while not gotit:
            r = self.read_fds + [self.server_socket]
            w = self.write_fds
            rcv_timeout = self.rcv_timeout
            if self.interval_funcs:
                now = time.time()
                for func, time_data in self.interval_funcs.items():
                    interval, last_called, one_shot = time_data
                    rcv_timeout = min(rcv_timeout,
                                      interval - (now - last_called))

                rcv_timeout = max(rcv_timeout, 0)
            if self.use_raw:
                try:
                    rc = self.get_message()
                    Trace.trace(5, "disptaching_worker!!: get_request %s"%(rc,))
                except (NameError, ValueError), detail:
                    Trace.trace(5, "dispatching_worker: nameerror %s"%(detail,))
                    self.erc.error_msg = str(detail)
                    self.handle_er_msg(None)
                    return None, None
                if rc and rc != ('',()):
                    #Trace.trace(5, "disptaching_worker: get_request %s"%(rc,))
                    return rc
                else:
                    # process timeout
                    if time.time()-t0 > rcv_timeout:
                        return ('',()) #timeout

            if not self.use_raw:
                r, w, x, remaining_time = cleanUDP.Select(r, w, r+w, rcv_timeout)
                if not r + w:
                    return ('',()) #timeout

                #handle pending I/O operations first
                for fd in r + w:
                    Trace.trace(5, 'dw: get_request cb %s'%(fd,))
                    if self.callback.has_key(fd) and self.callback[fd]:
                        self.callback[fd](fd)

                #now handle other incoming requests
                for fd in r:

                    if type(fd) == type(1) \
                           and fd in self.read_fds \
                           and self.callback[fd]==None:
                        #XXX this is special-case code,
                        #for old usage in media_changer

                        (request, addr) = self.read_fd(fd)
                        Trace.trace(5, 'dw: get_request special')
                        return (request, addr)

                    elif fd == self.server_socket:
                        #Get the 'raw' request and the address from whence it came.
                        try:
                            (request, addr) = self.get_message()
                        except (NameError, ValueError), detail:
                            Trace.trace(5, "dispatching_worker: nameerror %s"%(detail,))
                            self.erc.error_msg = str(detail)
                            Trace.trace
                            self.handle_er_msg(fd)
                            return None, None
                            

                        #Skip these if there is nothing to do.
                        if request == None or addr in [None, ()]:
                            #These conditions could be caught when
                            # hostaddr.allow() raises an exception.  Since,
                            # these are obvious conditions, we stop here to avoid
                            # the Trace.log() that would otherwise fill the
                            # log file with useless error messages.
                            return (request, addr)

                        #Determine if the address the request came from is
                        # one that we should be responding to.
                        try:
                            is_valid_address = hostaddr.allow(addr)
                        except (IndexError, TypeError), detail:
                            Trace.log(e_errors.ERROR,
                                      "hostaddr failed with %s Req.= %s, addr= %s"\
                                      % (detail, request, addr))
                            request = None
                            return (request, addr)

                        #If it should not be responded to, handle the error.
                        if not is_valid_address:
                            Trace.log(e_errors.ERROR,
                                   "attempted connection from disallowed host %s" \
                                      % (addr[0],))
                            request = None
                            return (request, addr)

                        return (request, addr)

        return (None, ())

    # Process the  request that was (generally) sent from UDPClient.send
    def process_request(self, request, client_address):

        #Since get_request() gets requests from UDPServer.get_message()
        # and self.read_fd(fd).  Thusly, some care needs to be taken
        # from within UDPServer.process_request() to be tolerent of
        # requests not originally read with UDPServer.get_message().
        ticket = udp_server.UDPServer.process_request(self, request,
                                                      client_address)

        Trace.trace(6, "dispatching_worker:process_request %s; %s"%(request, ticket,))
        #This checks help process cases where the message was repeated
        # by the client.
        if not ticket:
            Trace.trace(6, "dispatching_worker: no ticket!!!")
            Trace.log(e_errors.ERROR, "dispatching_worker: no ticket!!!")
            return

        # look in the ticket and figure out what work user wants
        try:
            function_name = ticket["work"]
        except (KeyError, AttributeError, TypeError), detail:
            ticket = {'status' : (e_errors.KEYERROR, 
                                  "cannot find any named function")}
            msg = "%s process_request %s from %s" % \
                (detail, ticket, client_address)
            Trace.trace(6, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            self._done_cleanup()
            return

        try:
            Trace.trace(5,"process_request: function %s"%(function_name,))
            function = getattr(self,function_name)
        except (KeyError, AttributeError, TypeError), detail:
            ticket = {'status' : (e_errors.KEYERROR, 
                                  "cannot find requested function `%s'"
                                  % (function_name,))}
            msg = "%s process_request %s %s from %s" % \
                (detail, ticket, function_name, client_address) 
            Trace.trace(6, msg)
            Trace.log(e_errors.ERROR, msg)
            self.reply_to_caller(ticket)
            self._done_cleanup()
            return

        # call the user function
        t = time.time()
        Trace.trace(5,"process_request: function %s"%(function_name, ))
        apply(function, (ticket,))
        self._done_cleanup()
        Trace.trace(5,"process_request: function %s time %s"%(function_name,time.time()-t))

    def handle_error(self, request, client_address):
        exc, msg, tb = sys.exc_info()
        Trace.trace(6,"handle_error %s %s"%(exc,msg))
        Trace.log(e_errors.INFO,'-'*40)
        Trace.log(e_errors.INFO,
                  'Exception during request from %s, request=%s'%
                  (client_address, request))
        Trace.handle_error(exc, msg, tb)
        Trace.log(e_errors.INFO,'-'*40)
        if self.custom_error_handler:
            self.custom_error_handler(exc,msg,tb)
        else:
            self.reply_to_caller( {'status':(str(exc),str(msg), 'error'), 
                                   'request':request, 
                                   'exc_type':str(exc), 
                                   'exc_value':str(msg)} )

    def alive(self,ticket):
        ticket['address'] = self.server_address
        ticket['status'] = (e_errors.OK, None)
        ticket['pid'] = os.getpid()
        self.reply_to_caller(ticket)


    def _do_print(self, ticket):
        Trace.do_print(ticket['levels'])
        
    def do_print(self, ticket):
        Trace.do_print(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)

    def dont_print(self, ticket):
        Trace.dont_print(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)

    def do_log(self, ticket):
        Trace.do_log(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)
        
    def dont_log(self, ticket):
        Trace.dont_log(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)

    def do_alarm(self, ticket):
        Trace.do_alarm(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)
        
    def dont_alarm(self, ticket):
        Trace.dont_alarm(ticket['levels'])
        ticket['status']=(e_errors.OK, None)
        self.reply_to_caller(ticket)
        
        
    def quit(self,ticket):
        if sys.version_info >= (2, 6):
            import multiprocessing
            children = multiprocessing.active_children()
            for p in children:
                p.terminate()
        Trace.trace(10,"quit address="+repr(self.server_address))
        ticket['address'] = self.server_address
        ticket['status'] = (e_errors.OK, None)
        ticket['pid'] = os.getpid()
        Trace.log( e_errors.INFO, 'QUITTING... via os._exit')
        self.reply_to_caller(ticket)
        sys.stdout.flush()
        os._exit(0) ##MWZ: Why not sys.exit()?  No servers fork() anymore...

    # cleanup if we are done with this unique id
    def done_cleanup(self, ticket):
        #The parameter ticket is necessary since that is part of the
        # interface.  All other 'work' related functions also have it.
        __pychecker__ = "unusednames=ticket"
        self._done_cleanup()

    # send back our response
    def send_reply(self, t):
        try:
            self.reply_to_caller(t)
        except:
            # even if there is an error - respond to caller so he can process it
            exc, msg = sys.exc_info()[:2]
            t["status"] = (str(exc),str(msg))
            self.reply_to_caller(t)
            Trace.trace(enstore_constants.DISPWORKDBG,
                        "exception in send_reply %s" % (t,))
            return


    def restricted_access(self):
        '''
        restricted_access(self) -- check if the service is restricted

        restricted service can only be requested on the server node
        This function simply compares self.server_address and
        self.reply_address. If they match, return None. If not, return a
        error status that can be used in reply_to_caller.
        '''
        if self.reply_address[0] in self.ipaddrlist:
             return None

        return (e_errors.ERROR,
                "This restricted service can only be requested from node %s"
                % (self.node_name))
    
