#
# system import
import sys
import time
import string
import os
import stat
import string

# enstore imports
import Trace
import alarm
import enstore_html
import enstore_functions
import enstore_status
import enstore_constants
import e_errors
import www_server

TRUE = 1
FALSE = 0
TMP = ".tmp"
START_TIME = "start_time"
STOP_TIME = "stop_time"
LOG_PREFIX = "LOG-"

# ENCP line pieces from log file
ETIME = 0
ENODE = 1
EUSER = 2
ESTATUS = 3
ETEXT = 4
EXRATE = 4
EBYTES = 5
EDEV = 6
EURATE = 7
EDICTS = 8
ETYPE = 9

# message is either a mount request or an actual mount
MREQUEST = 0
MMOUNT = 1

# different MOUNT line pieces from log file
MDEV = 4
MSTART = 5
MDICTS = 6

default_dir = "./"

def inq_file_name():
    return "enstore_system.html"

def default_inq_file():
    return "%s%s"%(default_dir, inq_file_name())

def encp_html_file_name():
    return "encp_%s"%(inq_file_name(),)

def default_encp_html_file():
    return "%s%s"%(default_dir, encp_html_file_name())

def config_html_file_name():
    return "config_%s"%(inq_file_name(),)

def default_config_html_file():
    return "%s%s"%(default_dir, config_html_file_name())

def misc_html_file_name():
    return "misc_%s"%(inq_file_name(),)

def default_misc_html_file():
    return "%s%s"%(default_dir, misc_html_file_name())

def plot_html_file_name():
    return "plot_%s"%(inq_file_name(),)

def default_plot_html_file():
    return "%s%s"%(default_dir, plot_html_file_name())

def status_html_file_name():
    return "status_%s"%(inq_file_name(),)

def default_status_html_file():
    return "%s%s"%(default_dir, status_html_file_name())

class EnFile:

    def __init__(self, file, system_tag=""):
        self.file_name = file 
        self.real_file_name = file 
	self.openfile = 0
	self.system_tag = system_tag

    def open(self, mode='w'):
	try:
            self.openfile = open(self.file_name, mode)
            Trace.trace(10,"%s open "%(self.file_name,))
        except IOError:
            self.openfile = 0
            Trace.log(e_errors.WARNING,
                      "%s not openable for %s"%(self.file_name, mode))

    # write it to the file
    def write(self, data):
        if self.openfile:
            self.openfile.write(str(data))

    def close(self):
	Trace.trace(10,"enfile close %s"%(self.file_name,))
	if self.openfile:
	    self.openfile.close()
	    self.openfile = 0

    def install(self):
	# copy the file we created to the real file name
	if not self.real_file_name == self.file_name:
	    os.system("mv %s %s"%(self.file_name, self.real_file_name))

    # remove the file
    def cleanup(self, keep, pts_dir):
        if not keep:
            # delete the data file
            os.remove(self.file_name)
        else:
            if pts_dir:
                # move these files somewhere, do a copy and remove in case we
                # are moving across disks
                os.system("cp %s %s"%(self.file_name, pts_dir))
                os.remove(self.file_name)

class EnStatusFile(EnFile):

    def __init__(self, file, system_tag=""):
     	EnFile.__init__(self, file, system_tag)
	self.text = {}

    # open the file
    def open(self):
        Trace.trace(12,"open %s"%(self.file_name,))
        # try to open status file for append
        EnFile.open(self, 'a')
        if not self.openfile:
            # could not open for append, try to create it
            EnFile.open(self, 'w')

    # remove something from the text hash that will be written to the files
    def remove_key(self, key):
	if self.text.has_key(key):
	    del self.text[key]
    
    def set_refresh(self, refresh):
	self.refresh = refresh

    def get_refresh(self):
	return self.refresh

class HTMLStatusFile(EnStatusFile, enstore_status.EnStatus):

    def __init__(self, file, refresh, system_tag=""):
	EnStatusFile.__init__(self, file, system_tag)
	self.refresh = refresh

    def set_alive_error_status(self, key):
	self.text[key][enstore_constants.STATUS][0] = "error"

    # write the status info to the file
    def write(self):
        if self.openfile:
	    doc = enstore_html.EnSysStatusPage(self.refresh, self.system_tag)
	    doc.body(self.text)
            self.openfile.write(str(doc))

class HTMLEncpStatusFile(EnStatusFile):

    def __init__(self, file, refresh, system_tag=""):
	EnStatusFile.__init__(self, file, system_tag)
	self.refresh = refresh

    # output the encp info
    def write(self, lines):
        if self.openfile:
	    # break up each line into it's component parts and format it
	    eline = []
	    for line in lines:
		einfo = enstore_status.parse_encp_line(line)
		if len(einfo) and einfo[ESTATUS] == e_errors.sevdict[e_errors.INFO]:
		    eline.append([einfo[ETIME], einfo[ENODE], einfo[EUSER], 
				  einfo[EBYTES], einfo[EDEV], einfo[EXRATE], 
				  einfo[EURATE]])
		elif len(einfo) and einfo[ESTATUS] == e_errors.sevdict[e_errors.ERROR]:
		    # remove the MSG_TYPE=XXXXX from the output text
		    txt = string.split(einfo[ETEXT], Trace.MSG_TYPE)
		    eline.append([einfo[ETIME], einfo[ENODE], einfo[EUSER], txt[0]])
	    else:
		doc = enstore_html.EnEncpStatusPage(refresh=self.refresh, 
						    system_tag=self.system_tag)
		doc.body(eline)
            self.openfile.write(str(doc))

class HTMLLogFile(EnFile):

    # format the log files and write them to the file, include a link to the
    # page to search the log files
    def write(self, http_path, logfiles, user_logs, host):
        if self.openfile:
	    doc = enstore_html.EnLogPage(system_tag=self.system_tag)
	    doc.body(http_path, logfiles, user_logs, host)
            self.openfile.write(str(doc))

class HTMLConfigFile(EnFile):

    # format the config entry and write it to the file
    def write(self, cdict):
        if self.openfile:
	    doc = enstore_html.EnConfigurationPage(system_tag=self.system_tag)
	    doc.body(cdict)
            self.openfile.write(str(doc))

class HTMLPlotFile(EnFile):

    # format the config entry and write it to the file
    def write(self, jpgs, stamps, pss):
        if self.openfile:
	    doc = enstore_html.EnPlotPage(system_tag=self.system_tag)
	    doc.body(jpgs, stamps, pss)
            self.openfile.write(str(doc))

class HTMLMiscFile(EnFile):

    # format the file name and write it to the file
    def write(self, data):
        if self.openfile:
	    doc = enstore_html.EnMiscPage(system_tag=self.system_tag)
	    doc.body(data)
            self.openfile.write(str(doc))

class EnDataFile(EnFile):

    # make the data file by grepping the inFile.  fproc is any further
    # processing that must be done to the data before it is written to
    # the ofile.
    def __init__(self, inFile, oFile, text, indir="", fproc=""):
	EnFile.__init__(self, oFile)
	self.lines = []
	self.data = []
	if not indir:
	    cdcmd = " "
	else:
	    cdcmd = "cd %s;"%(indir,)
	try:
	    os.system(cdcmd+"grep "+text+" "+inFile+fproc+"> "+oFile)
	except:
	    self.file_name = ""
            exc, msg, tb=sys.exc_info()
	    format = "%s: inquisitor plot system error: %s" % (sys.argv,msg)
	    Trace.trace(9,"__init__ %s"%(format,))

    def read(self, max_lines):
	i = 0
	if self.openfile:
            while i < max_lines:
                l = self.openfile.readline()
                if l:
		    # THIS IS A KLUDGE - do not use any error lines which have a status=ok in 
		    # them.  remove the following if block and this comment to get rid of the
		    # kludge.
		    if not string.find(l, " E ENCP ") == -1 and \
		       not string.find(l, "STATUS=ok") == -1:
			continue
		    #
                    self.lines.append(l)
                    i = i + 1
                else:
                    break
	return self.lines

    # read in the given file and return a list of lines that are between a
    # given start and end time
    def timed_read(self, ticket):
	do_all = FALSE
        start_time = ticket.get(START_TIME, "")
        stop_time = ticket.get(STOP_TIME, "")
        if not stop_time and not start_time:
            do_all = TRUE
	# read it in.  only save the lines that match the desired time frame
        if self.openfile:
            try:
                while TRUE:
                    line = self.openfile.readline()
                    if not line:
                        break
                    else:
                        if do_all or \
                           self.check_line(line, start_time, stop_time):
                            self.lines.append(line)
            except:
                pass
	return self.lines

    # check the line to see if the date and timestamp on the beginning of it
    # is between the given start and end values
    def check_line(self, line, start_time, stop_time):
	# split the line into the date/time and all the rest
	datetime, rest = string.split(line, None, 1)
	# remove the beginning LOG_PREFIX
	l = string.replace(datetime, LOG_PREFIX,"")
	# now see if the date/time is between the start time and the end time
	time_ok = TRUE
	if start_time:
	    if l < start_time:
	        time_ok = FALSE
	if time_ok and stop_time:
	    if l > stop_time:
	        time_ok = FALSE
	return time_ok

class EnMountDataFile(EnDataFile):

    # parse the mount line
    def parse_line(self, line):
	[etime, enode, etmp, euser, estatus, dev, type, erest] = \
                                                   string.split(line, None, 7)
	if type == string.rstrip(Trace.MSG_MC_LOAD_REQ) :
	    # this is the request for the mount
	    start = MREQUEST
	else:
	    start = MMOUNT

	# parse out the file directory , a remnant from the grep in the time 
	# field
	enstore_functions.strip_file_dir(etime)

        # pull out any dictionaries from the rest of the message
        msg_dicts = enstore_status.get_dict(erest)

	return [etime, enode, euser, estatus, dev, start, msg_dicts]

    # pull out the plottable data from each line that is from one of the
    # specified movers
    def parse_data(self, mcs):
	for line in self.lines:
	    minfo = self.parse_line(line)
            if not mcs or enstore_status.mc_in_list(minfo[MDICTS], mcs):
                self.data.append([minfo[MDEV], string.replace(minfo[ETIME],
                                                              LOG_PREFIX, ""),
                                  minfo[MSTART]])

class EnEncpDataFile(EnDataFile):

    # parse the encp line
    def parse_line(self, line):
	einfo = enstore_status.parse_encp_line(line)
        if not len(einfo):
            # nothing was returned skip this line
            return []
        # the time info may contain the file directory which we must
        # strip off
        enstore_functions.strip_file_dir(einfo[ETIME])
        return [einfo[ETIME], einfo[EBYTES], einfo[EDICTS], einfo[ETYPE]]

    # pull out the plottable data from each line
    def parse_data(self, mcs):
	for line in self.lines:
	    einfo = self.parse_line(line)
	    if einfo and (not mcs or enstore_status.mc_in_list(einfo[2], mcs)):
	        self.data.append([string.replace(einfo[0], LOG_PREFIX, ""), \
	                         einfo[1], einfo[3]])

class HtmlAlarmFile(EnFile):

    # we need to save both the file name passed to us and the one we will
    # write to.  we will create the temp one and then move it to the real
    # one.
    def __init__(self, name, system_tag=""):
        EnFile.__init__(self, name+TMP, system_tag)
        self.real_file_name = name

    # we need to close the open file and move it to the real file name
    def close(self):
        EnFile.close(self)
        os.rename(self.file_name, self.real_file_name)

    # format the file name and write it to the file
    def write(self, data, www_host):
        if self.openfile:
	    doc = enstore_html.EnAlarmPage(system_tag=self.system_tag)
	    doc.body(data, www_host)
            self.openfile.write(str(doc))

class HTMLPatrolFile(EnFile):

    # we need to save both the file name passed to us and the one we will
    # write to.  we will create the temp one and then move it to the real
    # one.
    def __init__(self, name, system_tag=""):
        EnFile.__init__(self, name+TMP, system_tag)
        self.real_file_name = name

    # we need to close the open file and move it to the real file name
    def close(self):
        EnFile.close(self)
        os.rename(self.file_name, self.real_file_name)

    # format the file name and write it to the file
    def write(self, data):
        if self.openfile:
	    doc = enstore_html.EnPatrolPage(system_tag=self.system_tag)
	    doc.body(data)
            self.openfile.write(str(doc))

class EnAlarmFile(EnFile):

    # open the file, if no mode is passed in, try opening for append and
    # then write
    def open(self, mode=""):
        if mode:
            EnFile.open(self, mode)
        else:
            EnFile.open(self, "a")
            if not self.openfile:
                # the open for append did not work, now try write
                EnFile.open(self, "w")

    # read lines from the file
    def read(self):
        enAlarms = {}
        if self.openfile:
            try:
                while TRUE:
                    line = self.openfile.readline()
                    if not line:
                        break
                    else:
                        theAlarm = alarm.AsciiAlarm(line)
                        enAlarms[theAlarm.id] = theAlarm
            except IOError:
                pass
        return enAlarms
                
    # write the alarm to the file
    def write(self, alarm):
        if self.openfile:
            line = repr(alarm)+"\n"
            try:
                self.openfile.write(line)
            except IOError:
                pass

class EnPatrolFile(EnFile):

    # we need to save both the file name passed to us and the one we will
    # write to.  we will create the temp one and then move it to the real
    # one.
    def __init__(self, name):
        EnFile.__init__(self, name+TMP)
        self.real_file_name = name
        self.lines = []

    # we need to close the open file and move it to the real file name
    def close(self):
        EnFile.close(self)
        os.rename(self.file_name, self.real_file_name)

    # write out the alarm
    def write(self, alarm):
        if self.openfile:
            # tell the alarm that this is going to patrol so the alarm
            # can add the patrol expected header
            self.openfile.write(alarm.prepr())

    # rm the file
    def remove(self):
        try:
            if self.real_file_name and os.path.exists(self.real_file_name):
                os.remove(self.real_file_name)
        except IOError:
            # file does not exist
            pass

class HtmlSaagFile(EnFile):

    # we need to save both the file name passed to us and the one we will
    # write to.  we will create the temp one and then move it to the real
    # one.
    def __init__(self, name, system_tag=""):
        EnFile.__init__(self, name+TMP, system_tag)
        self.real_file_name = name

    def write(self, enstore_contents, network_contents, media_contents, 
	      alarm_contents, node_contents, outage, offline):
	if self.openfile:
	    doc = enstore_html.EnSaagPage(system_tag=self.system_tag)
	    media = enstore_functions.get_from_config_file(www_server.WWW_SERVER,
							   www_server.MEDIA_TAG,
							   www_server.MEDIA_TAG_DEFAULT)
	    doc.body(enstore_contents, network_contents, media_contents, 
		     alarm_contents, node_contents, outage, offline, media)
	    self.openfile.write(str(doc))

class ScheduleFile(EnFile):

    def __init__(self, dir, name):
	self.html_dir = dir
        EnFile.__init__(self, "%s/%s"%(dir, name))

    def read(self):
	# get the contents of the file by just importing it
	sys.path.append(self.html_dir)
	try:
	    import enstore_outage
	    try:
		outage_d = enstore_outage.outage
	    except AttributeError:
		outage_d = {}
	    try:
		offline_d = enstore_outage.offline
	    except AttributeError:
		offline_d = {}
	except ImportError:
	    # can't find the module
	    outage_d = {}
	    offline_d = {}
	return outage_d, offline_d

    # turn the dictionary into python code to be written out to the file
    def write(self, dict1, dict2):
	# open the file for writing
	self.open()

	# write out the dictionary
	if self.openfile:
	    self.openfile.write("outage = %s\n"%(dict1,))
	    self.openfile.write("offline = %s\n"%(dict2,))
	    rtn = 1
	    # close the file
	    self.close()
	else:
	    # could not open the file
	    rtn = 0
	return rtn
