#!/usr/bin/env python

###############################################################################
# src/$RCSfile$   $Revision$
#
#########################################################################
# Log Server.                                                           #
# Receives log messages form the client process and logs them into      #
# the log file.                                                         #
# Log file is being open for append in the directory specified in the   #
# corresponding entry in the configuration dictionary (sever does not   #
# take any arguments so far).                                           #
# The log file has a name LOG-YYYY-MM-DD                                #
# where:                                                                #
#     YYYY - is four digit year number                                  #
#     MM - month of the year (1 - 12)                                   #
#     DD - day of the month                                             #
# at midnight currently open log file gets closed and another one is    #
# open.                                                                 #
# Format of the message in the dictionary is as follows:                #
# HH:MM:SS HOST PID UID SL CLNTABBREV MESSAGE                           #
# where:                                                                #
#    HH:MM:SS - Log Server time when the message has been received      #
#    HOST - name of the host where client sending the message runs      #
#    PID - Process ID of the client which sent a message                #
#    UID - User ID of the client                                        #
#    SL - severity level abbreviation (see client code)                 #
#    MESSAGE - arbitrary message received from the client               #
#########################################################################

# system imports
import sys
import os
import time
import string
import glob

#enstore imports
import setpath

import dispatching_worker
import generic_server
import e_errors
import hostaddr
import Trace
import log_client

"""Logger Class. Instance of this class is a log server. Multiple instances
   of this class can run using unique port numbers. But it actually is not
   recommended. It is assumed that the only one Log Server will serve the
   whole system.
"""
MY_NAME = "log_server"
FILE_PREFIX = "LOG-"

class Logger(  dispatching_worker.DispatchingWorker
	     , generic_server.GenericServer):

    def __init__(self, csc, test=0):
        # need the following definition so the generic client init does not
        # get a logger client
        self.is_logger = 1
        generic_server.GenericServer.__init__(self, csc, MY_NAME)
        self.repeat_count = 0
        self.last_message = ''
        #   pretend that we are the test system
        #   remember, in a system, there is only one bfs
        #   get our port and host from the name server
        #   exit if the host is not this machine
        keys = self.csc.get(MY_NAME)
        Trace.init(self.log_name)
        dispatching_worker.DispatchingWorker.__init__(self, (keys['hostip'],
	                                              keys['port']))
        if keys["log_file_path"][0] == '$':
	    tmp = keys["log_file_path"][1:]
	    try:
	        tmp = os.environ[tmp];
	    except:
	        Trace.log(12, "log_file_path '%s' configuration ERROR"
                          %(keys["log_file_path"]))
	        sys.exit(1)
	    self.logfile_dir_path = tmp
	else:
	    self.logfile_dir_path =  keys["log_file_path"]
	self.test = test

    def open_logfile(self, logfile_name) :
        # try to open log file for append
        try:
            dirname, file = os.path.split(logfile_name)
            if not os.path.exists(dirname):
                os.mkdir(dirname)
            self.logfile = open(logfile_name, 'a')
        except :
	    try:
		self.logfile = open(logfile_name, 'w')
	    except:
                print  "cannot open log %s"%(logfile_name,)
                sys.stderr.write("cannot open log %s\n"%(logfile_name,))
		os._exit(1)

    # return the current log file name
    def get_logfile_name(self, ticket):
        ticket["status"] = (e_errors.OK, None)
        ticket["logfile_name"] = self.logfile_name
        self.send_reply(ticket)

    # return the last log file name
    def get_last_logfile_name(self, ticket):
        ticket["status"] = (e_errors.OK, None)
        ticket["last_logfile_name"] = self.last_logfile_name
        self.send_reply(ticket)

    # return the requested list of logfile names
    def get_logfiles(self, ticket):
	ticket["status"] = (e_errors.OK, None)
	period = ticket.get("period", "today")
	vperiod_keys = log_client.VALID_PERIODS.keys()
	if period in vperiod_keys:
	    num_files_to_get = log_client.VALID_PERIODS[period]
	    files = os.listdir(self.logfile_dir_path)
	    # we want to take the latest files so sort them in reverse order
	    files.sort()
	    files.reverse()
	    num_files = 0
	    lfiles = []
	    for file in files:
		if file[0:4] == FILE_PREFIX:
		    lfiles.append("%s/%s"%(self.logfile_dir_path,file))
		    num_files = num_files +1
		    if num_files >= num_files_to_get and  not period == "all":
			break
	else:
	    # it was not a shortcut keyword so we assume it is a string of the
	    # form LOG*, use globbing to get the list
	    files = "%s/%s"%(self.logfile_dir_path, period)
	    lfiles = glob.glob(files)
	ticket["logfiles"] = lfiles
        self.send_reply(ticket)

    # log the message recieved from the log client
    def log_message(self, ticket) :
        if not ticket.has_key('message'):
            return
        host = hostaddr.address_to_name(self.reply_address[0])
                  ## XXX take care of case where we can't figure out the host name
        message = "%-8s %s"%(host,ticket['message'])
        tm = time.localtime(time.time()) # get the local time
        if message == self.last_message:
            self.repeat_count=self.repeat_count+1
            return
        elif self.repeat_count:
            self.logfile.write("%.2d:%.2d:%.2d last message repeated %d times\n"%
                               (tm[3],tm[4],tm[5], self.repeat_count))
            self.logfile.flush()
            self.repeat_count=0
        self.last_message=message



        # format log message
        message = "%.2d:%.2d:%.2d %s\n" %  (tm[3], tm[4], tm[5], message)
        
        res = self.logfile.write(message)    # write log message to the file
        self.logfile.flush()

    def serve_forever(self):                      # overrides UDPServer method
        self.repeat_count=0
        self.last_message=''
        tm = time.localtime(time.time())          # get the local time
        day = current_day = tm[2];
        if self.test :
            min = current_min = tm[4]
        # form the log file name
        fn = '%s%04d-%02d-%02d' % (FILE_PREFIX, tm[0], tm[1], tm[2])
        if self.test:
            ft = '-%02d-%02d' % (tm[3], tm[4])
            fn = fn + ft

        self.logfile_name = self.logfile_dir_path + "/" + fn
	self.last_logfile_name = ""
        # open log file
        self.open_logfile(self.logfile_name)
        while 1:
            self.handle_request() # this method will eventually call
                                  # log_message()

            # get local time
            tm = time.localtime(time.time())
            day = tm[2];
            if self.test :
                min = tm[4]
            # if test flag is not set reopen log file at midnight
            if not self.test :
                # check if day has been changed
                if day != current_day :
                    # day changed: close the current log file
                    self.logfile.close()
	            self.last_logfile_name = self.logfile_name
                    current_day = day;
                    # and open the new one
                    fn = '%s%04d-%02d-%02d' % (FILE_PREFIX, tm[0], tm[1], 
					       tm[2])
                    self.logfile_name = self.logfile_dir_path + "/" + fn
                    self.open_logfile(self.logfile_name)
            else :
                # if test flag is set reopen log file every minute
                if min != current_min :
                    # minute changed: close the current log file
                    self.logfile.close()
                    current_min = min;
                    # and open the new one
                    fn = '%s%04d-%02d-%02d' % (FILE_PREFIX, tm[0], tm[1], 
					       tm[2])
                    ft = '-%02d-%02d' % (tm[3], tm[4])
                    fn = fn + ft
                    self.logfile_name = self.logfile_dir_path + "/" + fn
                    self.open_logfile(self.logfile_name)


class LoggerInterface(generic_server.GenericServerInterface):

    def __init__(self):
        # fill in the defaults for possible options
	self.config_file = ""
	self.test = 0
        generic_server.GenericServerInterface.__init__(self)

    # define the command line options that are valid
    def options(self):
        return generic_server.GenericServerInterface.options(self)+\
	       ["config_file=", "test"]


if __name__ == "__main__" :
    Trace.init(string.upper(MY_NAME))

    # get the interface
    intf = LoggerInterface()

    logserver = Logger((intf.config_host, intf.config_port), intf.test)
    logserver.handle_generic_commands(intf)
    
    while 1:
        try:
            logserver.serve_forever()
	except SystemExit, exit_code:
	    sys.exit(exit_code)
        except:
	    logserver.serve_forever_error(logserver.log_name)
            continue
