###############################################################################
# src/$RCSfile$   $Revision$
#
#########################################################################
#                                                                       #
# Mover client.                                                         #
# Mover access methods                                                  #
#                                                                       #
#########################################################################

# system imports
import sys
import string
import pprint

#enstore imports
import udp_client
import interface
import generic_client
import Trace

class MoverClient(generic_client.GenericClient):
    def __init__(self, csc, name=""):
        self.mover=name
        self.log_name = "C_"+string.upper(name)
        generic_client.GenericClient.__init__(self, csc, self.log_name)
        self.u = udp_client.UDPClient()
        self.server_address = self.get_server_address(self.mover)

    def status(self, rcv_timeout=0, tries=0):
        return self.send({"work" : "status"}, rcv_timeout, tries)

    def clean_drive(self, rcv_timeout=0, tries=0):
        return self.send({"work":"clean_drive"}, rcv_timeout, tries)

    def start_draining(self, rcv_timeout=0, tries=0):
        return self.send({"work" : "start_draining"}, rcv_timeout, tries)

    def stop_draining(self, rcv_timeout=0, tries=0):
        return self.send({"work" : "stop_draining"}, rcv_timeout, tries)

    def warm_restart(self, rcv_timeout=0, tries=0):
        return self.send({"work" : "warm_restart"}, rcv_timeout, tries)

    def device_dump(self, sendto=[], notify=[], rcv_timeout=0, tries=0):
        # print "device_dump(self, sendto="+`sendto`+', notify='+`notify`+', rcv_timeout='+`rcv_timeout`+', tries='+`tries`+')'
        return self.send({"work" : "device_dump_S",
                          "sendto" : sendto,
                          "notify" : notify}, rcv_timeout, tries)

class MoverClientInterface(generic_client.GenericClientInterface):
    def __init__(self, flag=1, opts=[]):
        self.do_parse = flag
        self.restricted_opts = opts
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.mover = ""
        self.local_mover = 0
        self.clean_drive = 0
        self.enable = 0
        self.status = 0
        self.start_draining = 0
        self.stop_draining = 0
        self.notify = []
        self.sendto = []
        self.dump = 0
        self.warm_restart = 0
        generic_client.GenericClientInterface.__init__(self)
        
    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            # start draining needs a parameter because the library manager uses the same
            # option and it needs a parameter.  the interface is dumb enough not to know
            # the difference between the mover and the library manager.
            return self.client_options()+["status", "clean-drive", "offline",
                                          "down", "start-draining=",
                                          "stop-draining", "online",
                                          "up", "sendto=", "notify=",
                                          "dump", "warm-restart"]

    #  define our specific help
    def parameters(self):
        return "mover"

    # parse the options like normal but make sure we have a mover name
    def parse_options(self):
        interface.Interface.parse_options(self)
        # bomb out if we don't have a mover
        if len(self.args) < 1 :
            self.missing_parameter(self.parameters())
            self.print_help()
            sys.exit(1)
        else:
            #If the user opted not to add the ".mover" to the end of the
            # server, then it should be concatenated.
            try:
                if self.args[0][-6:] != ".mover":
                    self.mover = self.args[0] + ".mover"
                else:
                    self.mover = self.args[0]
            except IndexError:
                #The string does not contain enough characters to end in
                # ".mover".  So, it must be added.
                self.mover = self.args[0] + ".mover"


def do_work(intf):
    # get a mover client
    movc = MoverClient((intf.config_host, intf.config_port), intf.mover)
    Trace.init(movc.get_name(movc.log_name))

    ticket = {}
    msg_id = None

    ticket = movc.handle_generic_commands(intf.mover, intf)
    if ticket:
        pass

    elif intf.status:
        ticket = movc.status(intf.alive_rcv_timeout,intf.alive_retries)
        pprint.pprint(ticket)
    elif intf.local_mover:
        ticket = movc.local_mover(intf.enable, intf.alive_rcv_timeout,
                                  intf.alive_retries)
    elif intf.clean_drive:
        ticket = movc.clean_drive(intf.alive_rcv_timeout, intf.alive_retries)
        print ticket
    elif intf.start_draining:
        ticket = movc.start_draining(intf.alive_rcv_timeout, intf.alive_retries)
    elif intf.stop_draining:
        ticket = movc.stop_draining(intf.alive_rcv_timeout, intf.alive_retries)
    elif intf.warm_restart:
        ticket = movc.warm_restart(intf.alive_rcv_timeout, intf.alive_retries)
    elif intf.dump:
        ticket = movc.device_dump(intf.sendto, intf.notify, intf.alive_rcv_timeout, intf.alive_retries)
    else:
        intf.print_help()
        sys.exit(0)

    movc.check_ticket(ticket)

if __name__ == "__main__" :
    Trace.init("MOVER_CLI")
    Trace.trace(6,"movc called with args "+repr(sys.argv))

    # fill in the interface
    intf = MoverClientInterface()

    do_work(intf)
