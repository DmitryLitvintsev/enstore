###############################################################################
# src/$RCSfile$   $Revision$
#
#########################################################################
#                                                                       #
# Media Changer client.                                                 #
# Media Changer access methods                                          #
#                                                                       #
#########################################################################

#system imports
import sys
import string
import types
import pprint

#enstore imports
import udp_client
import interface
import generic_client
import Trace
import volume_clerk_client
import e_errors

MY_NAME = ".MC"

class MediaChangerClient(generic_client.GenericClient):
    def __init__(self, csc, name=""):
        self.media_changer=name
        self.log_name = "C_"+string.upper(string.replace(name,
                                                         ".media_changer",
                                                         MY_NAME))
        generic_client.GenericClient.__init__(self, csc, self.log_name)
        self.u = udp_client.UDPClient()
        self.server_address = self.get_server_address(name)


    def loadvol(self, vol_ticket, mover, drive):
	ticket = {'work'           : 'loadvol',
                  'vol_ticket'     : vol_ticket,
                  'drive_id'       : drive
                  }
	rt = self.send(ticket, 300, 10)
        if rt['status'][0] != e_errors.OK:
            Trace.log(e_errors.ERROR, "loadvol %s" % (rt['status'],))
        return rt

    def unloadvol(self, vol_ticket, mover, drive):
        ticket = {'work'           : 'unloadvol',
                  'vol_ticket' : vol_ticket,
                  'drive_id'       : drive
                  }
	rt = self.send(ticket,300,10)
        if rt['status'][0] != e_errors.OK:
            Trace.log(e_errors.ERROR, "unloadvol %s" % (rt['status'],))
        return rt

    def viewvol(self, volume, m_type):
        ticket = {'work' : 'viewvol',
                  'external_label' : volume,
                  'media_type' : m_type
                     }
	rt = self.send(ticket)
        return rt

    def doCleaningCycle(self, moverConfig):
        ticket = {'work'       : 'doCleaningCycle',
                  'moverConfig': moverConfig,
                  }
	rt = self.send(ticket,300,10)
        return rt

    def insertvol(self, IOarea, inNewLib):
        ticket = {'work'         : 'insertvol',
	          'IOarea_name'  : IOarea,
		  'newlib'       : inNewLib
		 }
        if type(IOarea) != types.ListType:
            Trace.log(e_errors.ERROR, "ERROR:insertvol IOarea must be a list")
	    rt = {'status':(e_errors.WRONGPARAMETER, 1, "IOarea must be a list")}
	    return rt
	zz = raw_input('Insert volumes into I/O area. Do not mix media types.\nWhen I/O door is closed hit return:')
	if zz == "FakeOpenIODoor":
	    ticket["FakeIOOpen"] = 'yes'
	rt = self.send(ticket,300,10)
        return rt

    def ejectvol(self, media_type, volumeList):
        ticket = {'work'         : 'ejectvol',
	          'volList'      : volumeList,
	          'media_type'   : media_type
                  }
        if type(volumeList) != types.ListType:
            Trace.log(e_errors.ERROR, "ERROR:ejectvol volumeList must be a list")
	    rt = {'status':(e_errors.WRONGPARAMETER, 1, "volumeList must be a list")}
	    return rt
	rt = self.send(ticket,300,10)
        return rt

    def max_work(self, max_work):
        ticket = {'work'           : 'max_work',
                  'max_work'        : max_work
                 }
        return self.send(ticket)

    def GetWork(self):
        ticket = {'work'           : 'getwork'
                 }
        return self.send(ticket)

class MediaChangerClientInterface(generic_client.GenericClientInterface):
    def __init__(self, flag=1, opts=[]):
        self.do_parse = flag
        self.restricted_opts = opts
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.media_changer = ""
        self.get_work=0
        self.max_work=-1
        self.volume = 0
	self.update = 0
	self._import = 0
	self._export = 0
        self.mount = 0
        self.dismount = 0
	self.viewattrib = 0
        self.drive = 0
        generic_client.GenericClientInterface.__init__(self)
        
    # define the command line options that are valid
    def options(self):
        if self.restricted_opts:
            return self.restricted_opts
        else:
            return self.client_options()+\
                   ["max_work=","update=","get_work","import",
                    "export","mount","dismount"]
    #  define our specific help
    def parameters(self):
        return "media_changer"

    # parse the options like normal but make sure we have other args
    def parse_options(self):
        interface.Interface.parse_options(self)
	if self._import:
            if len(self.args) < 2:
	        self.missing_parameter("--import media_changer insertNewLib")
                self.print_help()
                sys.exit(1)
            else:
                self.media_changer = self.args[0]
                self.insertNewLib = self.args[1]
		self.ioarea = []
		if len(self.args) > 2:
		    for pos in range(2,len(self.args)):
		        self.ioarea.append(self.args[pos])
	elif self._export:
            if len(self.args) < 3:
	        self.missing_parameter("--export media_changer media_type volumeList")
                self.print_help()
                sys.exit(1)
            else:
                self.media_changer = self.args[0]
                self.media_type = self.args[1]
		self.volumeList = []
		for pos in range(2,len(self.args)):
		    self.volumeList.append(self.args[pos])
	elif self.mount:
            if len(self.args) < 3:
	        self.missing_parameter("--mount media_changer external_label drive")
                self.print_help()
                sys.exit(1)
            else:
                self.media_changer = self.args[0]
                self.volume=self.args[1]
                self.drive = self.args[2]
	elif self.dismount:
            if len(self.args) < 3:
	        self.missing_parameter("--dismount media_changer external_lable drive")
                self.print_help()
                sys.exit(1)
            else:
                self.media_changer = self.args[0]
                self.volume=self.args[1]
                self.drive = self.args[2]
	else:
            if len(self.args) < 1 :
	        self.missing_parameter("media_changer")
                self.print_help()
                sys.exit(1)
            else:
                self.media_changer = self.args[0]

    # print out our extended help
    def print_help(self):
        interface.Interface.print_help(self)
        #print "        --max_work=N        Max simultaneous operations allowed (may be 0)"
        #print "        --get_work          List operations in progress"
        #print "        --update volume"
        #print "        --import insertNewLib [IOarea]"
        #print "        --export media_type volume1 [volume2 ...]"
        
def do_work(intf):
    # get a media changer client
    mcc = MediaChangerClient((intf.config_host, intf.config_port),
                             intf.media_changer)

    Trace.init(mcc.get_name(mcc.log_name))

    ticket = mcc.handle_generic_commands(intf.media_changer, intf)
    
    if ticket:
        pass

    elif intf.update:
        # get a volume clerk client
        vcc = volume_clerk_client.VolumeClerkClient(mcc.csc)
        v_ticket = vcc.inquire_vol(intf.update)
	volume = v_ticket['external_label']
	m_type = v_ticket['media_type']
	ticket=mcc.viewvol(volume, m_type)
	del vcc
    elif intf.mount:
        vcc = volume_clerk_client.VolumeClerkClient(mcc.csc)
        vol_ticket = vcc.inquire_vol(intf.volume)
        v = vcc.set_at_mover(intf.volume, 'mounting', intf.drive)
        vol_ticket = vcc.inquire_vol(intf.volume)
        ticket = mcc.loadvol(vol_ticket, intf.drive, intf.drive)
	del vcc
    elif intf.dismount:
        vcc = volume_clerk_client.VolumeClerkClient(mcc.csc)
        vol_ticket = vcc.inquire_vol(intf.volume)
        v = vcc.set_at_mover(intf.volume, 'unmounting', intf.drive)
        vol_ticket = vcc.inquire_vol(intf.volume)
        ticket = mcc.unloadvol(vol_ticket, intf.drive, intf.drive)
    elif intf._import:
	ticket=mcc.insertvol(intf.ioarea, intf.insertNewLib)
    elif intf._export:
        ticket=mcc.ejectvol(intf.media_type, intf.volumeList)
    elif intf.max_work  >= 0:
        ticket=mcc.max_work(intf.max_work)
    elif intf.get_work:
        ticket=mcc.GetWork()
        pprint.pprint(ticket)
    else:
        intf.print_help()
        sys.exit(0)

    del mcc.csc.u
    del mcc.u		# del now, otherwise get name exception (just for python v1.5???)

    mcc.check_ticket(ticket)

if __name__ == "__main__" :
    Trace.init("MEDCH CLI")
    Trace.trace(6,"mcc called with args "+repr(sys.argv))
    
    # fill in the interface
    intf = MediaChangerClientInterface()

    do_work(intf)
