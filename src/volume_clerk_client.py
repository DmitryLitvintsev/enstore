#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import sys
import string
import time
import errno
import socket
import select
import pprint
import rexec

_rexec = rexec.RExec()
def eval(stuff):
    return _rexec.r_eval(stuff)

# enstore imports
import setpath
import callback
import hostaddr
import option
import generic_client
import backup_client
import udp_client
import Trace
import e_errors
import file_clerk_client
import cPickle

MY_NAME = "VOLUME_C_CLIENT"
MY_SERVER = "volume_clerk"


#turn byte count into a nicely formatted string
def capacity_str(x,mode="GB"):
    if mode == "GB":
        z = x/1024./1024./1024. # GB
        return "%7.2fGB"%(z,)

    x=1.0*x    ## make x floating-point
    neg=x<0    ## remember the sign of x
    x=abs(x)   ##  make x positive so that "<" comparisons work

    for suffix in ('B ', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if x <= 1024:
            break
        x=x/1024
    if neg:    ## if x was negative coming in, restore the - sign  
        x = -x
    return "%6.2f%s"%(x,suffix)
    

KB=1024
MB=KB*KB
GB=MB*KB

def my_atol(s):
    s_orig = s
    mult = 1
    if not s:
        raise ValueError, s_orig
    e = string.lower(s[-1])
    if e=='b':
        s = s[:-1]
        if not s:
            raise ValueError, s_orig
        e = string.lower(s[-1])
    if e in 'lkmg':
        s = s[:-1]
        mult = {'l':1, 'm':MB, 'k':KB, 'g':GB}[e]
    x = float(s)*mult
    return(long(x))
            
# to sum up an object -- as an integrity assurance
#
# currently it only deal with numerical, string, list and dictionary
#
def sumup(a):
	# symple type?
	if type(a) == type(1) or type(a) == type(1L) or \
		type(a) == type(1.0):	# number
		return a
	elif type(a) == type("a"):	# string or character
		if len(a) == 1:		# character
			return ord(a)
		else:			# string
			sum = 0
			for i in a:
				sum = sum + ord(i)
			return sum
	elif type(a) == type([]):	# list
		sum = 0
		for i in a:
			sum = sum + sumup(i)
		return sum
	elif type(a) == type({}):	# dictionary
		sum = 0
		for i in a.keys():
			sum = sum + sumup(i) + sumup(a[i])
		return sum

	return 0

# simple syntax check for volume labels
#
# Characters        Constraint
# 1-2               must be alphabetic in upper case
# 3-4               alphanumerical
# 5-6               numerical
# 7-8               either L1 or blank
# length must be 6 or 8.
#
# check_label() returns 0 if the label conforms above rule, otherwise
# none zero is returned

def check_label(label):
    # cehck the length and suffix 'L1'
    if len(label) == 8:
        if label[-2:] != 'L1':
            return 1
    elif len(label) != 6:
            return 1

    # now check the rest of the rules
    if  not label[0] in string.uppercase or \
        not label[1] in string.uppercase or \
        not label[2] in string.uppercase+string.digits or \
        not label[3] in string.uppercase+string.digits or \
        not label[4] in string.digits or \
        not label[5] in string.digits:
        return 1

    return 0



# a function to extract values from enstore vol --vols

def extract_volume(v):    # v is a string
    system_inhibit = ["", ""]
    si_time = (0, 0)
    t = string.split(v, '(')
    t1 = t[0]
    label, avail = string.split(t1)
    tt = string.split(t[1], ')')
    ttt = string.split(tt[1])
    library = ttt[0]
    volume_family = ttt[1]
    if len(ttt) == 3:
        comment = ttt[2]
    else:
        comment = ""
    t = string.split(tt[0])
    system_inhibit = [t[0], ""]
    if len(t) == 2:
        system_inhibit[1] = t[1]
        si_time = (0,0)
    elif len(t) == 3:
        if t[1][0] in string.digits:    # time stamp
            si_time = (t[1], '')
            system_inhibit[1] = t[2]
        else:
            system_inhibit[1] = t[1]
            si_time = ('', t[2])
    elif len(t) == 4:
        system_inhibit[1] = t[2]
        si_time = (t[1], t[3])

    return {'label': label,
            'avail': avail,
            'system_inhibit': system_inhibit,
            'si_time': si_time,
            'library': library,
            'volume_family': volume_family,
            'comment': comment}
		
class VolumeClerkClient(generic_client.GenericClient,
                        backup_client.BackupClient):

    def __init__( self, csc, server_address=None ):
        generic_client.GenericClient.__init__(self, csc, MY_NAME, server_address)
        if self.server_address == None:
            self.server_address = self.get_server_address(MY_SERVER, rcv_timeout=10, tries=1)

    # add a volume to the stockpile
    def add(self,
            library,               # name of library media is in
            file_family,           # volume family the media is in
            storage_group,         # storage group for this volume
            media_type,            # media
            external_label,        # label as known to the system
            capacity_bytes,        #
            eod_cookie  = "none",  # code for seeking to eod
            user_inhibit  = ["none","none"],# 0:"none" | "readonly" | "NOACCESS"
            error_inhibit = "none",# "none" | "readonly" | "NOACCESS" | "writing"
                                   # lesser access is specified as
                                   #       we find media errors,
                                   # writing means that a mover is
                                   #       appending or that a mover
                                   #       crashed while writing
            last_access = -1,      # last accessed time
            first_access = -1,     # first accessed time
            declared = -1,         # time volume was declared to system
            sum_wr_err = 0,        # total number of write errors
            sum_rd_err = 0,        # total number of read errors
            sum_wr_access = 0,     # total number of write mounts
            sum_rd_access = 0,     # total number of read mounts
            wrapper = "cpio_odc",  # kind of wrapper for volume
            blocksize = -1,        # blocksize (-1 =  media type specifies)
            non_del_files = 0,     # non-deleted files
            system_inhibit = ["none","none"], # 0:"none" | "writing??" | "NOACCESS", "DELETED
                                             # 1:"none" | "readonly" | "full"
            remaining_bytes = None
            ):
        Trace.log(e_errors.INFO, 'add label=%s'%(external_label,))
        if storage_group == 'none':
            # the rest must be 'none' only
            file_family = 'none'
        if file_family == 'none':
            # the rest must be 'none' only
            wrapper = 'none'
        ticket = { 'work'            : 'addvol',
                   'library'         : library,
                   'storage_group'   : storage_group,
                   'file_family'     : file_family,
                   'media_type'      : media_type,
                   'external_label'  : external_label,
                   'capacity_bytes'  : capacity_bytes,
                   'eod_cookie'      : eod_cookie,
                   'user_inhibit'    : user_inhibit,
                   'error_inhibit'   : error_inhibit,
                   'last_access'     : last_access,
                   'first_access'    : first_access,
                   'declared'        : declared,
                   'sum_wr_err'      : sum_wr_err,
                   'sum_rd_err'      : sum_rd_err,
                   'sum_wr_access'   : sum_wr_access,
                   'sum_rd_access'   : sum_rd_access,
                   'wrapper'         : wrapper,
                   'blocksize'       : blocksize,
                   'non_del_files'   : non_del_files,
                   'system_inhibit'  : system_inhibit
                   }
        if remaining_bytes != None:
            ticket['remaining_bytes'] = remaining_bytes
        # no '.' are allowed in storage_group, file_family and wrapper
        for item in ('storage_group', 'file_family', 'wrapper'):
            if '.' in ticket[item]:
                print "No '.' allowed in %s"%(item,)
                break
        else:
            return self.send(ticket)
        return {'status':(e_errors.NOTALLOWED, "No '.' allowed in %s"%(item,))}

    def modify(self,ticket):
        ticket['work']='modifyvol'
        return self.send(ticket)

    # remove a volume entry in volume database
    def rmvolent(self, external_label):
        ticket= { 'work'           : 'rmvolent',
                  'external_label' : external_label}
        return self.send(ticket)

    # delete a volume from the stockpile
    def restore(self, external_label, restore=0):
        if restore: restore_vm = "yes"
        else: restore_vm = "no"
        ticket= { 'work'           : 'restorevol',
                  'external_label' : external_label,
                  "restore"         : restore_vm}
        return self.send(ticket)

    # get a list of all volumes
    def get_vols(self, key=None,state=None, not_cond=None, print_list=1):
        # get a port to talk on and listen for connections
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "get_vols",
                  "callback_addr" : (host, port),
                  "key"           : key,
                  "in_state"      : state,
                  "not"           : not_cond}

        # send the work ticket to the library manager
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            Trace.log( e_errors.ERROR,
                       'vcc.get_vols: sending ticket: %s'%(ticket,) )
            return ticket

        r,w,x = select.select([listen_socket], [], [], 15)
        if not r:
            raise errno.errorcode[errno.ETIMEDOUT], "timeout wiating for volume clerk callback"
        
        control_socket, address = listen_socket.accept()
        
        if not hostaddr.allow(address):
            control_socket.close()
            listen_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)
        
        ticket = callback.read_tcp_obj(control_socket)

        listen_socket.close()

        if ticket["status"][0] != e_errors.OK:
            return ticket

        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['volume_clerk_callback_addr'])
        ticket= callback.read_tcp_obj(data_path_socket)
        volumes = callback.read_tcp_obj_new(data_path_socket)
        data_path_socket.close()


        # Work has been read - wait for final dialog with volume clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        if volumes.has_key("header"):        # full info
            if print_list:
                print "%-10s     %-8s         %-17s          %012s     %-012s          %-012s"%(
                    "label","avail.", "system_inhibit",
                    "library","    volume_family", "comment")
                for v in volumes["volumes"]:
                    print "%-10s"%(v['volume'],),
                    print capacity_str(v['remaining_bytes']),
                    si0t = ''
                    si1t = ''
                    if v.has_key('si_time'):
                        if v['si_time'][0] > 0:
                            si0t = time.strftime("%m%d-%H%M",
                                time.localtime(v['si_time'][0]))
                        if v['si_time'][1] > 0:
                            si1t = time.strftime("%m%d-%H%M",
                                time.localtime(v['si_time'][1]))
                    print " (%-010s %9s %08s %9s) %-012s %012s"%(
                        v['system_inhibit'][0], si0t,
                        v['system_inhibit'][1], si1t,
                        # v['user_inhibit'][0],v['user_inhibit'][1],
                        v['library'],v['volume_family']),
                    if v.has_key('comment'):
                        print v['comment']
                    else:
                        print
        else:
            vlist = ''
            for v in volumes.get("volumes",[]):
                vlist = vlist+v['volume']+" "
            if print_list:
                print vlist
                
        ticket['volumes'] = volumes.get('volumes',{})
        return ticket

    # get a list of all volumes
    def get_vol_list(self):
        # get a port to talk on and listen for connections
        host, port, listen_socket = callback.get_callback()
        listen_socket.listen(4)
        ticket = {"work"          : "get_vol_list",
                  "callback_addr" : (host, port)}

        # send the work ticket to the library manager
        ticket = self.send(ticket)
        if ticket['status'][0] != e_errors.OK:
            Trace.log( e_errors.ERROR,
                       'vcc.get_vol_liat: sending ticket: %s'%(ticket,) )
            return ticket

        r,w,x = select.select([listen_socket], [], [], 15)
        if not r:
            raise errno.errorcode[errno.ETIMEDOUT], "timeout wiating for volume clerk callback"
        
        control_socket, address = listen_socket.accept()
        
        if not hostaddr.allow(address):
            control_socket.close()
            listen_socket.close()
            raise errno.errorcode[errno.EPROTO], "address %s not allowed" %(address,)
        
        ticket = callback.read_tcp_obj(control_socket)

        listen_socket.close()

        if ticket["status"][0] != e_errors.OK:
            return ticket

        data_path_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        data_path_socket.connect(ticket['volume_clerk_callback_addr'])
        ticket= callback.read_tcp_obj(data_path_socket)
        volumes = callback.read_tcp_obj_new(data_path_socket)
        data_path_socket.close()

        # Work has been read - wait for final dialog with volume clerk
        done_ticket = callback.read_tcp_obj(control_socket)
        control_socket.close()
        if done_ticket["status"][0] != e_errors.OK:
            return done_ticket

        ticket['volumes'] = volumes
        return ticket

    # what is the current status of a specified volume?
    def inquire_vol(self, external_label):
        ticket= { 'work'           : 'inquire_vol',
                  'external_label' : external_label }
        return self.send(ticket)

    # update the last_access time
    def touch(self, external_label):
        ticket= { 'work'           : 'touch',
                  'external_label' : external_label }
        return self.send(ticket)

    # trim obsolete fields if necessary
    def check_record(self, external_label):
        ticket= { 'work'           : 'check_record',
                  'external_label' : external_label }
        return self.send(ticket)

    # show_quota() -- show quota
    def show_quota(self):
        ticket = {'work': 'show_quota'}
	return self.send(ticket)

    # move a volume to a new library
    def new_library(self, external_label,new_library):
        ticket= { 'work'           : 'new_library',
                  'external_label' : external_label,
                  'new_library'    : new_library}
        return self.send(ticket)

    # we are using the volume
    def set_writing(self, external_label):
        ticket= { 'work'           : 'set_writing',
                  'external_label' : external_label }
        return self.send(ticket)

    # we are using the volume
    def set_system_readonly(self, external_label):
        ticket= { 'work'           : 'set_system_readonly',
                  'external_label' : external_label }
        return self.send(ticket)

    # mark volume as not allowed 
    def set_system_notallowed(self, external_label):
        ticket= { 'work'           : 'set_system_notallowed',
                  'external_label' : external_label }
        return self.send(ticket)

    # mark volume as noaccess
    def set_system_noaccess(self, external_label):
        ticket= { 'work'           : 'set_system_noaccess',
                  'external_label' : external_label }
        return self.send(ticket)

    # set system inhibit to none
    def set_system_none(self, external_label):
        ticket= { 'work'           : 'set_system_none',
                  'external_label' : external_label }
        return self.send(ticket)

    # clear any inhibits on the volume
    def clr_system_inhibit(self,external_label,what=None, pos=0):
        ticket= { 'work'           : 'clr_system_inhibit',
                  'external_label' : external_label,
                  'inhibit'        : what,
                  'position'       : pos}
        return self.send(ticket)

    # decrement the file count on a tape
    def decr_file_count(self,external_label, count=1):
        ticket= { 'work'           : 'decr_file_count',
                  'external_label' : external_label,
                  'count'          : count }
        return self.send(ticket)

    # we are using the volume
    def set_hung(self, external_label):
        ticket= { 'work'           : 'set_hung',
                  'external_label' : external_label }
        return self.send(ticket)

    # this many bytes left - read the database
    def get_remaining_bytes(self, external_label):
        ticket= { 'work'            : 'get_remaining_bytes',
                  'external_label'  : external_label }
        return self.send(ticket)

    # this many bytes left - update database
    def set_remaining_bytes(self, external_label,remaining_bytes,eod_cookie,bfid=None):
        # Note - bfid should be set if we added a new file
        ticket= { 'work'            : 'set_remaining_bytes',
                  'external_label'  : external_label,
                  'remaining_bytes' : remaining_bytes,
                  'eod_cookie'      : eod_cookie,
                  'bfid'            : bfid }
        return self.send(ticket)

    # update the counts in the database
    def update_counts(self, external_label, wr_err=0, rd_err=0,wr_access=0,rd_access=0,mounts=0):
        ticket= { 'work'            : 'update_counts',
                  'external_label'  : external_label,
                  'wr_err'          : wr_err,
                  'rd_err'          : rd_err,
                  'wr_access'       : wr_access,
                  'rd_access'       : rd_access,
                  'mounts'          : mounts
                  }
        return self.send(ticket)

    # Check if volume is available
    def is_vol_available(self, work, external_label, family=None, size=0):
        ticket = { 'work'                : 'is_vol_available',
                   'action'              : work,
                   'volume_family'       : family,
                   'file_size'           : size,
                   'external_label'      : external_label
                   }
        return self.send(ticket)
        
        
    # which volume can we use for this library, bytes and file family and ...
    def next_write_volume (self, library, min_remaining_bytes,
                           volume_family, vol_veto_list,first_found, mover={}, exact_match=0):
        if not mover:
             mover_type = 'Mover'
        else:
            mover_type = mover.get('mover_type','Mover')
        if mover_type is 'DiskMover':
            exact_match = 1
        ticket = { 'work'                : 'next_write_volume',
                   'library'             : library,
                   'min_remaining_bytes' : min_remaining_bytes,
                   'volume_family'       : volume_family,
                   'vol_veto_list'       : `vol_veto_list`,
                   'first_found'         : first_found,
                   'mover'               : mover,
                   'use_exact_match'     : exact_match}

        return self.send(ticket)

    # check if specific volume can be used for write
    def can_write_volume (self, library, min_remaining_bytes,
                           volume_family, external_label):
        ticket = { 'work'                : 'can_write_volume',
                   'library'             : library,
                   'min_remaining_bytes' : min_remaining_bytes,
                   'volume_family'         : volume_family,
                   'external_label'       : external_label }

        return self.send(ticket)

    # clear the pause flag for the LM and all LMs that relate to the Media Changer
    def clear_lm_pause(self, library_manager):
        ticket = { 'work'    :'clear_lm_pause',
                   'library' : library_manager
                   }
        return  self.send(ticket)

    def rename_volume(self, old, new):
        ticket = {'work': 'rename_volume',
                  'old' : old,
                  'new' : new }
        return self.send(ticket)
        
    def delete_volume(self, vol):
        ticket = {'work': 'delete_volume',
                  'external_label': vol}
        return self.send(ticket)

    def erase_volume(self, vol):
        ticket = {'work': 'erase_volume',
                  'external_label': vol}
        return self.send(ticket)

    def restore_volume(self, vol):
        ticket = {'work': 'restore_volume',
                  'external_label': vol}
        return self.send(ticket)

    def recycle_volume(self, vol):
        ticket = {'work': 'recycle_volume',
                  'external_label': vol}
        return self.send(ticket)

    def set_ignored_sg(self, sg):
        ticket = {'work': 'set_ignored_sg',
                  'sg': sg}
        return self.send(ticket)

    def clear_ignored_sg(self, sg):
        ticket = {'work': 'clear_ignored_sg',
                  'sg': sg}
        return self.send(ticket)

    def clear_all_ignored_sg(self):
        ticket = {'work': 'clear_all_ignored_sg'}
        return self.send(ticket)

    def list_ignored_sg(self):
        ticket = {'work': 'list_ignored_sg'}
        return self.send(ticket)

    def set_comment(self, vol, comment):
        ticket = {'work': 'set_comment',
                  'vol': vol,
                  'comment': comment}
        return self.send(ticket)

    def assign_sg(self, vol, sg):
        ticket = {'work': 'reassign_sg',
                  'external_label': vol,
                  'storage_group': sg}
        return self.send(ticket)


class VolumeClerkClientInterface(generic_client.GenericClientInterface):

    def __init__(self, args=sys.argv, user_mode=1):
        #self.do_parse = flag
        #self.restricted_opts = opts
        self.alive_rcv_timeout = 0
        self.alive_retries = 0
        self.clear = ""
        self.backup = 0
        self.vols = 0
        self.labels = 0
        self.in_state = 0
        self.next = 0
        self.vol = ""
        self.check = ""
        self.add = ""
        self.erase = None
        self.modify = ""
        self.delete = ""
        self.restore = ""
        self.all = 0
        self.new_library = ""
        self.read_only = ""
        self.no_access = ""
        self.not_allowed = None
        self.decr_file_count = 0
        self.rmvol = 0
        self.vol1ok = 0
        self.lm_to_clear = ""
        self.list = None
        self.ls_active = None
        self.recycle = None
        self.export = None
        self._import = None
        self.ignore_storage_group = None
        self.forget_ignored_storage_group = None
        self.forget_all_ignored_storage_groups = 0
        self.show_ignored_storage_groups = 0
        self.remaining_bytes = None
        self.set_comment = None
        self.volume = None
        self.assign_sg = None
        self.touch = None
	self.trim_obsolete = None
        self.show_quota = 0
        self.bypass_label_check = 0
        
        generic_client.GenericClientInterface.__init__(self, args=args,
                                                       user_mode=user_mode)

    def valid_dictionaries(self):
        return (self.alive_options, self.help_options, self.trace_options,
                self.volume_options)

    volume_options = {
        option.ADD:{option.HELP_STRING:"declare a new volume",
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"volume_name",
                    option.USER_LEVEL:option.ADMIN,
                    option.EXTRA_VALUES:[{option.VALUE_NAME:"library",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                         {option.VALUE_NAME:"storage_group",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                         {option.VALUE_NAME:"file_family",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                         {option.VALUE_NAME:"wrapper",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                         {option.VALUE_NAME:"media_type",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                     {option.VALUE_NAME:"volume_byte_capacity",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED,},
                                         {option.VALUE_NAME:"remaining_bytes",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.OPTIONAL,
                                          option.DEFAULT_TYPE:None,
                                          option.DEFAULT_VALUE:None,}
                                         ]},
        option.ALL:{option.HELP_STRING:"used with --restore to restore all",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.ASSIGN_SG:{
                    option.HELP_STRING: 'reassign to new storage group',
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"storage_group",
                    option.USER_LEVEL:option.ADMIN,
                    option.EXTRA_VALUES:[{
                        option.VALUE_NAME:"volume",
                        option.VALUE_LABEL:"volume_name",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED}]},
        option.BACKUP:{option.HELP_STRING:
                       "backup voume journal -- part of database backup",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.SHOW_QUOTA:{option.HELP_STRING:
                       "show quota information",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.BYPASS_LABEL_CHECK:{
                       option.HELP_STRING:
                       "skip syntatical label check when adding new volumes",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        option.CHECK:{option.HELP_STRING:"check a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.TRIM_OBSOLETE:{option.HELP_STRING:"trim obsolete fields",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.CLEAR:{option.HELP_STRING:"clear a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.FORGET_IGNORED_STORAGE_GROUP:{option.HELP_STRING:
                      "clear a ignored storage group",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"storage_group",
                      option.USER_LEVEL:option.ADMIN},
        option.FORGET_ALL_IGNORED_STORAGE_GROUPS:{option.HELP_STRING:
                      "clear all ignored storage groups",
                      option.VALUE_TYPE:option.INTEGER,
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.USER_LEVEL:option.ADMIN},
        option.DECR_FILE_COUNT:{option.HELP_STRING:
                                "decreases file count of a volume",
                                option.VALUE_TYPE:option.INTEGER,
                                option.VALUE_USAGE:option.REQUIRED,
                                option.VALUE_LABEL:"count",
                                option.USER_LEVEL:option.ADMIN},
        option.DELETE:{option.HELP_STRING:"delete a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.ERASE:{option.HELP_STRING:"erase a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.EXPORT:{option.HELP_STRING:
                       "export a volume",
                       option.DEFAULT_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.VALUE_LABEL:"volume_name",
                       option.USER_LEVEL:option.ADMIN},
        option.IGNORE_STORAGE_GROUP:{option.HELP_STRING:
                      'ignore a storage group. The format is "<library>.<storage_group>"',
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"storage_group",
                      option.USER_LEVEL:option.ADMIN},
        option.IMPORT:{option.HELP_STRING:
                       'import an exported volume object. The file name is of the format "vol.<volume_name>.obj"',
                       option.DEFAULT_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.VALUE_NAME:"_import",
                       option.VALUE_LABEL:"exported_volume_object",
                       option.USER_LEVEL:option.ADMIN},
        option.LIST:{option.HELP_STRING:"list the files in a volume",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"volume_name",
                        option.USER_LEVEL:option.USER},
        option.LS_ACTIVE:{option.HELP_STRING:"list active files in a volume",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.USER},
        option.SET_COMMENT:{
                        option.HELP_STRING:"set comment for a volume",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"comment",
                        option.USER_LEVEL:option.ADMIN,
                        option.EXTRA_VALUES:[{option.VALUE_NAME:"volume",
                                          option.VALUE_LABEL:"volume_name",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.REQUIRED}]},
        option.SHOW_IGNORED_STORAGE_GROUPS:{option.HELP_STRING:
                      "show all ignored storage group",
                      option.VALUE_TYPE:option.INTEGER,
                      option.VALUE_USAGE:option.IGNORED,
                      option.USER_LEVEL:option.ADMIN},
        option.MODIFY:{option.HELP_STRING:
                       "modify a volume record -- extremely dangerous",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"volume_name",
                        option.USER_LEVEL:option.ADMIN},
        option.NEW_LIBRARY:{option.HELP_STRING:"set new library",
                            option.VALUE_TYPE:option.STRING,
                            option.VALUE_USAGE:option.REQUIRED,
                            option.VALUE_LABEL:"library",
                            option.USER_LEVEL:option.ADMIN},
        option.NO_ACCESS:{option.HELP_STRING:"set volume to NOTALLOWED",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.ADMIN},
        option.NOT_ALLOWED:{option.HELP_STRING:"set volume to NOTALLOWED",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.ADMIN},
        option.READ_ONLY:{option.HELP_STRING:"set volume TO readonly",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.ADMIN},
        option.RECYCLE:{option.HELP_STRING:"recycle a volume",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"volume_name",
                      option.USER_LEVEL:option.ADMIN},
        option.RESET_LIB:{option.HELP_STRING:"reset library manager",
                          option.VALUE_NAME:"lm_to_clear",
                          option.VALUE_LABEL:"library",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.USER_LEVEL:option.ADMIN},
        option.RESTORE:{option.HELP_STRING:"restore a volume",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.VALUE_LABEL:"volume_name",
                        option.USER_LEVEL:option.ADMIN},
        option.TOUCH:{option.HELP_STRING:"set last_access time as now",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.ADMIN},
        option.VOL:{option.HELP_STRING:"get info of a volume",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.VALUE_LABEL:"volume_name",
                          option.USER_LEVEL:option.USER},
        option.LABELS:{
                option.HELP_STRING:"list all volume labels",
                option.DEFAULT_VALUE:option.DEFAULT,
                option.DEFAULT_TYPE:option.INTEGER,
                option.VALUE_USAGE:option.IGNORED,
                option.USER_LEVEL:option.ADMIN},
        option.VOLS:{option.HELP_STRING:"list all volumes",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_USAGE:option.IGNORED,
                     option.USER_LEVEL:option.USER},
        option.VOL1OK:{option.HELP_STRING:
                       "reset cookie to '0000_000000000_0000001'",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.DEFAULT_NAME:"vol1ok",
                       option.VALUE_USAGE:option.IGNORED,
                       option.USER_LEVEL:option.ADMIN},
        }

def do_work(intf):
    # get a volume clerk client
    vcc = VolumeClerkClient((intf.config_host, intf.config_port))
    Trace.init(vcc.get_name(MY_NAME))

    ticket = vcc.handle_generic_commands(MY_SERVER, intf)
    if ticket:
        pass

    elif intf.backup:
        ticket = vcc.start_backup()
        ticket = vcc.backup()
        ticket = vcc.stop_backup()
    elif intf.vols:
        # optional argument
        nargs = len(intf.args)
        not_cond = None
        if nargs:
            if nargs == 3:
                key = intf.args[0]     
                in_state=intf.args[1]
                not_cond = intf.args[2]
            elif nargs == 2:
                key = intf.args[0]     
                in_state=intf.args[1]
            elif nargs == 1:
                key = None
                in_state=intf.args[0]
            else:
                print "Wrong number of arguments"
                print "usage: --vols"
                print "       --vols state (will match system_inhibit)"
                print "       --vols key state"
                print "       --vols key state not (not in state)"
                return
        else:
            key = None
            in_state = None 
        ticket = vcc.get_vols(key, in_state, not_cond)
    elif intf.labels:
        ticket = vcc.get_vol_list()
        if ticket['status'][0] == e_errors.OK:
            for i in ticket['volumes']:
                print i
    elif intf.next:
        ticket = vcc.next_write_volume(intf.args[0], #library
                                       string.atol(intf.args[1]), #min_remaining_byte
                                       intf.args[2], #volume_family
                                            [], #vol_veto_list
                                             1) #first_found
    elif intf.assign_sg and intf.volume:
        ticket = vcc.assign_sg(intf.volume, intf.assign_sg)
    elif intf.touch:
        ticket = vcc.touch(intf.touch)
    elif intf.trim_obsolete:
        ticket = vcc.check_record(intf.trim_obsolete)
    elif intf.show_quota:
        ticket = vcc.show_quota()
	pprint.pprint(ticket['quota'])
    elif intf.vol:
        ticket = vcc.inquire_vol(intf.vol)
        if ticket['status'][0] == e_errors.OK:
            status = ticket['status']
            del ticket['status']
            pprint.pprint(ticket)
            ticket['status'] = status
    elif intf.check:
        ticket = vcc.inquire_vol(intf.check)
        ##pprint.pprint(ticket)
        # guard against error
        if ticket['status'][0] == e_errors.OK:
            print "%-10s  %s %s %s" % (ticket['external_label'],
                                   capacity_str(ticket['remaining_bytes']),
                                   ticket['system_inhibit'],
                                   ticket['user_inhibit'])
    elif intf.set_comment: # set comment of vol
        if len(intf.argv) != 4:
            print "Error! usage: enstore %s --set-comment=<comment> <vol>"%(sys.argv[0])
            sys.exit(1)
        ticket = vcc.set_comment(intf.volume, intf.set_comment)
    elif intf.export: # volume export
        # check for correct syntax
        if len(sys.argv) != 3:	# wrong number of arguments
            print "Error! usage: enstore %s --export <vol>"%(sys.argv[0])
            sys.exit(1)
        # get volume info first
        volume = {}
        volume['vol_name'] = intf.export
        volume['files'] = {}
        ticket = vcc.inquire_vol(intf.export)
        if ticket['status'][0] == e_errors.OK:
            del ticket['status']
            volume['vol'] = ticket
            # get all bfids
            fcc = file_clerk_client.FileClient(vcc.csc)
            ticket = fcc.get_bfids(intf.export)
            if ticket['status'][0] == e_errors.OK:
                bfids = ticket['bfids']
                status = (e_errors.OK, None)
                for i in bfids:
                    ticket = fcc.bfid_info(i)
                    if ticket['status'][0] == e_errors.OK:
                        status = ticket['status']
                        del ticket['status']
                        # deal with brain damaged backward compatibility
                        if ticket.has_key('fc'):
                            del ticket['fc']
                        if ticket.has_key('vc'):
                            del ticket['vc']
                        volume['files'][i] = ticket
                    else:
                        break
                # is the status still ok?
                if status[0] == e_errors.OK:
                    # !!! need to generate a key to prevent fake import
                    # dump it now
                    volume['key'] = 0
                    volume['key'] = sumup(volume) * -1
                    f = open('vol.'+intf.export+'.obj', 'w')
                    cPickle.dump(volume, f)
                    f.close()
                    Trace.log(e_errors.INFO, "volume %s exported"%(intf.export))
                else:
                    Trace.log(e_errors.ERROR, "failed to export volume "+intf.export)
                ticket={'status':status}
    elif intf._import: # volume import

        # Just to be paranoid, a lot of checking here

        # check for correct syntax
        if len(sys.argv) != 3:	# wrong number of arguments
            print "Error! usage: enstore %s --import vol.<vol>.obj"%(sys.argv[0])
            sys.exit(1)

        # the import file name must be vol.<vol>.obj
        fname = string.split(intf._import, '.')
        if len(fname) < 3 or fname[0] != 'vol' or fname[-1] != 'obj':
            print "Error!", intf._import, "is of wrong type of name"
            sys.exit(1)

        vname = fname[1]

        # load it up
        try:
            f = open(intf._import, 'r')
        except:
            print "Error! can not open", intf._import
            sys.exit(1)
        try:
            volume = cPickle.load(f)
        except:
            print "Error! can not load", intf._import
            sys.exit(1)

        # check if it is a real exported volume object
        #if sumup(volume) != 0:
        #    print "Error!", intf._import, "is a counterfeit"
        #    sys.exit(1)

        # check if volume contains all necessary information
        for i in ['vol', 'files', 'vol_name', 'key']:
            if not volume.has_key(i):
                print 'Error! missing key "'+i+'"'
                sys.exit(1)
        # check if file name match the volume name
        if volume['vol']['external_label'] != vname:
            print "Error!", intf._import, "does not match external_label"
            sys.exit(1)

        # check if all files match the external_label
        bfids = []
        for i in volume['files'].keys():
            f = volume['files'][i]
            if f['external_label'] != vname:
                print "Error!", intf._import, "is corrupted"
                sys.exit(1)
            bfids.append(f['bfid'])    # collect all bfids

        # get a fcc here
        fcc = file_clerk_client.FileClient(vcc.csc)

        # check for file existence
        result = fcc.exist_bfids(bfids)
        err = 0
        j = 0
        for i in result:
            if i:
                print "Error! file %s exists"%(volume['files'].values()[j]['bfid'])
                err = 1
            j = j + 1
        if err:
            sys.exit(1)

        # check if volume exists
        v = vcc.inquire_vol(volume['vol']['external_label'])
        if v['status'][0] == e_errors.OK:	# it exists
            print "Error! volume %s exists"%(volume['vol']['external_label'])
            sys.exit(1)

        # now we are getting serious

        # get the file family from volume record
        try:
            sg, ff, wr = string.split(volume['vol']['volume_family'], '.')
        except:
            print "Invalid volume_family:", `volume['vol']['volume_family']`
            sys.exit(1)

        # insert the file records first
        for i in volume['files'].keys():
            f = volume['files'][i]
            ticket = fcc.add(f)
            # handle errors
            if ticket['status'][0] != e_errors.OK:
                print "Error! failed to insert file record:", `f`
                # ignore the error, if serious, make it up later
                # sys.exit(1)

        # insert the volume record

        ticket = vcc.add(
                    library = volume['vol']['library'],
                    file_family = ff,
                    storage_group = sg,
                    media_type = volume['vol']['media_type'],
                    external_label = volume['vol']['external_label'],
                    capacity_bytes = volume['vol']['capacity_bytes'],
                    eod_cookie = volume['vol']['eod_cookie'],
                    user_inhibit = volume['vol']['user_inhibit'],
                    # error_inhibit = volume['vol']['error_inhibit'],
                    last_access = volume['vol']['last_access'],
                    first_access = volume['vol']['first_access'],
                    declared = volume['vol']['declared'],
                    sum_wr_err = volume['vol']['sum_wr_err'],
                    sum_rd_err = volume['vol']['sum_rd_err'],
                    sum_wr_access = volume['vol']['sum_wr_access'],
                    sum_rd_access = volume['vol']['sum_rd_access'],
                    wrapper = volume['vol']['wrapper'],
                    blocksize = volume['vol']['blocksize'],
                    non_del_files = volume['vol']['non_del_files'],
                    system_inhibit = volume['vol']['system_inhibit'],
                    remaining_bytes = volume['vol']['remaining_bytes'])
    elif intf.ignore_storage_group:
        ticket = vcc.set_ignored_sg(intf.ignore_storage_group)
        if ticket['status'][0] == e_errors.OK:
            pprint.pprint(ticket['status'][1])
    elif intf.forget_ignored_storage_group:
        ticket = vcc.clear_ignored_sg(intf.forget_ignored_storage_group)
        if ticket['status'][0] == e_errors.OK:
            pprint.pprint(ticket['status'][1])
    elif intf.forget_all_ignored_storage_groups:
        ticket = vcc.clear_all_ignored_sg()
        if ticket['status'][0] == e_errors.OK:
            pprint.pprint(ticket['status'][1])
    elif intf.show_ignored_storage_groups:
        ticket = vcc.list_ignored_sg()
        if ticket['status'][0] == e_errors.OK:
            pprint.pprint(ticket['status'][1])
    elif intf.add:
        if not intf.bypass_label_check:
            if check_label(intf.add):
                print 'Error: "%s" is not a valid label of format "AAXX99{L1}" '%(intf.add)
                sys.exit(1)

        #print intf.add, repr(intf.args)
        cookie = 'none'
        if intf.vol1ok:
            cookie = '0000_000000000_0000001'
        #library, storage_group, file_family, wrapper, media_type, capacity = intf.args[:6]
        capacity = my_atol(intf.volume_byte_capacity)
        if intf.remaining_bytes != None:
            remaining = my_atol(intf.remaining_bytes)
        else:
            remaining = None
        # if wrapper is empty create a default one
        if not intf.wrapper:
            if intf.media_type == 'null': #media type
                intf.wrapper = "null"
            else:
                intf.wrapper = "cpio_odc"
        ticket = vcc.add(intf.library,
                         intf.file_family,
                         intf.storage_group,
                         intf.media_type,     
                         intf.add,                  # name of this volume
                         capacity,
                         wrapper=intf.wrapper,
                         eod_cookie=cookie,            # rem cap'y of volume
                         remaining_bytes = remaining)
    elif intf.modify:
        d={}
        for s in intf.args:
            k,v=string.split(s,'=')
            try:
                v=eval(v) #numeric args
            except:
                pass #yuk...
            d[k]=v
        d['external_label']=intf.modify # name of this volume
        ticket = vcc.modify(d)

        
    elif intf.new_library:
        ticket = vcc.new_library(intf.args[0],         # volume name
                                 intf.new_library)     # new library name
    elif intf.delete:
        # ticket = vcc.delete(intf.delete,intf.force)   # name of this volume
        ticket = vcc.delete_volume(intf.delete)   # name of this volume
    elif intf.erase:
        ticket = vcc.erase_volume(intf.erase)
    elif intf.restore:
        # ticket = vcc.restore(intf.restore, intf.all)  # name of volume
        ticket = vcc.restore_volume(intf.restore)  # name of volume
    elif intf.recycle:
        ticket = vcc.recycle_volume(intf.recycle)
    elif intf.clear:
        nargs = len(intf.args)
        what = None
        pos = 0
        if nargs > 0:
            if nargs != 2:
                intf.print_clear_args()
            else:
                ipos = string.atoi(intf.args[1])-1
                if not (intf.args[0] == "system_inhibit" or intf.args[0] == "user_inhibit"):
                    intf.print_clear_args()
                    return
                elif not (ipos == 0 or ipos == 1):
                    intf.print_clear_args()
                    return
                else:
                    what = intf.args[0]
                    pos = ipos
                
        ticket = vcc.clr_system_inhibit(intf.clear, what, pos)  # name of this volume
    elif intf.decr_file_count:
        print `type(intf.decr_file_count)`
        ticket = vcc.decr_file_count(intf.args[0],string.atoi(intf.decr_file_count))
        Trace.trace(12, repr(ticket))
    elif intf.read_only:
        ticket = vcc.set_system_readonly(intf.read_only)  # name of this volume
    elif intf.no_access:
        ticket = vcc.set_system_notallowed(intf.no_access)  # name of this volume
    elif intf.not_allowed:
        ticket = vcc.set_system_notallowed(intf.not_allowed)  # name of this volume
    elif intf.lm_to_clear:
        ticket = vcc.clear_lm_pause(intf.lm_to_clear)
    elif intf.list:
        fcc = file_clerk_client.FileClient(vcc.csc)
        ticket = fcc.tape_list(intf.list)
        vol = ticket['tape_list']
        print "     label           bfid       size        location_cookie delflag original_name\n"
        klist = []
        for key in vol.keys():
            klist.append((vol[key]['location_cookie'], vol[key]['bfid']))
        klist.sort()
        for k in klist:
            key = k[1]
            record = vol[key]
            deleted = 'unknown'
            if record.has_key('deleted'):
                if record['deleted'] == 'yes':
                    deleted = 'deleted'
                else:
                    deleted = 'active'
            print "%10s %s %10i %22s %7s %s" % (intf.list,
                record['bfid'], record['size'],
                record['location_cookie'], deleted,
                record['pnfs_name0'])
    elif intf.ls_active:
        fcc = file_clerk_client.FileClient(vcc.csc)
        ticket = fcc.list_active(intf.ls_active)
        active_list = ticket['active_list']
        for i in active_list:
            print i
    else:
        intf.print_help()
        sys.exit(0)

    vcc.check_ticket(ticket)

if __name__ == "__main__":
    Trace.init(MY_NAME)
    Trace.trace( 6, 'vcc called with args: %s'%(sys.argv,) )

    # fill in the interface
    intf = VolumeClerkClientInterface(user_mode=0)

    do_work(intf)


