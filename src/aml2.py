######################################################################
#  $Id$
#
#  Python replacement for aml2.so built on top of the aci module
#
#

#system imports
import types
import string
import time
import whrandom
import popen2
import string
import sys
import aml2_log

#enstore imports
import aci
import derrno
import volume_clerk_client
import Trace
import e_errors

status_table = (
    ("ok",	"request successful"),			                #0
    ("BAD",	"rpc failure"),			       	                #1
    ("BAD",	"aci parameter invalid "),	       	                #2
    ("TAPE",	"volume not found of this type"),		        #3
    ("DRIVE",   "drive not in Grau ATL "),			        #4
    ("DRIVE",   "the requested drive is in use"),		        #5
    ("TAPE",	"the robot has a physical problem with the volume"),	#6
    ("BAD",	"an internal error in the AMU "),		        #7
    ("BAD",	"the DAS was unable to communicate with the AMU"),	#8
    ("BAD",	"the robotic system is not functioning"),	        #9
    ("BAD",	"the AMU was unable to communicate with the robot"),	#10
    ("BAD",	"the DAS system is not active "),		        #11
    ("DRIVE",   "the drive did not contain an unloaded volume"),	#12
    ("BAD",	"invalid registration"),			      	#13
    ("BAD",	"invalid hostname or ip address"),		        #14
    ("BAD",	"the area name does not exist "),		        #15
    ("BAD",	"the client is not authorized to make this request"),   #16
    ("BAD",	"the dynamic area became full, insertion stopped"),	#17
    ("DRIVE",   "the drive is currently available to another client"),  #18
    ("BAD",	"the client does not exist "),			        #19
    ("BAD",	"the dynamic area does not exist"),		        #20
    ("BAD",	"no request exists with this number"),	                #21
    ("BAD",	"retry attempts exceeded"),		                #22
    ("TAPE",	"requested volser is not mounted"),		        #23
    ("TAPE",	"requested volser is in use "),			        #24
    ("BAD",	"no space available to add range"),	        	#25
    ("BAD",	"the range or object was not found"),	        	#26
    ("BAD",	"the request was cancelled by aci_cancel()"),       	#27
    ("BAD",	"internal DAS error"),     				#28
    ("BAD",	"internal ACI error"),		        		#29
    ("BAD",	"for a query more data are available"),	        	#30
    ("BAD",	"things don't match together"),		        	#31
    ("TAPE",	"volser is still in another pool"),	                #32
    ("DRIVE",   "drive in cleaning"),		        		#33
    ("BAD",	"The aci request timed out"),		        	#34
    ("DRIVE",   "the robot has a problem with handling the device"),	#35
    ("notused", "not used"),                                            #36
    # non aci errors:
    ("ERROR",   "command error"),                                       #37
    ("ERROR",   "vcc.new_library error(s)"),                            #38
    )

def convert_status(int_status):
    status = int_status
    if status > len(status_table):  #invalid error code
        status = derrno.EDASINT
    return status_table[status][0], status, status_table[status][1]    


def mount(volume, drive, media_type,view_first=1):
    status = 0
    
    if view_first:
        v = view(volume,media_type)
        if v[0] != 'ok':
            status = v[1]
            return status_table[status][0], status, status_table[status][1]
        elif v[5] != 'O':
            return 'BAD',99,'Tape is not in home position in tower: %s'%(v,)
        
    media_code = aci.__dict__.get("ACI_"+media_type)
    if media_code is None:
        status = derrno.ENOVOLUME
    elif aci.aci_mount(volume,media_code,drive):  #note order of args!
        status = aci.cvar.d_errno
        if status > len(status_table):  #invalid error code
            status = derrno.EDASINT
    
    return status_table[status][0], status, status_table[status][1]    
    

def dismount(volume, drive, media_type,view_first=1):
    status = 0

    if view_first:
        v = view(volume,media_type)
        if v[0] != 'ok':
            status = v[1]
            return status_table[status][0], status, status_table[status][1]
        elif v[5] != 'M':
            return 'BAD',99,'Tape is not in mounted in drive: %s'%(v,)

    if aci.aci_force(drive):
        status=aci.cvar.d_errno
        if status > len(status_table):
            status = derrno.EDASINT

    return status_table[status][0], status, status_table[status][1]    

# home robot arm
def robotHome(arm):
    status = aci.aci_robhome(arm)
    if not status:
        status = aci.aci_robstat(arm,"start")
    return status_table[status][0], status, status_table[status][1]

# get status of robot
def robotStatus():
    status = aci.aci_robstat("\0","stat")
    return status_table[status][0], status, status_table[status][1]

#start robot arm
def robotStart(arm):
    status = aci.aci_robstat(arm,"start")
    return status_table[status][0], status, status_table[status][1]

# home and start robot arm
def robotHomeAndRestart(ticket, classTicket):
    arm = ticket["robotArm"]
    status = 37
    if arm=='R1' or arm=='Both':
        st1,status,st2 = robotHome('R1')
        if not status:
            st1,status,st2 = robotStart('R1')
	    if status:
                Trace.trace(e_errors.INFO, 'aml2 robotHomeAndRestart Start failed on R1')
                return status_table[status][0], status, status_table[status][1]
	else:
            Trace.trace(e_errors.INFO, 'aml2 robotHomeAndRestart Home failed on R1')
            return status_table[status][0], status, status_table[status][1]
    if arm=='R2' or arm=='Both':
        st1,status,st2 = robotHome('R2')
        if not status:
            st1,status,st2 = robotStart('R2')
	    if status:
                Trace.trace(e_errors.INFO, 'aml2 robotHomeAndRestart Start failed on R2')
                return status_table[status][0], status, status_table[status][1]
	else:
            Trace.trace(e_errors.INFO, 'aml2 robotHomeAndRestart Home failed on R2')
            return status_table[status][0], status, status_table[status][1]
    return status_table[status][0], status, status_table[status][1]

def view(volume, media_type):
    status = 0
    media_code = aci.__dict__.get("ACI_"+media_type)

    if media_code is None:
        status = derrno.ENOVOLUME
        return ('TAPE', 3, 'volume not found of this type', '', '\000', '\000', media_type, volume, '\000', 0, 0)
    else:
        v = aci.aci_view(volume,media_code)
        if v[0]:
            status = aci.cvar.d_errno
            if status > len(status_table):  #invalid error code
                status = derrno.EDASINT
    
    return status_table[status][0], status, status_table[status][1],\
           v[1].coord, v[1].owner, v[1].attrib, v[1].type, v[1].volser, \
           v[1].vol_owner, v[1].use_count, v[1].crash_count
	   
#sift through a list of lists
def yankList(listOfLists, listPosition, look4String):
    newRecordList = []
    for record in listOfLists:
	if string.find(record[listPosition],look4String)>-1:
	    newRecordList.append(record)
    return newRecordList    
    
def insert(ticket, classTicket):
    if classTicket.has_key("mcSelf"):
        mcSelf = classTicket["mcSelf"]
    else:
        status = 37
        mcSelf.workQueueClosed = 0
        Trace.trace(e_errors.ERROR, 'aml2 no mcSelf field found in ticket.')
        return status_table[status][0], status, 'aml2 no mcSelf field found in ticket.'
    
    mediaAssgn = ticket['medIOassign']
    Iareas = []
    for media in mediaAssgn.keys():
        for box in mediaAssgn[media]:
            Iareas.append("I"+box[1:])

    status = 0
    if ticket.has_key("IOarea_name") and len(ticket["IOarea_name"])>0:
        IOarea_input = ticket["IOarea_name"]
	for IOarea_name in IOarea_input:
	    if IOarea_name not in Iareas:
	        status = derrno.EINVALID
                mcSelf.workQueueClosed = 0
                Trace.trace(e_errors.ERROR, 'aml2 bad IOarea parameter specified.')
	        return status_table[status][0], status, status_table[status][1]
        areaList = IOarea_input
    else:
        areaList = list(Iareas)

    timeL1 = time.time()
    timeCmd = ticket["timeOfCmd"]
    time.sleep(90)  # let robot-IOarea door open and start inventory
                    # helps for clock skew between adic2 and mc host

    robot_host = "adic2.fnal.gov"
    year, month, day, hour, minute = time.localtime(timeL1)[:5]
    outfileName = "/tmp/aml2Log%02d%02d" % (day, month)

    mcSelf.workQueueClosed = 0

    while timeL1-timeCmd>1200:   # timeout in seconds
        #get amulog from adic2
        Trace.trace(e_errors.INFO, 'aml2 fetching log...')
        aml2_log.fetch_log_file(robot_host, month, day, outfileName)

	if ticket.has_key('FakeIOOpen'):
	    time.sleep(5)
            Trace.trace(e_errors.INFO, 'aml2: Fake IO Door Open')
	    break

        # examine the log - get INVT records
        ofile = open(outfileName,'r')
        recordCount = aml2_log.n_records(outfileName)
        Irecord = []
        for recordPointer in range(recordCount-1,0,-1):
            record = aml2_log.get_record(ofile, recordPointer)
	    if string.find(record[3],"INVT")>-1:
	        if timeCmd<record[0]:  #comment out 4dbug
	            Irecord.append(record)
        ofile.close()

        if len(Irecord) == 0:
            status = 37
            mcSelf.workQueueClosed = 0
            Trace.trace(e_errors.ERROR, 'aml2 no INVT records found.')
            return status_table[status][0], status, 'aml2 no INVT records found.'

	ESrecord = yankList(Irecord, 3, "INVT of E")
	EFrecord = []
	for record in ESrecord:
	    look4 = record[3][5:9]+" "+record[3][:4]
	    EFrecord = EFrecord+yankList(Irecord, 3, look4)
	if len(ESrecord) == len(EFrecord):
	    break
	timeL1 = time.time()

    # do insert command...
    bigVolList = []
    for area in areaList:
	Trace.trace(e_errors.INFO, 'aml2 InsertVol IOarea: %s' % (area,))
	result = aci.aci_insert(area)   # aci insert command
	res = result[0]
	media_code = result[-1]
	volser_ranges = result[1:-1]
	###XXX this is a little ugly... but it works.
	### we could fix up aci_typemaps to return the volser_ranges in
	### a sublist, but life is short
        Trace.trace(e_errors.INFO, 'aml2 aci_insert: %i %i' % (res,media_code))
        if res:
            status = aci.cvar.d_errno
            if status > len(status_table):  #invalid error code
                status = derrno.EDASINT
            Trace.trace(e_errors.ERROR, 'aml2 insert failed %s' % (status_table[status][1],))
	for strList in volser_ranges:
	    pieces = string.split(strList,', ')
	    for vol_label in pieces:
	        if len(vol_label)>0:
		    info = vol_label, res
	            bigVolList.append(info)

    # set library name to ticket["newlib"]
    vcc = volume_clerk_client.VolumeClerkClient(mcSelf.csc)
    for info in bigVolList:
        if not info[1]:
            ret = vcc.new_library(info[0],ticket["newlib"])
	    if ret['status'][0] != 'ok':
                Trace.trace(e_errors.ERROR, 'aml2 NewLib-InsertVol failed %s' % (vol_label,))
                status = 38
	    else:
                Trace.trace(e_errors.INFO, 'aml2 NewLib-InsertVol sucessful %s' % (vol_label,))

    return status_table[status][0], status, status_table[status][1]

def eject(ticket, classTicket):

    if classTicket.has_key("mcSelf"):
        mcSelf = classTicket["mcSelf"]
    else:
        status = 37
        mcSelf.workQueueClosed = 0
        Trace.trace(e_errors.ERROR, 'aml2 no mcSelf field found in ticket.')
        return status_table[status][0], status, 'aml2 no mcSelf field found in ticket.'

    mediaAssgn = ticket['medIOassign']
    status = 0
    if ticket.has_key("media_type"):
        media_type = ticket["media_type"]
        media_code = aci.__dict__.get("ACI_"+media_type)
    else:
	status = derrno.EINVALID
	return status_table[status][0], status, status_table[status][1]
    if media_code is None:
        status = derrno.ENOVOLUME
        return status_table[status][0], status, status_table[status][1]
	
    if ticket.has_key("IOarea_name"):
        IOarea_name = ticket["IOarea_name"]
	if IOarea_name not in mediaAssgn["ACI_"+media_type]:
	    status = derrno.EINVALID
	    return status_table[status][0], status, status_table[status][1]
    else:
        box = whrandom.randint(0,len(mediaAssgn["ACI_"+media_type])-1)
        IOarea_name = mediaAssgn["ACI_"+media_type][box]
    
    if ticket.has_key("volList"):
        volumeList = ticket['volList']
    else:
	status = derrno.EINVALID
	return status_table[status][0], status, status_table[status][1]
    Trace.trace(e_errors.INFO, 'aml2 aci_eject: %s %i' % (IOarea_name,media_code))

    for volser_range in volumeList:
        Trace.trace(e_errors.INFO, 'aml2 aci_eject: %s' % (volser_range))
        res = aci.aci_eject(IOarea_name, volser_range, media_code)
        if res:
            Trace.trace(e_errors.ERROR, 'aml2 aci_eject: %i' % (res,))
            status = aci.cvar.d_errno
            if status > len(status_table):  #invalid error code
                status = derrno.EDASINT
            return status_table[status][0], status, status_table[status][1]
    
    return status_table[status][0], status, status_table[status][1]
    


