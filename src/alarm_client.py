# system imports
#
import sys
import os
import pwd
import errno
import types

# enstore imports
import generic_client
import udp_client
import option
import enstore_constants
import Trace
import e_errors

MY_NAME = "ALARM_CLIENT"
MY_SERVER = "alarm_server"

RCV_TIMEOUT = 5
RCV_TRIES = 2

class Lock:
    def __init__(self):
        self.locked = 0
    def unlock(self):
        self.locked = 0
        return None
    def test_and_set(self):
        s = self.locked
        self.locked=1
        return s

class AlarmClient(generic_client.GenericClient):

    def __init__(self, csc, rcv_timeout=RCV_TIMEOUT, rcv_tries=RCV_TRIES,
		 flags=0):
        # need the following definition so the generic client init does not
        # get another alarm client
	flags = flags | enstore_constants.NO_ALARM
        generic_client.GenericClient.__init__(self, csc, MY_NAME, flags=flags)
        try:
            self.uid = pwd.getpwuid(os.getuid())[0]
        except:
            self.uid = "unknown"
        self.server_address = self.get_server_address(MY_SERVER, 10, 1)

        self.rcv_timeout = rcv_timeout
        self.rcv_tries = rcv_tries
        Trace.set_alarm_func( self.alarm_func )
        self.alarm_func_lock = Lock() 
        
    def alarm_func(self, time, pid, name, root_error, 
		   severity, args):
        # prevent infinite recursion (i.e if some function call by this
        # function does a trace and the alarm bit is set
        if self.alarm_func_lock.test_and_set(): return None
	# translate severity to text
	if type(severity) == types.IntType:
	    severity = e_errors.sevdict.get(severity, 
					    e_errors.sevdict[e_errors.ERROR])
        ticket = {}
        ticket['work'] = "post_alarm"
        ticket[enstore_constants.UID] = self.uid
        ticket[enstore_constants.PID] = pid
        ticket[enstore_constants.SOURCE] = name
	ticket[enstore_constants.SEVERITY] = severity
	ticket[enstore_constants.ROOT_ERROR] = root_error
	ticket['text'] = args
	log_msg = "%s, %s (severity : %s)"%(root_error, args, severity)

        self.send(ticket, self.rcv_timeout, self.rcv_tries )
        # log it for posterity
        Trace.log(e_errors.ALARM, log_msg, Trace.MSG_ALARM)
        return self.alarm_func_lock.unlock()

    def alarm(self, severity=e_errors.DEFAULT_SEVERITY, \
              root_error=e_errors.DEFAULT_ROOT_ERROR,
              alarm_info=None):
        if alarm_info is None:
            alarm_info = {}
        Trace.alarm(severity, root_error, alarm_info )

    def resolve(self, id):
        # this alarm has been resolved.  we need to tell the alarm server
        ticket = {'work' : "resolve_alarm",
                  enstore_constants.ALARM   : id}
        return self.send(ticket, self.rcv_timeout, self.rcv_tries)

    def get_patrol_file(self):
        ticket = {'work' : 'get_patrol_filename'}
        return self.send(ticket, self.rcv_timeout, self.rcv_tries)

class AlarmClientInterface(generic_client.GenericClientInterface):


    def __init__(self, args=sys.argv, user_mode=1):
        #self.do_parse = flag
        #self.restricted_opts = opts
        # fill in the defaults for the possible options
        # we always want a default timeout and retries so that the alarm
        # client/server communications does not become a weak link
        self.alive_rcv_timeout = RCV_TIMEOUT
        self.alive_retries = RCV_TRIES
        self.alarm = 0
        self.resolve = 0
        self.dump = 0
        self.severity = e_errors.DEFAULT_SEVERITY
        self.root_error = e_errors.DEFAULT_ROOT_ERROR
        self.get_patrol_file = 0
        generic_client.GenericClientInterface.__init__(self, args=args,
                                                       user_mode=user_mode)

    def valid_dictionaries(self):
        return (self.help_options, self.trace_options, self.alive_options,
                self.alarm_options)

    alarm_options = {
        option.DUMP:{option.HELP_STRING:
                        "print (stdout) alarms the alarm server has in memory",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.VALUE_USAGE:option.IGNORED,
                     option.USER_LEVEL:option.ADMIN,
                              },
        option.RAISE:{option.HELP_STRING:"raise an alarm",
                      option.DEFAULT_TYPE:option.INTEGER,
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.DEFAULT_NAME:"alarm",
                      option.VALUE_USAGE:option.IGNORED,
                      option.USER_LEVEL:option.ADMIN,
                      },
        option.RESOLVE:{option.HELP_STRING:
                        "resolve the previously raised alarm whose key "
                        "matches the entered value",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"key",
                        option.USER_LEVEL:option.ADMIN,
                        },
        option.ROOT_ERROR:{option.HELP_STRING:
                           "error which caused an alarm to be raised "
                           "[D: UNKONWN]",
                           option.VALUE_TYPE:option.STRING,
                           option.VALUE_USAGE:option.REQUIRED,
                           option.VALUE_LABEL:"node_name",
                           option.USER_LEVEL:option.ADMIN,
                           },
        option.SEVERITY:{option.HELP_STRING:"severity of raised alarm "
                         "(E, U, W, I, M)[D: W]",
                         option.VALUE_NAME:"severity",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"severity",
                         option.USER_LEVEL:option.ADMIN,
                         },
        }

def do_work(intf):
    # now get an alarm client
    alc = AlarmClient((intf.config_host, intf.config_port),
                      intf.alive_rcv_timeout, intf.alive_retries)
    Trace.init(alc.get_name(MY_NAME))
    ticket = alc.handle_generic_commands(MY_SERVER, intf)
    if ticket:
        pass

    elif intf.resolve:
        ticket = alc.resolve(intf.resolve)

    elif intf.dump:
        ticket = alc.dump()

    elif intf.alarm:
        alc.alarm(intf.severity, intf.root_error)
        ticket = {}

    else:
        intf.print_help()
        sys.exit(0)
    alc.check_ticket(ticket)

if __name__ == "__main__" :
    Trace.init(MY_NAME)
    Trace.trace(6,"alrmc called with args "+repr(sys.argv))
    # fill in interface
    intf = AlarmClientInterface(user_mode=0)

    do_work(intf)
