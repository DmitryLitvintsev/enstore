###############################################################################
# src/$RCSfile$   $Revision$
#

#import sys
#import string
import types

OK         = 'ok'
TIMEDOUT = 'TIMEDOUT'
KEYERROR = 'KEYERROR'
DOESNOTEXIST = 'DOESNOTEXIST'
WRONGPARAMETER = 'WRONGPARAMETER'
NOWORK = 'nowork'
NOMOVERS = 'nomovers'
MOUNTFAILED = 'MOUNTFAILED'
DISMOUNTFAILED = 'DISMOUNTFAILED'
MEDIA_IN_ANOTHER_DEVICE =  'media_in_another_device'
MEDIAERROR = 'MEDIAERROR'
USERERROR = 'USERERROR'
DRIVEERROR = 'DRIVEERROR'
UNKNOWNMEDIA = 'UNKNOWNMEDIATYPE'
NOVOLUME = 'NOVOLUME'
NOACCESS = 'NOACCESS'
NOTALLOWED = 'NOTALLOWED'
CONFLICT = 'CONFLICT'
TOOMANYSUSPVOLS = 'TOOMANYSUSPVOLS'
UNKNOWN = 'UNKNOWN'
NOALARM = 'NOALARM'
SERVERDIED = 'SERVERDIED'
CANTRESTART = 'CANTRESTART'
DELETED = 'DELETED'
NOSPACE = 'NOSPACE'                     #Encp: Output device full on read.
INPROGRESS = 'INPROGRESS'
VOL_SET_TO_FULL = 'VOLISSETTOFULL'
ENCP_GONE       = 'ENCP_GONE'
TCP_HUNG        = 'TCP_HUNG'
MOVER_CRASH     = 'MOVER_CRASH'
BELOW_THRESHOLD = 'BELOW_THRESHOLD'
ABOVE_THRESHOLD = 'ABOVE_THRESHOLD'

#V2 additions:
MOVER_STUCK = 'MOVER_STUCK'
MOVER_BUSY = 'MOVER_BUSY'
CONFIGDEAD = 'CONFIGDEAD'               #Config server was not found.
DOESNOTEXISTSTILLDONE = 'DOESNOTEXIST MARKED ANYWAY'
RECYCLE='RECYCLE_VOLUME'
QUOTAEXCEEDED='STORAGE_QUOTA_EXCEEDED'
CRC_ERROR='CRC MISMATCH'                #CRC error if caught by mover.
CRC_ENCP_ERROR='CRC ENCP MISMATCH'      #CRC error if caught by encp.
CRC_ECRC_ERROR='CRC ECRC MISMATCH'      #CRC error if caught by encp --ecrc.
NO_CRC_RETURNED = 'mover did not return CRC'  #Encp warning if no crc returned.
NET_ERROR="NET_ERROR"                   #Blanket error for caught socket.error.
RETRY="RETRY"                           #Internal encp error.
RESUBMITTING = "RESUBMITTING"           #Internal encp error.
TOO_MANY_RETRIES="TOO MANY RETRIES"     #External encp error.
TOO_MANY_RESUBMITS="TOO_MANY_RESUBMITS" #External encp error.
BROKEN="BROKEN"
EPROTO="PROTOCOL_ERROR"                 #Used for many things...
IOERROR = "IO ERROR"                    #Used for many things...
ENSTOREBALLRED = "ENSTORE BALL IS RED"
MALFORMED = "MALFORMED REQUEST"
VERSION_MISMATCH="VERSION MISMATCH"     #Tells user to update encp.
# LM states
LOCKED="locked"
UNLOCKED="unlocked"
NOREAD="noread"
NOWRITE="nowrite"
REJECT='reject'
PAUSE='pause'
IGNORE='ignore'
# end of LM statues
OSERROR = "OS ERROR"                    #Blanket error for caught OSError.
PNFS_ERROR = "PNFS ERROR"               #Encp to Pnfs specific error.
ENCP_STUCK = "ENCP STUCK"               #Mover detected no encp progress.
POSITIONING_ERROR='POSITIONING_ERROR'

#V3 additions:
DEVICE_ERROR = "DEVICE ERROR"           #read()/write() call stuck in kernel.
FILE_MODIFIED = "FILE WAS MODIFIED"     #Encp knows local file changed.
NO_FILES = "NO_FILES"                   #Internal encp error.
CRC_DCACHE_ERROR = "CRC DCACHE MISMATCH"  #CRC error if caught by encp.
UNCAUGHT_EXCEPTION = "UNCAUGHT EXCEPTION" #An exception was not caught in encp.

BFID_EXISTS = "BFID EXISTS"
NO_FILE = "NO SUCH FILE/BFID"
TOO_MANY_FILES = "TOO MANY FILES MATCH"
NO_VOLUME = "NO SUCH VOLUME"
TOO_MANY_VOLUMES = "TOO MANY VOLUMES MATCH"
RESTRICTED_SERVICE = "RESTRICTED SERVICE"
FILE_CLERK_ERROR = "F-ERROR"
VOLUME_CLERK_ERROR = "V-ERROR"
INFO_SERVER_ERROR = "I-ERROR"
NO_SG = "NO SUCH STORAGE GROUP"
VOLUME_EXISTS = "VOLUME EXISTS"
WRONG_FORMAT = "WRONG FORMAT"
DATABASE_ERROR = "DATABASE ERROR"

FILESYSTEM_CORRUPT = "Filesystem is corrupt" #Encp finds pnfs corrupted.
MC_QUEUE_FULL = "MEDIA_CHANGER_QUEUE_FULL" # media changer queue is full
BAD_FILE_SIZE = "BAD_FILE_SIZE" # file size is bad. For instance < 0
MEMORY_ERROR = "MEMORY_ERROR" # python exception MemoryError
NOT_SUPPORTED = "NOT SUPPORTED"
INVALID_WRAPPER = "INVALID WRAPPER" #The tape wrapper type is not known.
INVALID_ACTION = "INVALID ACTION" 

# Severity codes
# NOTE: IMPORTANT, THESE VALUES CORRESPOND TO "TRACE LEVELS" AND CHANGING
#       THEM WILL IMPACT OTHER PARTS OF THE SYSTEM
EMAIL      = -1  #Should this be -1???
ALARM      = 0
ERROR      = 1
USER_ERROR = 2
WARNING    = 3
INFO       = 4
MISC       = 5

# severity translator
sevdict = { ALARM      : 'A',
            ERROR      : 'E',
            USER_ERROR : 'U',
            WARNING    : 'W',
            INFO       : 'I',
            MISC       : 'M',
            EMAIL      : 'C'
            }

# Alarm severities
DEFAULT_SEVERITY = sevdict[WARNING]
DEFAULT_ROOT_ERROR = UNKNOWN

# Exceptions that are raised (now obsolete)
#-------------------------------------
TCP_EXCEPTION = "TCP connection closed"
NOT_ALWD_EXCEPTION = "Not allowed"
CLEANUDP_EXCEPTION = "mis-use of class cleanUDP"
VM_PNFS_EXCEPTION = "Pnfs error"
VM_ENSTORE_EXCEPTION = "enstore error"
VM_CONF_EXCEPTION = "conf.sh failed"
NO_FC_EXCEPTION = "can't find file clerk in conf.sh"
NO_PNFS_EXCEPTION = "Not a full path "
POSIT_EXCEPTION = "XXX Positioning error"


# Tape Errors:
#--------------------------------------
# Write Error:
WRITE_NOTAPE    = 'WRITE_NOTAPE'
WRITE_TAPEBUSY  = 'WRITE_TAPEBUSY'
WRITE_BADMOUNT  = 'WRITE_BADMOUNT'
WRITE_BADSWMOUNT = 'WRITE_BADSWMOUNT'
WRITE_BADSPACE  = 'WRITE_BADSPACE'
WRITE_ERROR     = 'WRITE_ERROR'
WRITE_EOT       = 'WRITE_EOT'




# Read Errors:
READ_NOTAPE     = 'READ_NOTAPE'
READ_TAPEBUSY   = 'READ_TAPEBUSY'
READ_BADMOUNT   = 'READ_BADMOUNT'
READ_BADSWMOUNT = 'READ_BADSWMOUNT'
READ_BADLOCATE  = 'READ_BADLOCATE'
READ_ERROR      = 'READ_ERROR'
READ_EOT        = 'READ_EOT'
READ_EOD        = 'READ_EOD'
READ_NODATA     = 'READ_NODATA'

## Volume label errors
# read error trying to check VOL1 header, reading/writing hsm
READ_VOL1_READ_ERR = "READ_VOL1_READ_ERR"
WRITE_VOL1_READ_ERR = "WRITE_VOL1_READ_ERR"
# VOL1 header missing, reading/writing hsm
READ_VOL1_MISSING = "READ_VOL1_MISSING"
WRITE_VOL1_MISSING = "WRITE_VOL1_MISSING"
# VOL1 header present, but incorrect volume
READ_VOL1_WRONG = "READ_VOL1_WRONG"
WRITE_VOL1_WRONG = "WRITE_VOL1_WRONG"
EOV1_ERROR = "EOV1_ERROR"


#---------------------------------------

#Media changer errors:
MC_VOLNOTHOME = 9999   # not in home position in tower
MC_DRVNOTEMPTY = 9998  # drive already has volume mounted in it
MC_NONE =  9997        # code is None - very bad - CHECK ROBOT
MC_FAILCHKVOL = 9996   # check of volume failed
MC_VOLNOTFOUND = 9995  # volume not found
MC_FAILCHKDRV = 9994   # check of volume failed
MC_DRVNOTFOUND = 9993  # volume not found

#---------------------------------------


## Retry policy:
## 3 strikes and you're out.  Also, locally-caught errors (permissions, no such file) are not retried.
non_retriable_errors = ( NOACCESS, # set by enstore
                         NOTALLOWED, #set by admin
                         USERERROR,
                         UNKNOWNMEDIA, # comes from volume clerk - unknown type
                         NOVOLUME, #unknown volume
                         DELETED,
                         QUOTAEXCEEDED,
                         TOO_MANY_RETRIES, #atttempts with failure
                         TOO_MANY_RESUBMITS, #attempts without trying
                         MALFORMED,
                         VERSION_MISMATCH, #ENCP to old
                         LOCKED,  # Library is locked for the access
                         NOREAD,  # Library is locked for the read access
                         NOWRITE, # Library is locked for the write access
                         REJECT, # Library Manager rejects to accept request
                         NOSPACE, # Local disk full on read.
                         CRC_ERROR,  #Set by mover
                         FILE_MODIFIED, #When writing the file changed.
                         NO_FILES, #encp has no files to transfer???
                         NO_FILE,   #FC does not know about requested bfid
                         NO_VOLUME, #VC does not know about requested volume
                         BAD_FILE_SIZE, # file size is bad. For instance < 0
                         INVALID_WRAPPER, #The tape wrapper type is not known.
                         )

raise_alarm_errors = ( CONFLICT, #Metadata is not consistant.
                       FILESYSTEM_CORRUPT, #PNFS metadata is not consistant.
                       )

email_alarm_errors = ( CRC_ENCP_ERROR,   #Set by encp
                       CRC_ECRC_ERROR,   #Set by encp
                       CRC_DCACHE_ERROR, #Set by encp
                       DEVICE_ERROR, #EXfer read/write call stuck in kernel
                      )

# CLIENT PORTION OF 'MESS_TYPE' MESSAGE
ctypedict = {  "checkpoint"      : "CP",
               "fc"              : "FC",          # FILE CLERK
               "alarm_srv"       : "AS",          # ALARM SERVER
               "filsrv"          : "FS",
               "volsrv"          : "VS",
               "server"          : "SVR",
               "encp"            : "ENCP",
               "lm"              : "LM",          # LIBRARY MANAGER
               "vc"              : "VC",          # VOLUME CLERK
               "mc"              : "MC",          # MEDIA CHANGER
               "re"              : "RE",
               "mvr"             : "MVR",         # MOVER
               "backup"          : "BU" }

# FUNCTION PORTION OF 'MESS_TYPE' MESSAGE
# ******* NOTE ******* DON'T PUT 'OK' FOR STRING CHECK. THE STRING CHECK WILL
# ALWAYS FIND SOMETHING AND MARK THE MESSAGE AS BEING SUCCESSFUL WHEN THERE
# MAY HAVE BEEN AN ERROR. IT'S BEST TO PUT 'OK' IN THE DICTIONARY FOR EACH
# OCCURRENCE THAT IT IS NEEDED.
ftypedict = { "read"          : "READ",
              "r"             : "READ",
              "write"         : "WRITE",
              "writing"       : "WRITE",
              "w"             : "WRITE",
              "write_file"    : "WRITE",
              "write_wrapper" : "WRITE",
              "write_hsm"     : "WRITE_HSM",
              "exception"     : "EXCEPTION",
              "no_acc"        : "NO_ACC",
              "server_died"   : "SVR",
              "mount"         : "MOUNT",
              "mounting"      : "MOUNT",
              "load"          : "MOUNT",
              "loading"       : "MOUNT",
              "filedb"        : "FILEDB",
              "voldb"         : "VOLDB",
              "insert_vol"    : "INSERT",
              "insert"        : "INSERT",
              "cant_restart"  : "RESTART",
              "volume"        : "VOL",
              "vol"           : "VOL",
              "vol_err"       : "VOL",
              "file"          : "FILE",
              "system"        : "SYS",
              "unmount"       : "DISM",
              "dismount"      : "DISM",
              "dismounting"   : "DISM",
              "unload"        : "DISM",
              "offline/eject" : "DISM",
              "offline_eject" : "DISM",
              "eject"         : "DISM",
              "bind"          : "BIND",
              "unbind"        : "UNBIND",
              "unbind_vol"    : "UNBIND",
              "list"          : "LIST",
              "list."         : "LIST",
              "fd_xfers"      : "XFER",
              "fd_xfer"       : "XFER",
              "xfer"          : "XFER",
              "copy"          : "XFER",
              "copying"       : "XFER",
              "move"          : "XFER",
              "moving"        : "XFER",
              "->"            : "XFER" }

# SEVERITY PORTION OF 'MESS_TYPE' MESSAGE
stypedict = { "died"               : "DIED",
              "server_died"        : "DIED",
              "ts"                 : "TS",
              "write_file"         : "FILE",
              "write_wrapper"      : "WRAP",
              "q'd"                : "QUEUED",
              "queue"              : "QUEUED",
              "queued"             : "QUEUED",
              "check"              : "CHECK",
              "check_suc"          : "CHECK_SUC",
              "insert_vol"         : "VOL",
              "unbind_vol"         : "VOL",
              "open"               : "OPEN",
              "opening"            : "OPEN",
              "close"              : "CLOSE",
              "closing"            : "CLOSE",
              "request"            : "REQ",
              "requested"          : "REQ",
              "requesting"         : "REQ",
              "hurrah"             : "SUC",
              "success"            : "SUC",
              "successful"         : "SUC",
              "successful'"        : "SUC",
              "wrote"              : "SUC",
              "copied"             : "SUC",
              "xfered"             : "SUC",
              "xfer'd"             : "SUC",
              "added"              : "SUC",
              "ok"                 : "SUC",
              "'ok'"               : "SUC",
              "'ok',"              : "SUC",
              "('ok',"             : "SUC",
              "status('ok',"       : "SUC",
              "done"               : "SUC",
              "end"                : "SUC",
              "ending"             : "SUC",
              "completed"          : "SUC",
              "complete"           : "SUC",
              "finish"             : "SUC",
              "finishing"          : "SUC",
              "finished"           : "SUC",
              "performed"          : "SUC",
              "add"                : "ADD",
              "adding"             : "ADD",
              "start"              : "START",
              "begin"              : "START",
              "starting"           : "START",
              "beginning"          : "START",
              "perform"            : "START",
              "performing"         : "START",
              "work"               : "START",
              "stop"               : "STOP",
              "next"               : "NEXT",
              "restart"            : "RESTART",
              "update_client_info" : "UCI",
              "error"              : "ERR",
              "vol_err"            : "ERR",
              "cant_restart"       : "ERR",
              "fail"               : "ERR",
              "bad"                : "ERR",
              "not"                : "ERR",
              "can't"              : "ERR",
              "cant"               : "ERR",
              "e"                  : "ERR",
              "i"                  : "INFO",
              "a"                  : "ALARM",
              "w"                  : "WARNING",
              "u"                  : "USERERR",
              "m"                  : "MISCERR" }

def _get_error(obj):
    if type(obj) == types.StringType:
        error = obj
    elif type(obj) == types.TupleType and len(obj) == 2:
        error = obj[0]
    elif type(obj) == types.DictionaryType and obj.get('status', None):
        error = obj['status'][0]
    else:
        error = obj

    return error

#Return true if the status is the same as e_errors.OK, false otherwise.
def is_ok(e):
    error = _get_error(e)
        
    if error == OK:
        return 1
    return 0

#Return true if the status is the same as e_errors.OK, false otherwise.
def is_timedout(e):
    error = _get_error(e)
    
    if error == TIMEDOUT:
        return 1

    return 0

#Return true if the status is in error but not in non_retriable or raise_alarm
# status.  Return false otherwise.
def is_retriable(e):
    error = _get_error(e)
    
    if is_ok(error):
        return 0
    elif error in non_retriable_errors:
        return 0
    elif error in raise_alarm_errors:
        return 0
    elif error in email_alarm_errors:
        return 0
    return 1

#If the value is in non_retriable or raise alarm return 1.  False otherwise.
def is_non_retriable(e):
    error = _get_error(e)
    
    if error in non_retriable_errors:
        return 1
    elif error in raise_alarm_errors:
        return 1
    elif error in email_alarm_errors:
        return 1
    return 0

#If the value is alarmable, return 1 otherwise false.
def is_alarmable(e):
    error = _get_error(e)
    
    if error in raise_alarm_errors:
        return 1
    elif error in email_alarm_errors:
        return 1
    return 0

#If the value is emailable, return 1 otherwise false.
def is_emailable(e):
    error = _get_error(e)
    
    if error in email_alarm_errors:
        return 1
    return 0

#If the value is RETRY or RESUBMITTING return 1 otherwise 0.
def is_resendable(e):
    error = _get_error(e)
    
    if error == RETRY:
        return 1
    elif error == RESUBMITTING:
        return 1
    return 0

#If the value is a media error return 1 otherwise 0.
def is_media(e):
    error = _get_error(e)

    if is_ok(error):
        return 0
    #Write errors.
    elif error in [WRITE_NOTAPE, WRITE_TAPEBUSY, WRITE_BADMOUNT,
                   WRITE_BADSWMOUNT, WRITE_BADSPACE, WRITE_ERROR, WRITE_EOT]:
        return 1
    #Read errors.
    elif error in [READ_NOTAPE, READ_TAPEBUSY, READ_BADMOUNT,
                   READ_BADSWMOUNT, READ_BADLOCATE, READ_ERROR, READ_EOT,
                   READ_EOD, READ_NODATA]:
        return 1
    #Label read/write errors.
    elif error in [READ_VOL1_READ_ERR, WRITE_VOL1_READ_ERR, READ_VOL1_MISSING,
                   WRITE_VOL1_MISSING, READ_VOL1_WRONG, WRITE_VOL1_WRONG,
                   EOV1_ERROR]:
        return 1
    #Misc. errors.
    elif error in [NOACCESS, NOTALLOWED, CRC_ERROR, MEDIAERROR]:
        return 1
    return 0
