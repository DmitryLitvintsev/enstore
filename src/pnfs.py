#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#
# system imports
import sys
import os
import errno
import stat
import pwd
import grp
import string
import time
import fcntl
import pprint
import pdb
import traceback
import select

# enstore imports
import Trace
import e_errors
try:
    import Devcodes # this is a compiled enstore module
except ImportError:
    Trace.log(e_errors.INFO, "Devcodes unavailable")
import option
import enstore_constants
import hostaddr

#ENABLED = "enabled"
#DISABLED = "disabled"
#VALID = "valid"
#INVALID =  "invalid"
UNKNOWN = "unknown"
#EXISTS = "file exists"
#DIREXISTS = "directory exists"
ERROR = -1

ATTEMPTS = 5

#do_log = 0 #If this is set, PNFS errors will be logged

##############################################################################

#This is used to print out some of the results to the terminal that are more
# than one line long and contained in a list.  The list is usually generated
# by a f.readlines() where if is a file object.  Otherwise the result is
# printed as is.
def print_results(result):
    if type(result) == type([]):
         for line in result:
            print line, #constains a '\012' at the end.
    else:
        print result

# generate the full path name to the file
def fullpath(filename):
    if not filename:
        return None, None, None, None

    machine = hostaddr.gethostinfo()[0]

    #Expand the path to the complete absolute path.
    filename = os.path.expandvars(filename)
    filename = os.path.expanduser(filename)
    filename = os.path.abspath(filename)
    filename = os.path.normpath(filename)

    dirname, basename = os.path.split(filename)

    return machine, filename, dirname, basename

##############################################################################

class Pnfs:# pnfs_common.PnfsCommon, pnfs_admin.PnfsAdmin):
    # initialize - we will be needing all these things soon, get them now
    def __init__(self, pnfsFilename="", mount_point=""):

                 #get_details=1, get_pinfo=0, timeit=0, mount_point=""):

        self.print_id = "PNFS"
        self.mount_point = mount_point

        if mount_point:
            self.dir = mount_point
        else:
            self.dir = os.getcwd() ###This needs to be addressed.

        #Test if the filename passed in is really a pnfs id.
        if self.is_pnfsid(pnfsFilename):
            
            try:
                self.id = pnfsFilename
                pnfsFilename = self.get_path(pnfsFilename)
            except (OSError, IOError), detail:
                self.id = ""

        if pnfsFilename:
            (self.machine, self.filepath, self.directory, self.filename) = \
                           fullpath(pnfsFilename)

        try:
            self.pnfsFilename = self.filepath
        except AttributeError:
            sys.stderr.write("self.filepath DNE after initialization\n")

    ##########################################################################

    def is_pnfsid(self, pnfsid):
        #This is an attempt to deterime if a string is a pnfsid.
        # 1) Is it a string?
        # 2) Is it 24 characters long?
        # 3) Does the string as a filepath not exist?
        # 4) All characters are in the capital hex character set.
        #Note: Does it need to be capital set of hex characters???
        if type(pnfsid) == type("") and len(pnfsid) == 24 and \
           not os.path.exists(pnfsid):
            allowable_characters = string.upper(string.hexdigits)
            for c in pnfsid:
                if c not in allowable_characters:
                    return 0
            else: #success
                return 1
        return 0

    # list what is in the current object
    def dump(self):
        #Trace.trace(14, repr(self.__dict__))
        print repr(self.__dict__)


    #This function is used to test for various conditions on the file.
    # The purpose of this function is to hide the hidden files associated
    # with each real file.
    def verify_existance(self, filepath=None):
        if filepath:
            fname = filepath
        else:
            fname = self.filepath

        
        if not os.path.exists(fname):
            raise OSError(errno.ENOENT,
                          os.strerror(errno.ENOENT) + ": " + fname)

        if not os.access(fname, os.R_OK):
            raise OSError(errno.EACCES,
                          os.strerror(errno.EACCES) + ": " + fname)

    ##########################################################################

    # create a new file or update its times
    def touch(self, filename=None):
        if not filename:
            filename = self.pnfsFilename
            
        try:
            self.utime(filename)
        except os.error, msg:
            if msg.errno == errno.ENOENT:
                f = open(filename,'w')
                f.close()
            else:
                Trace.log(e_errors.INFO,
                          "problem with pnfsFilename = " + filename)
                raise os.error, msg

        self.pstatinfo()

    # update the access/mod time of a file
    # this function also seems to flush the nfs cache
    def utime(self, filename=None):
        if not filename:
            filename = self.pnfsFilename
        
        for i in range(ATTEMPTS):
            try:
                t = int(time.time())
                os.utime(filename,(t,t))
                break
            except os.error, msg:
                time.sleep(1)
        else:
            Trace.log(e_errors.INFO, "can not utime: %s %s"%(os.error,msg))
            raise msg
        
    # delete a pnfs file including its metadata
    def rm(self, filename=None):
        if not filename:
            filename = self.pnfsFilename
            
        self.writelayer(1,"", filename)
        self.writelayer(2,"", filename)
        self.writelayer(3,"", filename)
        self.writelayer(4,"", filename)

        # It would be better to move the file to some trash space.
        # I don't know how right now.
        os.remove(filename)

        self.pstatinfo()

    ##########################################################################

    # write a new value to the specified file layer (1-7)
    # the file needs to exist before you call this
    def writelayer(self,layer,value, filepath=None):
        if filepath:
            (directory, file) = os.path.split(filepath)
        else:
            (directory, file) = os.path.split(self.filepath)
            
        fname = os.path.join(directory, ".(use)(%s)(%s)"%(layer, file))

        #If the value isn't a string, make it one.
        if type(value)!=type(''):
            value=str(value)

        for i in range(ATTEMPTS):
            try:
                f = open(fname,'w')
                f.write(value)
                f.close()
                self.utime()
                self.pstatinfo()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

    # read the value stored in the requested file layer
    def readlayer(self,layer, filepath=None):
        if filepath:
            (directory, file) = os.path.split(filepath)
        else:
            (directory, file) = os.path.split(self.filepath)
            
        fname = os.path.join(directory, ".(use)(%s)(%s)"%(layer, file))

        for i in range(ATTEMPTS):
            try:
                f = open(fname,'r')
                l = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail
        
        return l

    ##########################################################################

    # get the const info of the file, given the filename
    def get_const(self, filepath=None):

        if filepath:
            (directory, file) = os.path.split(filepath)
        else:
            (directory, file) = os.path.split(self.filepath)

        fname = os.path.join(directory, ".(const)(%s)"%(file,))

        for i in range(ATTEMPTS):
            try:
                f=open(fname,'r')
                const = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        if not filepath:
            self.const = const
        return const

    # get the numeric pnfs id, given the filename
    def get_id(self, filepath=None):

        if filepath:
            (directory, file) = os.path.split(filepath)
        else:
            (directory, file) = os.path.split(self.filepath)
            
        fname =os.path.join(directory, ".(id)(%s)" % (file,))

        for i in range(ATTEMPTS):
            try:
                f = open(fname,'r')
                id = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        id = string.replace(id[0],'\n','')

        if not filepath:
            self.id = id
        return id

    def get_showid(self, id=None, directory=""):

        if directory:
            use_dir = directory
        else:
            use_dir = self.dir

        if id:
            fname = os.path.join(directory, ".(showid)(%s)"%(id,))
        else:
            fname = os.path.join(self.dir, ".(showid)(%s)"%(self.id,))

        for i in range(ATTEMPTS):
            try:
                f = open(fname,'r')
                showid = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        if not id:
            self.showid = showid
        return id

    # get the nameof information, given the id
    def get_nameof(self, id=None, directory=""):

        if directory:
            use_dir = directory
        else:
            use_dir = self.dir

        if id:
            fname = os.path.join(use_dir, ".(nameof)(%s)"%(id,))
        else:
            fname = os.path.join(use_dir, ".(nameof)(%s)"%(self.id,))

        for i in range(ATTEMPTS):
            try:
                f = open(fname,'r')
                nameof = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail
        
        nameof = string.replace(nameof[0],'\n','')

        if not id:
            self.nameof = nameof
        return nameof

    # get the parent information, given the id
    def get_parent(self, id=None, directory=""):
        if directory:
            use_dir = directory
        else:
            use_dir = self.dir
            
        if id:
            fname = os.path.join(use_dir, ".(parent)(%s)"%(id,))
        else:
            fname = os.path.join(use_dir, ".(parent)(%s)"%(self.id,))

        for i in range(ATTEMPTS):
            try:            
                f = open(fname,'r')
                parent = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail
        
        parent = string.replace(parent[0],'\n','')

        if not id:
            self.parent = parent
        return parent

    # get the total path of the id
    def get_path(self, id=None, directory=""):
        if directory:
            use_dir = directory
        else:
            use_dir = self.dir

        if id:
            use_id = id
        else:
            use_id = self.id

        ###Note: The filepath should be munged with the mountpoint.
        search_path = os.path.join("/", use_dir.split("/")[0])
        for d in self.dir.split("/")[1:]:
            search_path = os.path.join(search_path, d)
            if os.path.ismount(search_path):
                #If the path is of the master /pnfs/fs, then the /usr should
                # be appended.  This is the user that is the equivalent of
                # the /root/fs/usr, but in this case the /usr compent of the
                # directory is required because it is removed from the filepath
                # variable when the entire /root/fs/usr is removed from the
                # beginning.
                if search_path == "/pnfs/fs":
                    search_path = "/pnfs/fs/usr"
                break;
        else:
            raise OSError(errno.ENODEV, "%s: %s"%(os.strerror(errno.ENODEV),
                                            "Unable to determine mount point"))

        #Obtain the root file path.  This is done by obtaining a directory
        # component id, its name and parents id.  Then with the parents id
        # the process is repeated.  It stops when the component is the /root
        # directory (pnfs_id=000000000000000000001020).
        try:
            filepath = self.get_nameof(use_id, use_dir) # starting point.
        except (OSError, IOError):
            raise OSError(errno.ENOENT, "%s: %s" % (os.strerror(errno.ENOENT),
                                                    "Not a valid pnfs id"))
        name = ""  # compoent name of a directory.
        while name != "root" and use_id != "000000000000000000001020":
            use_id = self.get_parent(use_id, use_dir) #get parent id
            name = self.get_nameof(use_id, use_dir) #get nameof parent id
            filepath = os.path.join(name, filepath) #join filepath together
        filepath = os.path.join("/", filepath)
        #Truncate the begining false directories.
        if filepath[:13] == "/root/fs/usr/":
            filepath = filepath[13:]
        else:
            raise OSError(errno.ENOENT, "%s: %s" % (os.strerror(errno.ENOENT),
                                                    "Not a valid pnfs id"))

        #Munge the mount point and the directories.  First check if the two
        # paths can be munged without modification.
        if os.access(os.path.join(search_path, filepath), os.F_OK):
            filepath = os.path.join(search_path, filepath)
        #Then check if removing the last compenent of the mount point path
        # (search_path) will help when munged.
        elif os.access(os.path.join(os.path.dirname(search_path), filepath),
                       os.F_OK):
            filepath = os.path.join(os.path.dirname(search_path), filepath)
        #Lastly, remove the first entry in the file path before munging.
        elif os.access(os.path.join(search_path, filepath.split("/", 1)[1]),
                       os.F_OK):
            filepath = os.path.join(search_path, filepath.split("/", 1)[1])

        if not id:
            self.path = filepath

        return filepath
        
    # get the cursor information
    def get_cursor(self, directory=None):

        if directory:
            fname = os.path.join(directory, ".(get)(cursor)")
        else:
            fname = os.path.join(self.dir, ".(get)(cursor)")

        for i in range(ATTEMPTS):
            try:       
                f = open(fname,'r')
                cursor = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail
        
        if not directory:
            self.cursor = cursor
        return cursor

    # get the cursor information
    def get_counters(self, directory=None):

        if directory:
            fname = os.path.join(directory, ".(get)(counters)")
        else:
            fname = os.path.join(self.dir, ".(get)(counters)")

        for i in range(ATTEMPTS):
            try:  
                f=open(fname,'r')
                counters = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        if not directory:
            self.counters = counters
        return counters

    # get the position information
    def get_position(self, directory=None):

        if directory:
            fname = os.path.join(directory, ".(get)(postion)")
        else:
            fname = os.path.join(self.dir, ".(get)(postion)")

        for i in range(ATTEMPTS):
            try:  
                f=open(fname,'r')
                position = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        if not directory:
            self.position = position
        return position

    # get the database information
    def get_database(self, directory=None):

        if directory:
            fname = os.path.join(directory, ".(get)(database)")
        else:
            fname = os.path.join(self.dir, ".(get)(database)")

        for i in range(ATTEMPTS):
            try:  
                f=open(fname,'r')
                database = f.readlines()
                f.close()
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail
        
        database = string.replace(database[0], "\n", "")

        if not directory:
            self.database = database
        return database

    ##########################################################################

    def get_file_size(self, filepath=None):

        if filepath:
            file = filepath
        else:
            file = self.filepath

        self.verify_existance()

        #Get the file system size.
        for i in range(ATTEMPTS):
            try:  
                file_size = os.stat(file)[stat.ST_SIZE]
                break
            except OSError, detail:
                time.sleep(1)
        else:
            raise detail

        #If there is no layer 4, go with the os size.
        try:
            filesize = long(self.get_xreference()[2].strip())
        except ValueError:
            self.file_size = file_size
            return file_size
        
        #Error checking.  However first ignore large file cases.
        if file_size == 1 and filesize > long(2L**31L) - 1:
            if not filepath:
                self.file_size = filesize
            return filesize
        elif file_size != filesize:
            raise OSError(errno.EBADFD,
                          os.strerror(errno.EBADFD) + ": filesize coruption")
        else:
            if not filepath:
                self.file_size = filesize
            return filesize
	

    def set_file_size(self, filesize, filepath=None):
        #handle large files.
        if filesize > (2**31L) - 1:
            size = 1
        else:
            size = filesize

        #Don't report the hidden file to the user if there is a problem,
        # report the original file.
        self.verify_existance()
        
        xref = self.get_xreference()
        formated_size = str(filesize)
        if formated_size[-1] == "L":
            formated_size = formated_size[:-1]
        xref[2] = formated_size  #get_xreferece() always returns a 10-tuple.
        apply(self.set_xreference, xref) #Don't untuple xref.

        #Set the filesize that the filesystem knows about.
        if filepath:
            (directory, file) = os.path.split(filepath)
        else:
            (directory, file) = os.path.split(self.filepath)
        fname = os.path.join(directory,
                             ".(fset)(%s)(size)(%s)"%(file,size))
        f = open(fname,'w')
        f.close()

        #Update the times.
        self.utime()
        self.pstatinfo()

    ##########################################################################

    # set a new mode for the existing file
    def chmod(self,mode):
        os.chmod(self.pnfsFilename,mode)
        self.utime()
        self.pstatinfo()

    # change the ownership of the existing file
    def chown(self,uid,gid):
        os.chown(self.pnfsFilename,uid,gid)
        self.utime()
        self.pstatinfo()

    ##########################################################################

    # store a new bit file id
    def set_bit_file_id(self,value,filepath=None):
        if filepath:
            self.writelayer(enstore_constants.BFID_LAYER, value, filepath)
        else:
            self.writelayer(enstore_constants.BFID_LAYER, value)
            self.get_bit_file_id()

        return value

    # store the cross-referencing data
    def set_xreference(self, volume, location_cookie, size, file_family,
                       pnfsFilename, volume_filepath, id, volume_fileP,
                       bit_file_id, drive, filepath=None):

        value = (10*"%s\n")%(volume,
                             location_cookie,
                             size,
                             file_family,
                             pnfsFilename,
                             volume_filepath,
                             id,
                             volume_fileP,  #.id,
                             bit_file_id,
                             drive)
        
        Trace.trace(11,'value='+value)
        if filepath:
            self.writelayer(enstore_constants.XREF_LAYER, value, filepath)
        else:
            self.writelayer(enstore_constants.XREF_LAYER, value)
            self.get_xreference()

        return value
    
    # get the bit file id
    def get_bit_file_id(self, filepath=None):
        if filepath:
            bit_file_id = self.readlayer(enstore_constants.BFID_LAYER,
                                         filepath)[0]
        else:
            bit_file_id = self.readlayer(enstore_constants.BFID_LAYER,
                                         self.filepath)[0]
            self.bit_file_id = bit_file_id

        return bit_file_id

    # get the cross reference layer
    def get_xreference(self, filepath=None):

        #Get the xref layer information.
        if filepath:
            xinfo = self.readlayer(enstore_constants.XREF_LAYER, filepath)
        else:
            xinfo = self.readlayer(enstore_constants.XREF_LAYER)

        #Strip off whitespace from each line.
        xinfo = map(string.strip, xinfo[:10])
        #Make sure there are 10 elements.  Early versions only contain 9.
        # This prevents problems.
        xinfo = xinfo + ([UNKNOWN] * (10 - len(xinfo)))

        #If the class member value was used, store the values seperatly.
        if not filepath:
            try:
                self.volume = xinfo[0]
                self.location_cookie = xinfo[1]
                self.size = xinfo[2]
                self.origff = xinfo[3]
                self.origname = xinfo[4]
                self.mapfile = xinfo[5]
                self.pnfsid_file = xinfo[6]
                self.pnfsid_map = xinfo[7]
                self.bfid = xinfo[8]
                self.origdrive = xinfo[9]
            except ValueError:
                pass

            self.xref = xinfo

        return xinfo

    ##########################################################################

    # get the stat of file, or if non-existant, its directory
    def get_stat(self):
        for i in range(ATTEMPTS):
            try:
                # first the file itself
                self.pstat = os.stat(self.filepath)
                break
            except OSError, msg:
                time.sleep(1)
        else:
            # if that fails, try the directory
            if msg.errno == errno.ENOENT:
                for i in range(ATTEMPTS):
                    try:
                        self.pstat = os.stat(os.path.dirname(self.filepath))
                    except OSError, msg2:
                        time.sleep(1)
                else:
                    raise msg2
            else:
                self.major,self.minor = (0,0)
                raise msg

    # update all the stat info on the file, or if non-existent, its directory
    def pstatinfo(self,update=1):
        if update:
            self.get_stat()
        self.pstat_decode()

        try:
            code_dict = Devcodes.MajMin(self.pnfsFilename)
        except:
            code_dict={"Major":0,"Minor":0}
        self.major = code_dict["Major"]
        self.minor = code_dict["Minor"]

        #The following needs to go somewhere.  It was placed in the
        # initialization code at one time, but got lost.  What they do,
        # I do not know.
        self.rmajor = 0
        self.rminor = 0

    def log_err(self,func_name):
         exc,msg,tb=sys.exc_info()
         Trace.log(e_errors.INFO,"pnfs %s %s %s %s"%(
                 func_name, self.filepath, exc,msg))
         ##Note:  I had e_errors.ERROR, and lots of non-fatal errors
         ##were showing up in the weblog

    # get the uid from the stat member
    def pstat_decode(self):
	self.uid = ERROR
        self.uname = UNKNOWN
        self.gid = ERROR
        self.gname = UNKNOWN
        self.mode = 0
        self.mode_octal = 0
        self.file_size = ERROR

        try:
            self.uid = self.pstat[stat.ST_UID]
        except:
            self.log_err("pstat_decode uid")
        try:
            self.uname = pwd.getpwuid(self.uid)[0]
        except:
            self.log_err("pstat_decode uid")
        try:
            self.gid = self.pstat[stat.ST_GID]
        except:
            self.log_err("pstat_decode gid")
        try:
            self.gname = grp.getgrgid(self.gid)[0]
        except:
            self.log_err("pstat_decode gname")
        try:
            # always return mode as if it were a file, not directory, so
            #  it can use used in enstore cpio creation  (we will be
            #  creating a file in this directory)
            # real mode is available in self.stat for people who need it
            self.mode = (self.pstat[stat.ST_MODE] % 0777) | 0100000
            self.mode_octal = str(oct(self.mode))
        except:
            self.log_err("pstat_decode mode")
            self.mode = 0
            self.mode_octal = 0
        if os.access(self.filepath, os.F_OK): #self.exists == EXISTS:
            try:
                self.file_size = self.pstat[stat.ST_SIZE]
            except:
                self.log_err("pstat_decode file_size")

##############################################################################

    #Prints out the specified layer of the specified file.
    def player(self, intf):
        try:
            self.verify_existance()
            data = self.readlayer(intf.named_layer)
            for datum in data:
                print datum.strip()
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #For legacy perpouses.
    pcat = player
    
    #Snag the cross reference of the file inside self.file.
    #***LAYER 4***
    def pxref(self, intf):
        names = ["volume", "location_cookie", "size", "file_family",
                 "original_name", "map_file", "pnfsid_file", "pnfsid_map",
                 "bfid", "origdrive"]
        try:
            self.verify_existance()
            data = self.get_xreference()
            #With the data stored in lists, with corresponding values
            # based on the index, then just print them out.
            for i in range(len(names)):
                print "%s: %s" % (names[i], data[i])
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    #For legacy perpouses.
    pinfo = pxref

    #Prints out the bfid value for the specified file.
    #***LAYER 1***
    def pbfid(self, intf):
        try:
            self.verify_existance()
            self.get_bit_file_id()
            print self.bit_file_id
            return 0
        except IndexError:
            print UNKNOWN
            return 1
        except (IOError, OSError), detail:
            print str(detail)
            return 1

    #Print out the filesize of the file from this layer.  It should only
    # be here as long as pnfs does not support NFS ver 3 and the filesize
    # is longer than 2GB.
    #***LAYER 4***
    def pfilesize(self, intf):
        try:
            self.get_file_size()
            print self.file_size
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #If dupl is empty, then show the duplicate data for the file
    # (in self.file).  If dupl is there then set the duplicate for the file
    # in self.file to that in dupl.
    #***LAYER 3***
    def pduplicate(self, intf):
        #Handle the add/edit duplicate feature.
        if intf.file and intf.duplicate_file:
            if os.path.isfile(intf.duplicate_file):
                self.writelayer(enstore_constants.DUPLICATE_LAYER,
                                intf.duplicate_file)
            else:
                print "Specified duplicate file does not exist."
                
        #Display only the duplicates for the specified file.
        elif intf.file:
            print "%s:" % (self.filepath),
            for filename in self.readlayer(enstore_constants.DUPLICATE_LAYER):
                print filename,
            print
        else:
            #Display all the duplicates for every file specified.
            for file in os.listdir(os.getcwd()):
                intf.file = file
                self.__init__(intf.filepath)
                self.pduplicate(intf)

    def penstore_state(self, intf):
        fname = os.path.join(self.dir, ".(config)(flags)/disabled")
        print fname
        if os.access(fname, os.F_OK):# | os.R_OK):
            f=open(fname,'r')
            self.enstore_state = f.readlines()
            f.close()
            print "Enstore disabled:", self.enstore_state[0],
        else:
            print "Enstore enabled"
            
    def ppnfs_state(self, intf):
        fname = "%s/.(config)(flags)/.(id)(pnfs_state)" % self.dir
        if os.access(fname, os.F_OK | os.R_OK):
            f=open(fname,'r')
            self.pnfs_state = f.readlines()
            f.close()
            print "Pnfs:", self.pnfs_state[0],
        else:
            print "Pnfs: unknown"

##############################################################################

    def pls(self, intf):
        (directory, file) = os.path.split(self.filepath)
        filename = os.path.join(directory, "\".(use)(%s)(%s)\"" % \
                                (intf.named_layer, file))
        os.system("ls -alsF " + filename)
        
    def pecho(self, intf):
        try:
            self.writelayer(intf.named_layer, intf.text)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def prm(self, intf):
        try:
            self.writelayer(intf.named_layer, "")
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    def pcp(self, intf):
        try:
            f = open(intf.unixfile, 'r')

            data = f.readlines()
            file_data_as_string = ""
            for line in data:
                file_data_as_string = file_data_as_string + line

            f.close()

            self.writelayer(intf.named_layer, file_data_as_string)

            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    def psize(self, intf):
        try:
            self.set_file_size(intf.filesize)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
    
    def pio(self, intf):
        print "Feature not yet implemented."

        #fname = "%s/.(fset)(%s)(io)(on)" % (self.dir, self.file)
        #os.system("touch" + fname)
    
    def pid(self, intf):
        try:
            self.get_id()
            print_results(self.id)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def pshowid(self, intf):
        try:
            self.get_showid()
            print_results(self.showid)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        except (AttributeError,), detail:
            print "A valid pnfs id was not entered."
            return 1
    
    def pconst(self, intf):
        try:
            self.get_const()
            print_results(self.const)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def pnameof(self, intf):
        try:
            self.get_nameof()
            print_results(self.nameof)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        except (AttributeError,), detail:
            print "A valid pnfs id was not entered."
            return 1
        
    def ppath(self, intf):
        try:
            self.get_path()
            print_results(self.path)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        except (AttributeError,), detail:
            print "A valid pnfs id was not entered."
            return 1
        
    def pparent(self, intf):
        try:
            self.get_parent()
            print_results(self.parent)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        except (AttributeError,), detail:
            print "A valid pnfs id was not entered."
            return 1
    
    def pcounters(self, intf):
        try:
            self.get_counters()
            print_results(self.counters)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def pcursor(self, intf):
        try:
            self.get_cursor()
            print_results(self.cursor)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
            
    def pposition(self, intf):
        try:
            self.get_position()
            print_results(self.position)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def pdatabase(self, intf):
        try:
            self.get_database()
            print_results(self.database)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1


    def pdown(self, intf):
        if os.environ['USER'] != "root":
            print "must be root to create enstore system-down wormhole"
            return
        
        dname = "/pnfs/fs/admin/etc/config/flags"
        if not os.access(dname, os.F_OK | os.R_OK):
            print "/pnfs/fs is not mounted"
            return

        fname = "/pnfs/fs/admin/etc/config/flags/disabled"
        f = open(fname,'w')
        f.write(intf.reason)
        f.close()

        os.system("touch .(fset)(disabled)(io)(on)")
        
    def pup(self, intf):
        if os.environ['USER'] != "root":
            print "must be root to create enstore system-down wormhole"
            return
        
        dname = "/pnfs/fs/admin/etc/config/flags"
        if not os.access(dname, os.F_OK | os.R_OK):
            print "/pnfs/fs is not mounted"
            return

        os.remove("/pnfs/fs/admin/etc/config/flags/disabled")

    def pdump(self, intf):
        self.dump()

##############################################################################

class PnfsInterface(option.Interface):

    def __init__(self, args=sys.argv, user_mode=1):
        # fill in the defaults for the possible options
        #self.test = 0
        #self.status = 0
        #self.info = 0
        #self.file = ""
        #self.restore = 0
        #These my be used, they may not.
        #self.duplicate_file = None
        option.Interface.__init__(self, args=args, user_mode=user_mode)

    pnfs_user_options = {
        option.BFID:{option.HELP_STRING:"lists the bit file id for file",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"bfid",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"filename",
                     option.FORCE_SET_DEFAULT:option.FORCE,
		     option.USER_LEVEL:option.USER
                     },
        option.CAT:{option.HELP_STRING:"see --layer",
                    option.DEFAULT_VALUE:option.DEFAULT,
                    option.DEFAULT_NAME:"layer",
                    option.DEFAULT_TYPE:option.INTEGER,
                    option.VALUE_NAME:"file",
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"filename",
                    option.FORCE_SET_DEFAULT:option.FORCE,
                    option.USER_LEVEL:option.USER,
                    option.EXTRA_VALUES:[{option.DEFAULT_VALUE:option.DEFAULT,
                                          option.DEFAULT_NAME:"named_layer",
                                          option.DEFAULT_TYPE:option.INTEGER,
                                          option.VALUE_NAME:"named_layer",
                                          option.VALUE_TYPE:option.INTEGER,
                                          option.VALUE_USAGE:option.OPTIONAL,
                                          option.VALUE_LABEL:"layer",
                                          }]
                    },
        option.DUPLICATE:{option.HELP_STRING:"gets/sets duplicate file values",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"duplicate",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_USAGE:option.IGNORED,
		     option.USER_LEVEL:option.ADMIN,
                     option.EXTRA_VALUES:[{option.DEFAULT_VALUE:"",
                                           option.DEFAULT_NAME:"file",
                                           option.DEFAULT_TYPE:option.STRING,
                                           option.VALUE_NAME:"file",
                                           option.VALUE_TYPE:option.STRING,
                                           option.VALUE_USAGE:option.OPTIONAL,
                                           option.VALUE_LABEL:"filename",
                                         option.FORCE_SET_DEFAULT:option.FORCE,
                                           },
                                          {option.DEFAULT_VALUE:"",
                                          option.DEFAULT_NAME:"duplicate_file",
                                           option.DEFAULT_TYPE:option.STRING,
                                           option.VALUE_NAME:"duplicat_file",
                                           option.VALUE_TYPE:option.STRING,
                                           option.VALUE_USAGE:option.OPTIONAL,
                                       option.VALUE_LABEL:"duplicate_filename",
                                         option.FORCE_SET_DEFAULT:option.FORCE,
                                           },]
                     },
        option.ENSTORE_STATE:{option.HELP_STRING:"lists whether enstore " \
                                                 "is still alive",
                         option.DEFAULT_VALUE:option.DEFAULT,
                         option.DEFAULT_NAME:"enstore_state",
                         option.DEFAULT_TYPE:option.INTEGER,
                         option.VALUE_NAME:"directory",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.USER_LEVEL:option.USER,
                         option.FORCE_SET_DEFAULT:option.FORCE,
                     },
        option.FILE_FAMILY:{option.HELP_STRING:"gets file family tag, " \
                            "default; sets file family tag, optional",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_NAME:"file_family",
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_TYPE:option.STRING,
                       option.USER_LEVEL:option.USER,
                       option.VALUE_USAGE:option.OPTIONAL,
                   },
        option.FILE_FAMILY_WIDTH:{option.HELP_STRING:"gets file family " \
                        "width tag, default; sets file family tag, optional",
                             option.DEFAULT_VALUE:option.DEFAULT,
                             option.DEFAULT_NAME:"file_family_width",
                             option.DEFAULT_TYPE:option.INTEGER,
                             option.VALUE_TYPE:option.STRING,
                             option.USER_LEVEL:option.USER,
                             option.VALUE_USAGE:option.OPTIONAL,
                   },
        option.FILE_FAMILY_WRAPPER:{option.HELP_STRING:"gets file family " \
                       "width tag, default; sets file family tag, optional",
                               option.DEFAULT_VALUE:option.DEFAULT,
                               option.DEFAULT_NAME:"file_family_wrapper",
                               option.DEFAULT_TYPE:option.INTEGER,
                               option.VALUE_TYPE:option.STRING,
                               option.USER_LEVEL:option.USER,
                               option.VALUE_USAGE:option.OPTIONAL,
                   },

        option.FILES:{option.HELP_STRING:"lists all the files on specified " \
                                         "tape in volmap-tape",
                 option.DEFAULT_VALUE:option.DEFAULT,
                 option.DEFAULT_NAME:"files",
                 option.DEFAULT_TYPE:option.INTEGER,
                 option.VALUE_NAME:"volume_tape",
                 option.VALUE_TYPE:option.STRING,
                 option.VALUE_USAGE:option.REQUIRED,
                 option.USER_LEVEL:option.USER,
                 option.FORCE_SET_DEFAULT:option.FORCE,
                   },
	option.FILESIZE:{option.HELP_STRING:"print out real filesize",
			 option.VALUE_NAME:"file",
			 option.VALUE_TYPE:option.STRING,
			 option.VALUE_LABEL:"file",
                         option.USER_LEVEL:option.USER,
			 option.VALUE_USAGE:option.REQUIRED,
			 },
        option.INFO:{option.HELP_STRING:"see --xref",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"xref",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"filename",
                     option.USER_LEVEL:option.USER,
                     option.FORCE_SET_DEFAULT:option.FORCE,
                },
        option.LAYER:{option.HELP_STRING:"lists the layer of the file",
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.DEFAULT_NAME:"layer",
                      option.DEFAULT_TYPE:option.INTEGER,
                      option.VALUE_NAME:"file",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"filename",
                      option.FORCE_SET_DEFAULT:option.FORCE,
                      option.USER_LEVEL:option.USER,
                      option.EXTRA_VALUES:[{option.DEFAULT_VALUE:
                                                                option.DEFAULT,
                                            option.DEFAULT_NAME:"named_layer",
                                            option.DEFAULT_TYPE:option.INTEGER,
                                            option.VALUE_NAME:"named_layer",
                                            option.VALUE_TYPE:option.INTEGER,
                                            option.VALUE_USAGE:option.OPTIONAL,
                                            option.VALUE_LABEL:"layer",
                                            }]
                 },
        option.LIBRARY:{option.HELP_STRING:"gets library tag, default; " \
                                      "sets library tag, optional",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"library",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_TYPE:option.STRING,
                   option.USER_LEVEL:option.USER,
                   option.VALUE_USAGE:option.OPTIONAL,
                   },
        option.PNFS_STATE:{option.HELP_STRING:"lists whether pnfs is " \
                                              "still alive",
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.DEFAULT_NAME:"pnfs_state",
                      option.DEFAULT_TYPE:option.INTEGER,
                      option.VALUE_NAME:"directory",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.USER_LEVEL:option.USER,
                      option.FORCE_SET_DEFAULT:option.FORCE,
                      },
        option.STORAGE_GROUP:{option.HELP_STRING:"gets storage group tag, " \
                              "default; sets storage group tag, optional",
                         option.DEFAULT_VALUE:option.DEFAULT,
                         option.DEFAULT_NAME:"storage_group",
                         option.DEFAULT_TYPE:option.INTEGER,
                         option.VALUE_TYPE:option.STRING,
                         option.USER_LEVEL:option.ADMIN,
                         option.VALUE_USAGE:option.OPTIONAL,
                   },
        option.TAGS:{option.HELP_STRING:"lists tag values and permissions",
                option.DEFAULT_VALUE:option.DEFAULT,
                option.DEFAULT_NAME:"tags",
                option.DEFAULT_TYPE:option.INTEGER,
                option.VALUE_USAGE:option.IGNORED,
                option.USER_LEVEL:option.USER,
                option.EXTRA_VALUES:[{option.DEFAULT_VALUE:"",
                                      option.DEFAULT_NAME:"directory",
                                      option.DEFAULT_TYPE:option.STRING,
                                      option.VALUE_NAME:"directory",
                                      option.VALUE_TYPE:option.STRING,
                                      option.VALUE_USAGE:option.OPTIONAL,
                                      option.FORCE_SET_DEFAULT:option.FORCE,
                                      }]
                },
        option.TAG:{option.HELP_STRING:"lists the tag of the directory",
                    option.DEFAULT_VALUE:option.DEFAULT,
                    option.DEFAULT_NAME:"tag",
                    option.DEFAULT_TYPE:option.INTEGER,
                    option.VALUE_NAME:"named_tag",
                    option.VALUE_TYPE:option.STRING,
                    option.VALUE_USAGE:option.REQUIRED,
                    option.VALUE_LABEL:"tag",
                    option.FORCE_SET_DEFAULT:1,
                    option.USER_LEVEL:option.USER,
                    option.EXTRA_VALUES:[{option.DEFAULT_VALUE:"",
                                          option.DEFAULT_NAME:"directory",
                                          option.DEFAULT_TYPE:option.STRING,
                                          option.VALUE_NAME:"directory",
                                          option.VALUE_TYPE:option.STRING,
                                          option.VALUE_USAGE:option.OPTIONAL,
                                         option.FORCE_SET_DEFAULT:option.FORCE,
                                          }]
               },
        option.XREF:{option.HELP_STRING:"lists the cross reference " \
                                        "data for file",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"xref",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"filename",
                     option.USER_LEVEL:option.USER,
                     option.FORCE_SET_DEFAULT:option.FORCE,
                },
        }

    pnfs_admin_options = {
        option.CP:{option.HELP_STRING:"echos text to named layer of the file",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"cp",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_NAME:"unixfile",
                   option.VALUE_TYPE:option.STRING,
                   option.VALUE_USAGE:option.REQUIRED,
                   option.FORCE_SET_DEFAULT:option.FORCE,
                   option.USER_LEVEL:option.ADMIN,
                   option.EXTRA_VALUES:[{option.VALUE_NAME:"file",
                                         option.VALUE_TYPE:option.STRING,
                                         option.VALUE_USAGE:option.REQUIRED,
                                         option.VALUE_LABEL:"filename",
                                         },
                                        {option.VALUE_NAME:"named_layer",
                                         option.VALUE_TYPE:option.INTEGER,
                                         option.VALUE_USAGE:option.REQUIRED,
                                         option.VALUE_LABEL:"layer",
                                         },]
                   },
        option.CONST:{option.HELP_STRING:"",
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.DEFAULT_NAME:"const",
                      option.DEFAULT_TYPE:option.INTEGER,
                      option.VALUE_NAME:"file",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"filename",
                      option.FORCE_SET_DEFAULT:option.FORCE,
                      option.USER_LEVEL:option.ADMIN,
                      },
        option.COUNTERS:{option.HELP_STRING:"",
                         option.DEFAULT_VALUE:option.DEFAULT,
                         option.DEFAULT_NAME:"counters",
                         option.DEFAULT_TYPE:option.INTEGER,
                         option.VALUE_NAME:"file",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"filename",
                         option.FORCE_SET_DEFAULT:option.FORCE,
                         option.USER_LEVEL:option.ADMIN,
                         },
        option.COUNTERSN:{option.HELP_STRING:"(must have cwd in pnfs)",
                          option.DEFAULT_VALUE:option.DEFAULT,
                          option.DEFAULT_NAME:"countersN",
                          option.DEFAULT_TYPE:option.INTEGER,
                          option.VALUE_NAME:"dbnum",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.FORCE_SET_DEFAULT:option.FORCE,
                          option.USER_LEVEL:option.ADMIN,
                          },
        option.CURSOR:{option.HELP_STRING:"",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_NAME:"cursor",
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_NAME:"file",
                       option.VALUE_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.VALUE_LABEL:"filename",
                       option.FORCE_SET_DEFAULT:option.FORCE,
                       option.USER_LEVEL:option.ADMIN,
                       },
        option.DATABASE:{option.HELP_STRING:"",
                         option.DEFAULT_VALUE:option.DEFAULT,
                         option.DEFAULT_NAME:"database",
                         option.DEFAULT_TYPE:option.INTEGER,
                         option.VALUE_NAME:"file",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"filename",
                         option.FORCE_SET_DEFAULT:option.FORCE,
                         option.USER_LEVEL:option.ADMIN,
                         },
        option.DATABASEN:{option.HELP_STRING:"(must have cwd in pnfs)",
                          option.DEFAULT_VALUE:option.DEFAULT,
                          option.DEFAULT_NAME:"databaseN",
                          option.DEFAULT_TYPE:option.INTEGER,
                          option.VALUE_NAME:"dbnum",
                          option.VALUE_TYPE:option.STRING,
                          option.VALUE_USAGE:option.REQUIRED,
                          option.FORCE_SET_DEFAULT:option.FORCE,
                          option.USER_LEVEL:option.ADMIN,
                          },
        option.DOWN:{option.HELP_STRING:"creates enstore system-down " \
                                        "wormhole to prevent transfers",
                option.DEFAULT_VALUE:option.DEFAULT,
                option.DEFAULT_NAME:"down",
                option.DEFAULT_TYPE:option.INTEGER,
                option.VALUE_NAME:"reason",
                option.VALUE_TYPE:option.STRING,
                option.VALUE_USAGE:option.REQUIRED,
                option.FORCE_SET_DEFAULT:option.FORCE,
                option.USER_LEVEL:option.ADMIN,
                },
        option.DUMP:{option.HELP_STRING:"dumps info",
              option.DEFAULT_VALUE:option.DEFAULT,
              option.DEFAULT_NAME:"dump",
              option.DEFAULT_TYPE:option.INTEGER,
              option.VALUE_USAGE:option.IGNORED,
              option.USER_LEVEL:option.ADMIN,
              },
        option.ECHO:{option.HELP_STRING:"sets text to named layer of the file",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"echo",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"text",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.FORCE_SET_DEFAULT:option.FORCE,
                     option.USER_LEVEL:option.ADMIN,
                     option.EXTRA_VALUES:[{option.VALUE_NAME:"file",
                                           option.VALUE_TYPE:option.STRING,
                                           option.VALUE_USAGE:option.REQUIRED,
                                           option.VALUE_LABEL:"filename",
                                           },
                                          {option.VALUE_NAME:"named_layer",
                                           option.VALUE_TYPE:option.INTEGER,
                                           option.VALUE_USAGE:option.REQUIRED,
                                           option.VALUE_LABEL:"layer",
                                           },]
                },
        option.ID:{option.HELP_STRING:"prints the pnfs id",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"id",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_NAME:"file",
                   option.VALUE_TYPE:option.STRING,
                   option.VALUE_USAGE:option.REQUIRED,
                   option.VALUE_LABEL:"filename",
                   option.FORCE_SET_DEFAULT:option.FORCE,
                   option.USER_LEVEL:option.ADMIN,
              },
        option.IO:{option.HELP_STRING:"sets io mode (can't clear it easily)",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"io",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_NAME:"file",
                   option.VALUE_TYPE:option.STRING,
                   option.VALUE_USAGE:option.REQUIRED,
                   option.VALUE_LABEL:"filename",
                   option.FORCE_SET_DEFAULT:option.FORCE,
                   option.USER_LEVEL:option.ADMIN,
                   },
        option.LS:{option.HELP_STRING:"does an ls on the named layer " \
                                      "in the file",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"ls",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_NAME:"file",
                   option.VALUE_TYPE:option.STRING,
                   option.VALUE_USAGE:option.REQUIRED,
                   option.VALUE_LABEL:"filename",
                   option.FORCE_SET_DEFAULT:option.FORCE,
                   option.USER_LEVEL:option.ADMIN,
                   option.EXTRA_VALUES:[{option.DEFAULT_VALUE:option.DEFAULT,
                                         option.DEFAULT_NAME:"named_layer",
                                         option.DEFAULT_TYPE:option.INTEGER,
                                         option.VALUE_NAME:"named_layer",
                                         option.VALUE_TYPE:option.STRING,
                                         option.VALUE_USAGE:option.OPTIONAL,
                                         option.VALUE_LABEL:"layer",
                                         }]
              },
        option.NAMEOF:{option.HELP_STRING:"prints the filename of the pnfs id"\
                       " (CWD must be under /pnfs)",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_NAME:"nameof",
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_NAME:"pnfs_id",
                       option.VALUE_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.FORCE_SET_DEFAULT:option.FORCE,
                       option.USER_LEVEL:option.ADMIN,
                       },
        option.PARENT:{option.HELP_STRING:"prints the pnfs id of the parent " \
                       "directory (CWD must be under /pnfs)",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_NAME:"parent",
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_NAME:"pnfs_id",
                       option.VALUE_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.FORCE_SET_DEFAULT:option.FORCE,
                       option.USER_LEVEL:option.ADMIN,
                       },
        option.PATH:{option.HELP_STRING:"prints the file path of the pnfs id"\
                                        " (CWD must be under /pnfs)",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"path",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"pnfs_id",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.FORCE_SET_DEFAULT:option.FORCE,
                     option.USER_LEVEL:option.ADMIN,
                     },
        option.POSITION:{option.HELP_STRING:"",
                         option.DEFAULT_VALUE:option.DEFAULT,
                         option.DEFAULT_NAME:"position",
                         option.DEFAULT_TYPE:option.INTEGER,
                         option.VALUE_NAME:"file",
                         option.VALUE_TYPE:option.STRING,
                         option.VALUE_USAGE:option.REQUIRED,
                         option.VALUE_LABEL:"filename",
                         option.FORCE_SET_DEFAULT:option.FORCE,
                         option.USER_LEVEL:option.ADMIN,
                         },
        option.RM:{option.HELP_STRING:"deletes (clears) named layer of the file",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"rm",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_NAME:"file",
                   option.VALUE_TYPE:option.STRING,
                   option.VALUE_USAGE:option.REQUIRED,
                   option.VALUE_LABEL:"filename",
                   option.FORCE_SET_DEFAULT:option.FORCE,
                   option.USER_LEVEL:option.ADMIN,
                   option.EXTRA_VALUES:[{option.VALUE_NAME:"named_layer",
                                         option.VALUE_TYPE:option.INTEGER,
                                         option.VALUE_USAGE:option.REQUIRED,
                                         option.VALUE_LABEL:"layer",
                                         },]
                   },
        option.SHOWID:{option.HELP_STRING:"prints the pnfs id information",
                       option.DEFAULT_VALUE:option.DEFAULT,
                       option.DEFAULT_NAME:"showid",
                       option.DEFAULT_TYPE:option.INTEGER,
                       option.VALUE_NAME:"pnfs_id",
                       option.VALUE_TYPE:option.STRING,
                       option.VALUE_USAGE:option.REQUIRED,
                       option.FORCE_SET_DEFAULT:option.FORCE,
                       option.USER_LEVEL:option.ADMIN,
                       },
        option.SIZE:{option.HELP_STRING:"sets the size of the file",
                     option.DEFAULT_VALUE:option.DEFAULT,
                     option.DEFAULT_NAME:"size",
                     option.DEFAULT_TYPE:option.INTEGER,
                     option.VALUE_NAME:"file",
                     option.VALUE_TYPE:option.STRING,
                     option.VALUE_USAGE:option.REQUIRED,
                     option.VALUE_LABEL:"filename",
                     option.FORCE_SET_DEFAULT:option.FORCE,
                     option.USER_LEVEL:option.ADMIN,
                     option.EXTRA_VALUES:[{option.VALUE_NAME:"filesize",
                                           option.VALUE_TYPE:option.INTEGER,
                                           option.VALUE_USAGE:option.REQUIRED,
                                           },]
                },
        option.TAGECHO:{option.HELP_STRING:"echos text to named tag",
                        option.DEFAULT_VALUE:option.DEFAULT,
                        option.DEFAULT_NAME:"tagecho",
                        option.DEFAULT_TYPE:option.INTEGER,
                        option.VALUE_NAME:"text",
                        option.VALUE_TYPE:option.STRING,
                        option.VALUE_USAGE:option.REQUIRED,
                        option.FORCE_SET_DEFAULT:option.FORCE,
                        option.USER_LEVEL:option.ADMIN,
                        option.EXTRA_VALUES:[{option.VALUE_NAME:"named_tag",
                                            option.VALUE_TYPE:option.STRING,
                                            option.VALUE_USAGE:option.REQUIRED,
                                            option.VALUE_LABEL:"tag",
                                              },]
                   },
        option.TAGRM:{option.HELP_STRING:"removes the tag (tricky, see DESY "
                                         "documentation)",
                      option.DEFAULT_VALUE:option.DEFAULT,
                      option.DEFAULT_NAME:"tagrm",
                      option.DEFAULT_TYPE:option.INTEGER,
                      option.VALUE_NAME:"named_tag",
                      option.VALUE_TYPE:option.STRING,
                      option.VALUE_USAGE:option.REQUIRED,
                      option.VALUE_LABEL:"tag",
                      option.FORCE_SET_DEFAULT:option.FORCE,
                      option.USER_LEVEL:option.ADMIN,
                 },
        option.UP:{option.HELP_STRING:"removes enstore system-down wormhole",
                   option.DEFAULT_VALUE:option.DEFAULT,
                   option.DEFAULT_NAME:"up",
                   option.DEFAULT_TYPE:option.INTEGER,
                   option.VALUE_USAGE:option.IGNORED,
                   option.USER_LEVEL:option.ADMIN,
                   },
        option.VOLUME:{option.HELP_STRING:"lists all the volmap-tape for the" \
                                     " specified volume",
                 option.DEFAULT_VALUE:option.DEFAULT,
                 option.DEFAULT_NAME:"volume",
                 option.DEFAULT_TYPE:option.INTEGER,
                 option.VALUE_NAME:"volumename",
                 option.VALUE_TYPE:option.STRING,
                 option.VALUE_USAGE:option.REQUIRED,
                 option.FORCE_SET_DEFAULT:option.FORCE,
                 option.USER_LEVEL:option.ADMIN,
                   },
        }
    
    def valid_dictionaries(self):
        return (self.help_options, self.pnfs_user_options,
                self.pnfs_admin_options)

    # parse the options like normal but make sure we have other args
    def parse_options(self):
        self.pnfs_id = "" #Assume the command is a dir and/or file.
        self.file = ""
        self.directory = ""
        option.Interface.parse_options(self)

        if not self.option_list:
            self.print_usage("No valid options were given.")

        if getattr(self, "help", None):
            self.print_help()

        if getattr(self, "usage", None):
            self.print_usage()

##############################################################################

# This is a cleaner interface to access the tags in /pnfs

class Tag:
    def __init__(self, directory):
        self.dir = directory
    
    # write a new value to the specified tag
    # the file needs to exist before you call this
    # remember, tags are a propery of the directory, not of a file
    def writetag(self, tag, value, directory=None):
        if type(value) != type(''):
            value=str(value)
        if directory:
            fname = os.path.join(directory, ".(tag)(%s)"%(tag,))
        else:
            fname = os.path.join(self.dir, ".(tag)(%s)"%(tag,))
        f = open(fname,'w')
        f.write(value)
        f.close()

    # read the value stored in the requested tag
    def readtag(self, tag, directory=None):
        if directory:
            fname = os.path.join(directory, ".(tag)(%s)" % (tag,))
        else:
            fname = os.path.join(self.dir, ".(tag)(%s)" % (tag,))
        f = open(fname,'r')
        t = f.readlines()
        f.close()
        return t

    ##########################################################################

    #Print out the current settings for all directory tags.
    def ptags(self, intf):
        if hasattr(intf, "directory"):
            filename = os.path.join(os.path.abspath(intf.directory),
                                    ".(tags)(all)")
        else:
            filename = os.path.join(os.getcwd(), ".(tags)(all)")

        try:
            file = open(filename, "r")
            data = file.readlines()
        except IOError, detail:
            print detail
            return 1

        #print the top portion of the output.  Note: the values placed into
        # line have a newline at the end of them, this is why line[:-1] is
        # used to remove it.
        for line in data:
            try:
                tag = string.split(line[7:], ")")[0]
                tag_info = self.readtag(tag)
                print line[:-1], "=",  tag_info[0]
            except IOError, detail:
                print line[:-1], ":", detail

        #Print the bottom portion of the output.
        for line in data:
            tag_file = os.path.join(intf.directory, line[:-1])
            os.system("ls -l \"" + tag_file + "\"")

        return 0
    
    def ptag(self, intf):
        try:
            if hasattr(intf, "directory") and intf.directory:
                tag = self.readtag(intf.named_tag, intf.directory)
            else:
                tag = self.readtag(intf.named_tag)
            print tag[0]
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    def ptagecho(self, intf):
        try:
            self.writetag(intf.named_tag, intf.text)
        except (OSError, IOError), detail:
            print str(detail)
            return 1
        
    def ptagrm(self, intf):
        print "Feature not yet implemented."

    ##########################################################################

    #Print or edit the library
    def plibrary(self, intf):
        try:
            if intf.library == 1:
                print self.get_library()
            else:
                self.set_library(intf.library)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #Print or edit the file family.
    def pfile_family(self, intf):
        try:
            if intf.file_family == 1:
                print self.get_file_family()
            else:
                self.set_file_family(intf.file_family)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #Print or edit the file family wrapper.
    def pfile_family_wrapper(self, intf):
        try:
            if intf.file_family_wrapper == 1:
                print self.get_file_family_wrapper()
            else:
                self.set_file_family_wrapper(intf.file_family_wrapper)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #Print or edit the file family width.
    def pfile_family_width(self, intf):
        try:
            if intf.file_family_width == 1:
                print self.get_file_family_width()
            else:
                self.set_file_family_width(intf.file_family_width)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1

    #Print or edit the storage group.
    def pstorage_group(self, intf):
        try:
            if intf.storage_group == 1:
                print self.get_storage_group()
            else:
                self.set_storage_group(intf.storage_group)
            return 0
        except (OSError, IOError), detail:
            print str(detail)
            return 1


    ##########################################################################

    # store a new tape library tag
    def set_library(self,value, directory=None):
        if directory:
            self.writetag("library", value, directory)
        else:
            self.writetag("library", value)
            self.get_library()
            
        return value

    # get the tape library
    def get_library(self, directory=None):
        if directory:
            library = self.readtag("library", directory)[0].strip()
        else:
            library = self.readtag("library")[0].strip()
            self.library = library

        return library
    
    ##########################################################################

    # store a new file family tag
    def set_file_family(self, value, directory=None):
        if directory:
            self.writetag("file_family", value, directory)
        else:
            self.writetag("file_family", value)
            self.get_file_family()

        return value

    # get the file family
    def get_file_family(self, directory=None):
        if directory:
            file_family = self.readtag("file_family", directory)[0].strip()
        else:
            file_family = self.readtag("file_family")[0].strip()
            self.file_family = file_family

        return file_family

    ##########################################################################

    # store a new file family wrapper tag
    def set_file_family_wrapper(self, value, directory=None):
        if directory:
            self.writetag("file_family_wrapper", value, directory)
        else:
            self.writetag("file_family_wrapper", value)
            self.get_file_family_wrapper()

        return value

    # get the file family
    def get_file_family_wrapper(self, directory=None):
        if directory:
            file_family_wrapper = self.readtag("file_family_wrapper",
                                               directory)[0].strip()
        else:
            file_family_wrapper = self.readtag(
                "file_family_wrapper")[0].strip()
            self.file_family_wrapper = file_family_wrapper

        return file_family_wrapper

    ##########################################################################

    # store a new file family width tag
    # this is the number of open files (ie simultaneous tapes) at one time
    def set_file_family_width(self, value, directory=None):
        if directory:
            self.writetag("file_family_width", value, directory)
        else:
            self.writetag("file_family_width", value)
            self.get_file_family_width()

        return value

    # get the file family width
    def get_file_family_width(self, directory=None):
        if directory:
            file_family_width = self.readtag("file_family_width",
                                                      directory)[0].strip()
        else:
            file_family_width = self.readtag("file_family_width")[0].strip()
            self.file_family_width = file_family_width

        return file_family_width

    ##########################################################################

    # store a new storage group tag
    # this is group of volumes assigned to one experiment or group of users
    def set_storage_group(self, value, directory=None):
        if directory:
            self.writetag("storage_group", value, directory)
        else:
            self.writetag("storage_group", value)
            self.get_storage_group()

        return value

    # get the storage group
    def get_storage_group(self, directory=None):
        if directory:
            storage_group = self.readtag("storage_group", directory)[0].strip()
        else:
            storage_group = self.readtag("storage_group")[0].strip()
            self.storage_group = storage_group

        return storage_group

##############################################################################

class N:
    def __init__(self, dbnum):
        self.dir = os.getcwd()

    # get the cursor information
    def get_countersN(self, dbnum):
        fname = os.path.join(self.dir, ".(get)(counters)(%s)"%(dbnum,))
        f=open(fname,'r')
        self.countersN = f.readlines()
        f.close()
        return self.countersN

    # get the database information
    def get_databaseN(self, dbnum):
        fname = os.path.join(".(get)(database)(%s)"%(dbnum,))
        f=open(fname,'r')
        self.databaseN = f.readlines()
        f.close()
        self.databaseN = string.replace(self.databaseN[0], "\n", "")
        return self.databaseN

    def pdatabaseN(self, intf):
        try:
            self.get_databaseN(intf.dbnum)
            print_results(self.databaseN)
        except (OSError, IOError), detail:
            print str(detail)

    def pcountersN(self, intf):
        try:
            self.get_countersN(intf.dbnum)
            print_results(self.countersN)
        except (OSError, IOError), detail:
            print str(detail)
    


# This is a cleaner interface to access the file, as well as its
# metadata, in /pnfs

class File:
	# the file could be a simple name, or a dictionary of file attributes
	def __init__(self, file):
		if type(file) == type({}):	# a dictionary
			self.volume = file['external_label']
			self.location_cookie = file['location_cookie']
			self.size = file['size']
			if file.has_key('file_family'):
				self.file_family = file['file_family']
			else:
				self.file_family = "unknown"
			self.volmap = file['pnfs_mapname']
			self.pnfs_id = file['pnfsid']
			self.pnfs_vid = file['pnfsvid']
			self.bfid = file['bfid']
			self.drive = file['drive']
			self.path = file['pnfs_name0']
		else:
			self.path = os.path.abspath(file)
			# does it exist?
			if os.access(self.path, os.F_OK):
				f = open(self.layer_file(4))
				self.volume, self.location_cookie, self.size,\
				self.file_family, p_path, self.volmap,\
				self.pnfs_id, self.pnfs_vid, self.bfid,\
				self.drive = map(string.strip, f.readlines())
				f.close()
				if p_path != self.path:
					print 'different paths'
					print '\t f>', self.path
					print '\t 4>', p_path
			else:
				self.volume = ""
				self.location_cookie = ""
				self.size = 0
				self.file_family = ""
				self.volmap = ""
				self.pnfs_id = ""
				self.pnfs_vid = ""
				self.bfid = ""
				self.drive = ""
		return

	# layer_file(i) -- compose the layer file name
	def layer_file(self, i):
		return os.path.join(self.dir(), '.(use)(%d)(%s)'%(i, self.file()))

	# id_file() -- compose the id file name
	def id_file(self):
		return os.path.join(self.dir(), '.(id)(%s)'%(self.file()))

	# size_file -- compose the size file, except for the actual size
	def size_file(self):
		return os.path.join(self.dir(), '.(fset)(%s)(size)'%(self.file()))

	# dir() -- get the directory of this file
	def dir(self):
		return os.path.dirname(self.path)

	# file() -- get the basename of this file
	def file(self):
		return os.path.basename(self.path)

	# get_pnfs_id() -- get pnfs id from pnfs id file
	def get_pnfs_id(self):
		f = open(self.id_file())
		id = string.strip(f.read())
		f.close()
		return id

	def show(self):
		print "           file =", self.path
		print "         volume =", self.volume
		print "location_cookie =", self.location_cookie
		print "           size =", self.size
		print "    file_family =", self.file_family
		print "         volmap =", self.volmap
		print "        pnfs_id =", self.pnfs_id
		print "       pnfs_vid =", self.pnfs_vid
		print "           bfid =", self.bfid
		print "          drive =", self.drive
		return

	# set_size() -- set size in pnfs
	def set_size(self):
		real_size = os.stat(self.path)[stat.ST_SIZE]
		if real_size == self.size:	# do nothing
			return
		size = str(self.size)
		if size[-1] == 'L':
			size = size[:-2]
		fname = self.size_file()+'('+size+')'
		f = open(fname, "w")
		f.close()
		if real_size:
			# oops, have to reset it again
			f = open(fname, "w")
			f.close()
		return

	# update() -- write out to pnfs files
	def update(self):
		if not self.bfid:
			return
		if self.exists():
			# writing layer 1
			f = open(self.layer_file(1), 'w')
			f.write(self.bfid)
			f.close()
			# writing layer 4
			f = open(self.layer_file(4), 'w')
			f.write(self.volume+'\n')
			f.write(self.location_cookie+'\n')
			f.write(str(self.size)+'\n')
			f.write(self.file_family+'\n')
			f.write(self.path+'\n')
			f.write(self.volmap+'\n')
			# always use real pnfs id
			f.write(self.get_pnfs_id()+'\n')
			f.write(self.pnfs_vid+'\n')
			f.write(self.bfid+'\n')
			f.write(self.drive+'\n')
			f.close()
			# set file size
			self.set_size()
		return

	# exists() -- to see if the file exists in /pnfs area
	def exists(self):
		return os.access(self.path, os.F_OK)

	# create() -- create the file
	def create(self):
		# do not create if there is no BFID
		if not self.bfid:
			return
		if not self.exists():
			f = open(self.path, 'w')
			f.close()
			self.update()

	# update_bfid(bfid) -- change the bfid
	def update_bfid(self, bfid):
		if bfid != self.bfid:
			self.bfid = bfid
			self.update()

	# set() -- set values
	def set(self, file):
		changed = 0
		res = None
		if file.has_key('external_label'):
			self.volume = file['external_label']
			changed = 1
		if file.has_key('location_cookie'):
			self.location_cookie = file['location_cookie']
			changed = 1
		if file.has_key('size'):
			self.size = file['size']
			changed = 1
		if file.has_key('file_family'):
			self.file_family = file['file_family']
			changed = 1
		if file.has_key('pnfs_mapname'):
			self.volmap = file['pnfs_mapname']
			changed = 1
		if file.has_key('pnfsid'):
			self.pnfs_id = file['pnfsid']
			changed = 1
		if file.has_key('pnfsvid'):
			self.pnfs_vid = file['pnfsvid']
			changed = 1
		if file.has_key('bfid'):
			self.bfid = file['bfid']
			changed = 1
		if file.has_key('drive'):
			self.drive = file['drive']
			changed = 1
		if file.has_key('pnfs_name0'):
			self.path = file['pnfs_name0']
			changed = 1
		if changed:
			res = self.update()
		return res


##############################################################################
def do_work(intf):

    rtn = 0

    if intf.file:
        p=Pnfs(intf.file)
        t=None
        n=None
    elif intf.pnfs_id:
        p=Pnfs(intf.pnfs_id)
        t=None
        n=None
    elif hasattr(intf, "dbnum:") and intf.dbnum:
        p=None
        t=None
        n=N(intf.dbnum)
    else:
        p=None
        t=Tag(intf.directory)
        n=None
        
    for arg in intf.option_list:
        if string.replace(arg, "_", "-") in intf.options.keys():
            arg = string.replace(arg, "-", "_")
            for instance in [t, p, n]:
                if getattr(instance, "p"+arg, None):
                    rtn = apply(getattr(instance, "p" + arg), (intf,))
                    break
            else:
                print "p%s not found" % arg 

    return rtn

##############################################################################
if __name__ == "__main__":

    intf = PnfsInterface()

    intf._mode = "admin"

    do_work(intf)
