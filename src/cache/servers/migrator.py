#!/usr/bin/env python

##############################################################################
#
# $Id$
#
##############################################################################

# system import
import sys
import os
import time
import threading
import types
import copy
import errno
import logging
import statvfs
import random
import stat
import multiprocessing
import shutil
import string

# enstore imports
import e_errors
import configuration_client
import event_relay_client
import file_clerk_client
import info_client
import event_relay_messages
import generic_server
import dispatching_worker
import monitored_server
import option
import Trace
import enstore_constants
import enstore_functions2
import enstore_functions3
import encp_wrapper
import file_cache_status
import checksum
import strbuffer
import volume_family
import namespace
import set_cache_status

# enstore cache imports
#import cache.stub.mw as mw
import mw
import cache.messaging.mw_client
from cache.messaging.messages import MSG_TYPES as mt
import cache.en_logging.en_logging

DEBUGLOG=11 # log on this level to DEBUGLOG

# intermediate states of migrator
# to check in more details of what migrator is doing
IDLE="IDLE"
PACKAGING = "PACKAGING"
UNPACKAGING = "UNPACKAGING"
CHECKING_CRC = "CHECKING_CRC"
WRITING_TO_TAPE = "WRITING_TO_TAPE"
REGISTERING_ARCHIVE = "REGISTERING_ARCHIVE"
CLEANING = "CLEANING"
PREPARING_READ_FROM_TAPE = "PREPARING_READ_FROM_TAPE"
READING_FROM_TAPE = "READING_FROM_TAPE"

# find a common prefix of 2 strings
# presenting file paths (beginning with 1st position) 
def find_common_prefix(s1, s2):
    if len(s1) < len(s2): # swap s1 and s2
        t_s2 = s2
        s2 = s1
        s1 = t_s2
    s1_split = s1.split('/')
    s2_split = s2.split('/')
    common = []

    for i in range(len(s2_split)):
        if  s2_split[i] == s1_split[i]:
            common.append(s2_split[i])
        else:
            break
    p = '/'.join((common))
    #print "P", p
    return p


# find directory common for all files in a path
def find_common_dir(paths):
    # paths - list of absolute file paths
    dirs = []
    for path in paths:
        if path[0] != '/':
            return None # path must be absolute
        else:
            dirs.append(os.path.dirname(path))
    common_path = dirs[0]
    for i in range(1, len(dirs)):
        common_path = find_common_prefix(common_path, dirs[i])
    return common_path

# calculate file checksum
# returns a tuple (0_seeded_crc, 1_seeded_crc)
def file_checkum(f):
    bs = enstore_constants.MB # 1 MB)
    buf=(" "*bs)
    fstats = os.stat(f)
    fsize = fstats[stat.ST_SIZE]
    blocks = fsize / bs
    rest = fsize % bs
    crc = 0L # will calculate 0 seeded crc
    fd = os.open(f, 0)
    i = 0
    while i < blocks:
        i = i + 1
        r = strbuffer.buf_read(fd, buf, 0, bs)
        if r > 0:
            crc = checksum.adler32_o(crc, buf, 0, r)
        elif r < 0:
            Trace.log(e_errors.ERROR, "file_checksum error %s reading %s"%(r, f))
    if rest:
        r = strbuffer.buf_read(fd, buf, 0, rest)
        if r > 0:
            crc = checksum.adler32_o(crc, buf, 0, r)
        elif r < 0:
            Trace.log(e_errors.ERROR, "file_checksum error %s reading %s"%(r, f))
    # 1 seeded crc:
    crc_1_seeded = checksum.convert_0_adler32_to_1_adler32(crc, fsize)
    
    return crc, crc_1_seeded


# check files prepared for writing to tape
# runs in subprocess to deal with
# .nfs.... files
# @param package - package complete path
# exit code maps to True / False 
def _check_packaged_files(archive_area, package):
    Trace.trace(10, "_check_packaged_files: called with %s %s"%(archive_area, package))
    # create a temporay directory
    tmp_dir = os.path.join(archive_area, "tmp_CRC", os.path.dirname(package).lstrip("/"))
    if not os.path.exists(tmp_dir):
        try:
            os.makedirs(tmp_dir)
        except:
            Trace.handle_error()
            Trace.alarm(e_errors.ERROR, "Can not create tmp dir %s"%(tmp_dir,))
            sys.exit("0")

    # uwind the package into this directiry
    os.chdir(tmp_dir)
    rtn = enstore_functions2.shell_command2("tar --force-local -xf %s"%(package,))
    if rtn[0] != 0: # tar return code
        Trace.log(e_errors.ERROR, "Error unwinding tar file %s %s"(rtn[2], package)) #stderr
        sys.exit("0")

    # create list of files to check
    try:
        f = open("README.1st", "r")
    except:
        Trace.handle_error()
        sys.exit("0") # False
    # Check all files found in README.1st
    first = True
    for l in f.readlines():
        # skip the first line
        # it is the header
        if first:
            first = False
            continue
        lst = l.split(" ")
        Trace.trace(10, "_check_packaged_files: %s, lst %s"%(l, lst))
        cache_fn, pnfs_fn, crc = lst[0], lst[1], lst[2]
        fn = cache_fn.lstrip("/")
        crc = long(crc)
        crc_0, crc_1 = file_checkum(fn)
        check_result = True
        if crc_0 != crc and crc_1 != crc:
            check_result = False
            Trace.log(e_errors.ERROR, "selective CRC check error on %s. Calculated seed_0 %s seed_1 %s Expected %s"% \
                      (fn, crc_0, crc_1, crc))
            break
    # remove these temporary files
    f.seek(0)
    first = True
    Trace.trace(10, "_check_packaged_files: remove temporay files")
    for l in f.readlines():
        # skip the first line
        # it is the header
        if first:
            first = False
            continue
        lst = l.split(" ")
        Trace.trace(10, "_check_packaged_files: removing %s, lst %s"%(l, lst))
        cache_fn, pnfs_fn, crc = lst[0], lst[1], lst[2]
        fn = cache_fn.lstrip("/")
        os.remove(fn)
    os.remove("README.1st")
    Trace.trace(10, "_check_packaged_files: exiting with %s"%(check_result,))

    sys.exit(str(int(check_result))) # process must return a string value

# check and set name space tags
def ns_tags(directory, library_tag, sg_tag, ff_tag, ff_wrapper_tag, ff_width_tag):
    tag = namespace.Tag(directory)
    try:
        cl = tag.readtag("library")[0]
    except IOError,detail:
        if detail.errno == errno.ENOENT:
            cl = ""
    if cl != library_tag:
        Trace.trace(10, "write_to_tape: library tag: %s"%(library_tag,))
        tag.writetag("library", library_tag)
    try:
        csg = tag.readtag("storage_group")[0]
    except IOError,detail:
        if detail.errno == errno.ENOENT:
            csg = ""
    if csg != sg_tag:
        Trace.trace(10, "write_to_tape: SG tag: %s"%(sg_tag,))
        tag.writetag("storage_group", sg_tag)
    try:
        cff = tag.readtag("file_family")[0]
    except IOError,detail:
        if detail.errno == errno.ENOENT:
            cff = ""
    if cff != ff_tag:
        Trace.trace(10, "write_to_tape: FF tag: %s"%(ff_tag,))
        tag.writetag("file_family", ff_tag)
    try:
        cffwr = tag.readtag("file_family_wrapper")[0]
    except IOError,detail:
        if detail.errno == errno.ENOENT:
            cffwr = ""
    if cffwr != ff_wrapper_tag:
        Trace.trace(10, "write_to_tape: FF wrapper tag: %s"%(ff_wrapper_tag,))
        tag.writetag("file_family_wrapper", ff_wrapper_tag)
    try:
        cffw = tag.readtag("file_family_width")[0]
    except IOError,detail:
        if detail.errno == errno.ENOENT:
            cffw = ""
    if cffw != ff_width_tag:
        Trace.trace(10, "write_to_tape: FF width tag: %s"%(ff_width_tag,))
        tag.writetag("file_family_width", ff_width_tag)
    

class StorageArea():
    """
    This class is needed to effectively work with
    NFS mounted storage areas.
    It was found that writes over nfs are slow.
    We want to tar files on the nfs server itself and not over nfs
    """
    #  @param path - path to storage arear
    #  @param remotehost - remote host where the storage area resides
    def __init__(self, path, remotehost=""):
        self.path = path
        self.real_path = path # real path on this host
        self.remote_path = path # path on remote host if nfs mounted
        self.server = "localhost"

        if remotehost: 
            # find the real path
            self.real_path = os.path.realpath(self.path)
            if self.real_path != self.path:
                # there is a mount point or a link in the path
                # lookup in /etc/mtab
                f = open("/etc/mtab", "r")
                mtab_entries = f.readlines()
                for e in mtab_entries:
                    columns = e.split(" ")
                    dev = columns[0].strip()
                    mpoint = ' '.join(columns[1].translate(None, string.whitespace[:5]).split())
                    if mpoint != "/" and self.real_path.startswith(mpoint):
                        parts = self.real_path.partition(mpoint)
                        host, rpath = dev.split(":")
                        rpath.lstrip("/")
                        self.remote_path = os.path.join(rpath, parts[-1].lstrip("/"))
                        self.server = host
                        break

    def __str__(self):
        return "path %s real_path %s remote_path %s server %s"%(self.path,
                                                                self.real_path,
                                                                self.remote_path,
                                                                self.server)


    
class Migrator(dispatching_worker.DispatchingWorker, generic_server.GenericServer, mw.MigrationWorker):
    """
    Configurable Migrator
    """

    def load_configuration(self):
        self.my_conf = self.csc.get(self.name)
        # it was discovered that write rates ove nfs are slow
        # to deal with this problem packaging / unpackging will be done
        # directly on the nfs server if it defined as aggregation_host in configuration
        self.remote_aggregation_host = self.my_conf.get("aggregation_host", "")
        self.data_area = StorageArea(self.my_conf['data_area'], self.remote_aggregation_host
                                     ) # area on disk where original files are stored
        self.archive_area = StorageArea(self.my_conf['archive_area'],
                                        self.remote_aggregation_host) # area on disk where archvived files are temporarily stored
        self.stage_area = StorageArea(self.my_conf.get('stage_area',''),
                                      self.remote_aggregation_host)   # area on disk where staged files are stored
        self.tmp_stage_area = StorageArea(self.my_conf['tmp_stage_area'],
                                          self.remote_aggregation_host)  # area on disk where staged files are temporarily stored
        self.packages_location = self.my_conf.get("packages_dir", "") # directory in name space for packages

        self.blocking_factor =  self.my_conf.get("tar_blocking_factor", 20) # 20 is a default tar blocking factor

        if not self.packages_location:
            Trace.alarm(e_errors.ERROR, "Define packages_dir in cofiguration! Exiting")
            sys.exit(-1)
        if not os.path.exists(self.packages_location):
            try:
                os.makedirs(self.packages_location)
            except:
                Trace.handle_error()
                Trace.alarm(e_errors.ERROR, "Can not create packages_dir %s! Exiting"%(self.packages_location,))
                sys.exit(-1)
                
        self.my_dispatcher = self.csc.get(self.my_conf['migration_dispatcher']) # migration dispatcher configuration
        self.purge_watermarks = None
        if self.my_dispatcher:
          self.purge_watermarks = self.my_dispatcher.get("purge_watermarks", None) 
            
        # configuration dictionary required by MigrationWorker
        self.migration_worker_configuration = {'server':{}}
        self.migration_worker_configuration['server']['queue_work'] = "%s; {create: always}"%(self.my_dispatcher['migrator_work'],)
        self.migration_worker_configuration['server']['queue_reply'] = "%s; {create: always}"%(self.my_dispatcher['migrator_reply'],)        
        
        self.queue_in_name = self.name.split('.')[0]
        self.migration_worker_configuration['server']['queue_in'] = "%s; {create: receiver, delete: receiver}"%(self.queue_in_name,) # migrator input control queue
        # get amqp broker configuration - common for all servers
        # @todo - change name in configuration file to make it more generic, "amqp"
        self.migration_worker_configuration['amqp'] = {}
        self.migration_worker_configuration['amqp']['broker'] = self.csc.get("amqp_broker") # amqp broker configuration

        fc_conf = self.csc.get("file_clerk")
        # specify tape dismout delay for write operations
        self.delayed_dismount = None
        delayed_dismount = self.my_conf.get('dismount_delay', None)
        if delayed_dismount:
            try:
                self.delayed_dismount = int(delayed_dismount)
            except:
                self.delayed_dismount = None

        # period to check integrity of files to be written (like in the mover code)
        self.check_written_file_period = self.my_conf.get('check_written_file', 0)

        self.fcc = file_clerk_client.FileClient(self.csc, bfid=0,
                                                server_address=(fc_conf['host'],
                                                                fc_conf['port']))
        ic_conf = self.csc.get("info_server")
        self.infoc = info_client.infoClient(self.csc, 
                                            server_address=(ic_conf['host'],
                                                            ic_conf['port']))
        Trace.trace(10, "d_a %s a_a %s s_a %s t_s_a %s"%(self.data_area,
                                                         self.archive_area,
                                                         self.stage_area,
                                                         self.tmp_stage_area))

    def  __init__(self, name, cs):
        """
        Creates Migrator. Constructor gets configuration from enstore Configuration Server
        
        """
        # Obtain information from the configuration server cs.
        self.csc = cs

        generic_server.GenericServer.__init__(self, self.csc, name,
					      function = self.handle_er_msg)


        Trace.init(self.log_name, 'yes')
        self._do_print({'levels':range(5, 400)})
        try:
            self.load_configuration()
        except:
            Trace.handle_error()
            sys.exit(-1)

        self.alive_interval = monitored_server.get_alive_interval(self.csc,
                                                                  name,
                                                                  self.my_conf)
        dispatching_worker.DispatchingWorker.__init__(self, (self.my_conf['hostip'],
                                                             self.my_conf['port']),
                                                      use_raw=0)
        
        self.logger, self.tracer = cache.en_logging.en_logging.set_logging(self.log_name)
        Trace.log(e_errors.INFO, "create %s server instance, qpid client instance %s"%
                  (self.name,
                   self.migration_worker_configuration['amqp']))

        mw.MigrationWorker.__init__(self, name, self.migration_worker_configuration)

        """
        Leave these here so far, as there may be an argument for have a separate handler for eact type of the message

        self.set_handler(mt.MWC_ARCHIVE, self.handle_write_to_tape)
        self.set_handler(mt.MWC_PURGE, self.handle_purge)
        self.set_handler(mt.MWC_STAGE, self.handle_stage_from_tape)
        self.set_handler(mt.MWC_STATUS, self.handle_status)
        """
        self.status = None # internal status of migrator to report to Migration Dispatcher
        self.status_change_time = time.time()
        self.state = IDLE # intermediate state of migrator
        self.state_change_time = time.time()
        self.cur_id = None
        self.migration_file = None
        self.draining = False # if this is set, complete current work and exit.
        
        # we want all message types processed by one handler
        self.handlers = {}
        for request_type in (mt.MWC_PURGE,
                             mt.MWC_ARCHIVE,
                             mt.MWC_STAGE,
                             mt.MWC_STATUS):
            self.handlers[request_type] = self.handle_request
        
        Trace.log(e_errors.INFO, "Migrator %s instance created"%(self.name,))

        self.resubscribe_rate = 300
        self.erc = event_relay_client.EventRelayClient(self, function = self.handle_er_msg)
        Trace.erc = self.erc # without this Trace.notify takes 500 times longer
        self.erc.start([event_relay_messages.NEWCONFIGFILE],
                       self.resubscribe_rate)

        # start our heartbeat to the event relay process
        self.erc.start_heartbeat(name, self.alive_interval)

    # redefine __setattr__
    # to treat some attributes differently
    def __setattr__(self, attr, val):
        try:
            if attr == 'status':
               self.__dict__['status_change_time'] = time.time()
            if attr == 'state':
               self.__dict__['state_change_time'] = time.time()
               
        except:
           pass #don't want any errors here to stop us
        self.__dict__[attr] = val
       
    # is it time to data files integrity?
    # stolen from mover.py
    def check_written_file(self):
        rc = 0
        if self.check_written_file_period:
            ran = random.randrange(self.check_written_file_period,self.check_written_file_period*10,1)
            if (ran % self.check_written_file_period == 0):
                rc = 1
        return rc

    # check files prepared for writing to tape
    # @param package - package complete path
    # @return True/False
    # fork the process to check files
    # wait until it returns
    # this is needed because nfs creates .nfs files which
    # get removed only when the process exits
    # so the only way to remove temporay nfs directories is
    # to terminate the process that leaves .nfs files open
    def check_packaged_files(self, package):
        Trace.trace(10, "check_packaged_files creating __check_packaged_files %s %s %s %s "%(type(self.archive_area),self.archive_area, type(package), package ))
        self.state = CHECKING_CRC
        
        proc = multiprocessing.Process(target = _check_packaged_files, args = (self.archive_area.path, package))
        Trace.trace(10, "check_packaged_files  calling _check_packaged_files")
        proc.start()
        Trace.trace(10, "check_packaged_files _check_packaged_files started")
        proc.join()
        Trace.trace(10, "check_packaged_files: returns %s"%(proc.exitcode))
        
        # Remove temporary directory
        # created by _check_packaged_files here
        # to take care about .nfs.... files
        tmp_dir = os.path.join(self.archive_area.path, "tmp_CRC", os.path.dirname(package).lstrip("/"))
        Trace.trace(10, "check_packaged_files: removing temporary directories")
        try:
           shutil.rmtree(tmp_dir)
           return True
        except OSError, detail:
           Trace.log(e_errors.ERROR, "check_packaged_files: error removind directory %s: %s"%(tmp_dir, detail,))
           return False
    
    # pack files into a single aggregated file
    # if there are multiple files in request list
    # 
    def pack_files(self, request_list):
        Trace.trace(10, "pack_files: request_list %s"%(request_list,))
        if not request_list:
            return None
        cache_file_list = []
        ns_file_list = []
        bfids = []
        self.state = PACKAGING
        # create list of files to pack
        for component in request_list:
            cache_file_path = enstore_functions3.file_id2path(self.data_area.remote_path,
                                                              component['nsid']) # pnfsId
            ### Before packaging file we need to make sure that the packaged file
            ### containing these files is not already written.
            ### This can be done by checking duplicate files map.
            ### Implementation must be HERE!!!!
            Trace.trace(10, "pack_files: cache_file_path %s"%(cache_file_path,))
            
            if type(component['bfid']) == types.UnicodeType:
                component['bfid'] = component['bfid'].encode("utf-8")
            bfids.append(component['bfid'])
            # Check if such file exists in cache.
            # This should be already checked anyway.
            if os.path.exists(cache_file_path):
                cache_file_list.append((cache_file_path, component['path'], component['complete_crc']))
                ns_file_list.append(component['path']) # file path in name space
            else:
                Trace.log(e_errors.ERROR, "File aggregation failed. File %s does not exist in cache"%(cache_file_path))
                return None
        if len(cache_file_path) == 1: # single file
            src_path = cache_file_path
            dst = self.request_list[0][ 'path'] # complete file path in name space
        else: # multiple files
            # Create a special file containing the names
            # of file as known in the namespace.
            # This file can be used for metadate recovery.
            #
            # find the destination directory
            dst = find_common_dir(ns_file_list)
            if not dst:
                Trace.log(e_errors.ERROR, "File aggregation failed. Can not find common destination directory")
                return None

            # Create tar file name
            t = time.time()
            t_int = long(t)
            fraction = int((t-t_int)*1000) # this gradation allows 1000 distinct file names 
            src_fn = "package-%s-%s.%sZ"%(self.queue_in_name,
                                           time.strftime("%Y-%m-%dT%H:%M:%S",
                                                         time.localtime(t_int)),
                                           fraction)

            # Create archive directory
            archive_dir = os.path.join(self.archive_area.remote_path, src_fn)
            
            src_path = "%s.tar"%(os.path.join(archive_dir, src_fn),)
            special_file_name = "README.1st"
 
            if not os.path.exists(archive_dir):
                os.makedirs(archive_dir)
                
            os.chdir(archive_dir)
            special_file_name = "README.1st"
            special_file = open(special_file_name, 'w')
            special_file.write("List of cached files and original names\n")

            Trace.trace(10, "pack_files: cache_file_list: %s"%(cache_file_list,))
            for f, c_f, crc in cache_file_list:
                special_file.write("%s %s %s\n"%(f, c_f, crc))
            
            special_file.close()

            # Create list of files for tar
            file_list = open("file_list", "w")
            file_list.write("%s\n"%(special_file_name,))
            for f, junk, junk in cache_file_list:
               Trace.trace(10, "file_list entry %s"%(f,)) 
               file_list.write("%s\n"%(f,))
            file_list.close()


            # call tar command
            start_t = time.time()
            Trace.log(DEBUGLOG, "Starting tar of %s files to %s"%(len(cache_file_list), src_path,))

            if self.remote_aggregation_host:
                # run tar on the remote host
                Trace.trace(10, "will run tar on remote host %s"%(self.remote_aggregation_host,))
                tarcmd = 'export ENSSH=/usr/bin/ssh; enrsh %s "cd %s && tar -b %s --force-local -cf %s --files-from=file_list"'%(self.remote_aggregation_host,
                                                                                                                               archive_dir,
                                                                                                                               self.blocking_factor,
                                                                                                                               src_path,)
                Trace.trace(10, "tar cmd %s"%(tarcmd,))
            else:
                Trace.trace(10, "will run tar on local host")
                tarcmd = "tar -b %s --force-local -cf %s --files-from=file_list"%(self.blocking_factor, src_path,)
            
            rtn = enstore_functions2.shell_command2(tarcmd)
            Trace.trace(10, "tar returned %s"%(rtn,))
            
            if rtn[0] != 0: # tar return code
                Trace.log(e_errors.ERROR, "Error creating package %s %s"%(src_path, rtn[2])) #stderr
                return None, None, None
            
            t = time.time() - start_t
            fstats = os.stat(src_path)
            fsize = fstats[stat.ST_SIZE]/1000000.
            
            Trace.log(DEBUGLOG, "Finished tar to %s size %s rate %s MB/s"%(src_path, fsize, fsize/t))              
            Trace.log(e_errors.INFO, "Finished tar to %s size %s rate %s MB/s"%(src_path, fsize, fsize/t))              
        os.remove("file_list")

        # Qpid converts strings to unicode.
        # Encp does not like this.
        # Convert unicode to ASCII strings.
        if type(src_path) == types.UnicodeType:
            src_path = src_path.encode("utf-8")
        if type(dst) == types.UnicodeType:
            dst = dst.encode("utf-8")
        dst_path = "%s.tar"%(os.path.join(dst, src_fn))
        Trace.trace(10, "pack_files: returning %s %s %s"%(src_path, dst_path, bfids))
           
        return src_path, dst_path, bfids

    # clean up after write
    # remove temporary files
    # and directories
    def clean_up_after_write(self, tmp_file_path):
        Trace.trace(10, "clean_up_after_write: removing temporary file %s"%(tmp_file_path,))
        self.state = CLEANING        
        os.remove(tmp_file_path)

        # remove README.1st and file_list
        for f in ("README.1st", "file_list"):
           try:
              os.remove(os.path.join(os.path.dirname(tmp_file_path), f))
           except:
              pass
        # Remove temporary archive directory
        try:
            os.removedirs(os.path.dirname(tmp_file_path))
        except OSError, detail:
            Trace.log(e_errors.ERROR, "write_to_tape: error removing directory: %s"%(detail,))
            pass
        self.state = IDLE        
        
        
    # write aggregated file to tape
    def write_to_tape(self, request):
        # save request
        rq = copy.copy(request)
        Trace.trace(10, "write_to_tape: request %s"%(rq.content,))
        # save correlation_id
        request_list = rq.content['file_list']
        Trace.trace(10, "write_to_tape: request_list %s"%(request_list))
        if not request_list:
            raise e_errors.EnstoreError(None, "Write to tape failed: no files to write", e_errors.NO_FILES)
            
        # check if files can be written to tape
        write_enabled_counter = 0
        output_library_tag = []
        for component in request_list:
            bfid = component['bfid']
            # Convert unicode to ASCII strings.
            if type(bfid) == types.UnicodeType:
                bfid = bfid.encode("utf-8")
            rec = self.fcc.bfid_info(bfid)
            Trace.trace(10, "write_to_tape: bfid_info %s"%(rec,))

            if (rec['status'][0] == e_errors.OK):
                try:
                    if (rec['archive_status'] not in
                        (file_cache_status.ArchiveStatus.ARCHIVED,
                         file_cache_status.ArchiveStatus.ARCHIVING) and
                        (rec['deleted'] == "no")): # file can be already deleted by the archiving time
                        write_enabled_counter = write_enabled_counter + 1
                        # get the library tag and combine output library tag
                        Trace.trace(10, "write_to_tape: getting library tag for %s"%(rec['pnfs_name0']),)
                        tag = namespace.Tag(os.path.dirname(rec['pnfs_name0']))
                        try:
                            lib_tag =tag.readtag("library", os.path.dirname(rec['pnfs_name0']))
                        except:
                            Trace.handle_error()
                            Trace.log(e_errors.ERROR, "error reading library tag")
                            return False
                            Trace.trace(10, "write_to_tape: original library tag: %s"%(lib,))
                        # readtag returns a list with size 1 and a string as its element like
                        # ['LTO3GS,LTO3GS']
                        Trace.trace(10, "write_to_tape: library tag %s"%(lib_tag[0],))
                        if not lib_tag[0] in output_library_tag:
                            for lib in output_library_tag:
                                # the following code shold resolve cases when
                                # the lib_tag[0] is already a part of the comma separated tag in output_library_tag
                                if lib_tag[0] in lib.split(","):
                                    break
                            else:
                                output_library_tag.append(lib_tag[0])
                        
                        Trace.trace(10, "write_to_tape: output library tag %s"%(output_library_tag),)
                    else:
                        Trace.log(e_errors.INFO, "File was not included into package %s archive_status %s"%
                                  (rec['bfid'], rec['archive_status']))
                except Exception, detail:
                    Trace.log(DEBUGLOG, "FC error: %s. Returned status OK but still error %s"%(detail, rec)) 
                    
                
            else:
                Trace.log(DEBUGLOG,
                          "FC error: %s. File was not included into package %s archive_status %s"%
                          (rec['status'], rec['bfid'], rec['archive_status']))

        if write_enabled_counter != len(request_list):
            Trace.log(DEBUGLOG, "No files will be archived, because some of them or all have been already archived or being archived write_enabled_counter %s request_list lenght %s request id %s"%(write_enabled_counter, len(request_list), rq.correlation_id))
            Trace.log(e_errors.ERROR, "No files will be archived, because some of them or all are already archived or being archived")

            # send reply
            content = {"migrator_status":
                       mt.FAILED,
                       "detail": "REBUILD PACKAGE",
                       "name": self.name} # this may need more details
            status_message = cache.messaging.mw_client.MWRStatus(orig_msg=rq,
                                                     content= content)
            try:
                self._send_reply(status_message)
            except Exception, e:
                self.trace.exception("sending reply, exception %s", e)
            return False
            
        packed_file = self.pack_files(request_list)
        Trace.trace(10, "write_to_tape: packed_file %s"%(packed_file,))
        Trace.log(e_errors.INFO, "write_to_tape: packed_file %s"%(packed_file,))
        if packed_file:
            src_file_path, dst_file_path, bfid_list = packed_file
            self.migration_file = dst_file_path
            if self.check_written_file():
                # check the integrity of the packaged file
                Trace.log(e_errors.INFO, "selective CRC check for package %s"%(bfid_list,))
                try:
                    rc = self.check_packaged_files(src_file_path)
                except:
                    Trace.handle_error()
                    Trace.log(e_errors.ERROR, "error checking CRC")
                    return False
            
                    
                if not rc:
                    Trace.alarm(e_errors.ERROR, "selective CRC check failed for %s"%(bfid_list,))
                    # Remove temporary file
                    Trace.trace(10, "write_to_tape: removing temporary file %s"%(src_file_path,))

                    os.remove(src_file_path)

                    # remove README.1st and file_list
                    for f in ("README.1st", "file_list"):
                       try:
                          os.remove(os.path.join(os.path.dirname(src_file_path), f))
                       except:
                          pass
                    # Remove temporary archive directory
                    try:
                        os.removedirs(os.path.dirname(src_file_path))
                    except OSError, detail:
                        Trace.log(e_errors.ERROR, "write_to_tape: error removind directory: %s"%(detail,))
                        pass
                    content = {"migrator_status":
                               mt.FAILED,
                               "detail": "ARCHIVING FAILED",
                               "name": self.name} # this may need more details
                    status_message = cache.messaging.mw_client.MWRStatus(orig_msg=rq,
                                                             content= content)
                    try:
                        self._send_reply(status_message)
                    except Exception, e:
                        self.trace.exception("sending reply, exception %s", e)
                    return False
        else:
            src_file_path = dst_file_path = None
        if not (src_file_path and dst_file_path):
            # aggregation failed
            raise e_errors.EnstoreError(None, "Write to tape failed: no files to write", e_errors.NO_FILES)

        # deduce package destination path in name space
        # from bfid info of the first file in the package
        dst_package_fn = os.path.basename(dst_file_path)
        rec = self.fcc.bfid_info(bfid)
        if (rec['status'][0] != e_errors.OK):
            Trace.log(e_errors.ERROR,
                      "write_to_tape: write to tape failed: can not get bfid info %s"%(rec['status'],))
            return False
        v_f = volume_family.make_volume_family(rec['storage_group'],
                                               rec['file_family'],
                                               rec['wrapper'])

        # the package file will eventually go dst_dir
        # appended with volume label
        # we do not yet know the volume label
        dst_dir = os.path.join(self.packages_location, v_f) 
        Trace.trace(10, "write_to_tape: write to %s"%(dst_dir,))
        tmp_dst_dir = os.path.join(dst_dir, "tmp")
            
        if not os.path.exists(dst_dir):
            Trace.trace(10, "write_to_tape: creating dst directory %s"%(dst_dir,))
            os.makedirs(dst_dir)

        Trace.trace(10, "write_to_tape: tmp_dst_dir %s"%(tmp_dst_dir,))
        if not os.path.exists(tmp_dst_dir):
            Trace.trace(10, "write_to_tape: create tmp_dst_dir %s"%(tmp_dst_dir,))
            try:
                os.makedirs(tmp_dst_dir)
            except:
                Trace.handle_error()
                Trace.log(e_errors.ERROR, "Error creating tmp dst directory %s"%(tmp_dst_dir,))
                return False
                
        # convert output_library_tag to a comma separated string
        # if its size is more than one (multiple copies)
        if len(output_library_tag) == 1:
           output_library_tag_str = output_library_tag[0]
        else:
            output_library_tag_str = ","
            output_library_tag_str.join(output_library_tag)
        Trace.trace(10, "write_to_tape: dst library tag: %s"%(output_library_tag_str,))
        try:
            ns_tags(tmp_dst_dir,
                    output_library_tag_str,
                    rec['storage_group'],
                    rec['file_family'],
                    rec['wrapper'],
                    rec['file_family_width'])
        except:
            Trace.handle_error()
            return False

        Trace.trace(10, "write_to_tape: dst_file_path: %s"%(dst_file_path,))

        dst_file_path = os.path.join(tmp_dst_dir, dst_package_fn)
        Trace.trace(10, "write_to_tape: dst_file_path: %s"%(dst_file_path,))

        # Change archive_status
        for bfid in bfid_list:
            # fill the argumet list for
            # set_cache_status method
            set_cache_params = []
            set_cache_params.append({'bfid': bfid,
                                     'cache_status':None,# we are not changing this
                                     'archive_status': file_cache_status.ArchiveStatus.ARCHIVING,
                                     'cache_location': None})       # we are not changing this
        rc = set_cache_status.set_cache_status(self.fcc, set_cache_params)
        Trace.trace(10, "write_to_tape: will write %s into %s"%(src_file_path, dst_file_path,))
        #return
        # create encp request
        args = ["encp"]
        if self.delayed_dismount:
            args.append("--delayed-dismount")
            args.append(str(self.delayed_dismount))
        args.append(src_file_path)
        args.append(dst_file_path)
        Trace.trace(10, "write_to_tape: sending %s"%(args,))
        encp = encp_wrapper.Encp()
        # call encp
        self.state = WRITING_TO_TAPE
        try:
            rc = encp.encp(args)
        except:
            Trace.handle_error()
            Trace.log(e_errors.ERROR, "encp failed with exception")
            rc = -1
            
        Trace.trace(10, "write_to_tape: encp returned %s %s"%(rc, encp.exit_status))

        # encp finished
        if rc != 0:
            really_failed = True
            # check if this was a multiple cpy request
            if len(output_library_tag_str.split(",")) > 1:
                # check if the original was written to a tape successfully
                res = self.infoc.find_file_by_path(dst_file_path)
                Trace.trace(10, "write_to_tape: find file %s returned %s"%(dst_file_path, res))
                if e_errors.is_ok(res['status']) and res['deleted'] == "no":
                    # File exists.
                    # Check if it is in the active_file_copying
                    q_res = self.infoc.query_db("select bfid,remaining from active_file_copying where bfid='%s'"%(res['bfid'],))
                    Trace.trace(10, "write_to_tape: db query returned %s %s"%(rc, q_res))
                    
                    # Example of query return
                    #  {'ntuples': 1,
                    #   'fields': ('bfid', 'remaining''),
                    #   'status': ('ok', None),
                    # 'result': [('GCMS134403394000000', 1]}
                    #
                    if e_errors.is_ok(q_res['status']) and q_res['ntuples'] != 0:
                        # the original is active_file_copying
                        # which means it is on tape but the copy failed
                        Trace.alarm(e_errors.WARNING, "Original %s is on tape," \
                                    "but the copy failed. Check later if this file has a copy"%(res['bfid'],))
                        really_failed = False # the original is on tape
            if really_failed:
                Trace.log(e_errors.ERROR, "write_to_tape: encp write to tape failed: %s"%(rc,))
                set_cache_params = []
                # Change archive_status
                for bfid in bfid_list:
                    set_cache_params.append({'bfid': bfid,
                                             'cache_status':None,# we are not changing this
                                             'archive_status': "null",
                                             'cache_location': None})       # we are not changing this

                # this comment is added to please RB, which ignores
                # changes with whitespaces only
                rc1 = set_cache_status.set_cache_status(self.fcc, set_cache_params)
                self.clean_up_after_write(src_file_path)
                # remove tepmporary file in name space if exists
                Trace.trace(10, "write_to_tape: removing temp. file %s"%(dst_file_path,))
                try:
                    os.remove(dst_file_path)
                except:
                    pass
                return False
        
        # register archive file in file db
        self.state = REGISTERING_ARCHIVE
        res = self.infoc.find_file_by_path(dst_file_path)
        Trace.trace(10, "write_to_tape: find file %s returned %s"%(dst_file_path, res))
        
        if e_errors.is_ok(res['status']):
            dst_bfids = [] # to deal with possible multiple copies
            if res.has_key('file_list'):
                for rec in res['file_list']:
                   dst_bfids.append(rec['bfid'])
                   
            else:
                dst_bfids.append(res['bfid'])

            # move destination file to its final destination
            # create final destination directory
            # <packages_dir>/<volume_family>/<external_label>
            bfid_info = self.fcc.bfid_info(dst_bfids[0])
            if (bfid_info['status'][0] != e_errors.OK):
                Trace.log(e_errors.ERROR,
                          "write_to_tape: write to tape failed: can not get bfid info %s"%(bfid_info['status'],))
                return False
            # we need to use original (in case if there are multiple copies)
            #rec = self.infoc.find_the_original(dst_bfids[0])
            Trace.trace(10, "write_to_tape: find the original")
            try:
                rec = self.infoc.find_the_original(dst_bfids[0])
            except:
                Trace.trace(10, "write_to_tape: exception findingfind the original")
                Trace.handle_error()
            Trace.trace(10, "write_to_tape: find the original returned %s"%(rec,))
            
            if (rec['status'][0] != e_errors.OK):
                Trace.log(e_errors.ERROR,
                          "write_to_tape: write to tape failed: can not get bfid info %s"%(rec['status'],))
                return False
            original_pack_bfid = rec['original']
            if rec['original'] != dst_bfids[0]:
                # get bfid info of original
                bfid_info = self.fcc.bfid_info(rec['original'])
                if (bfid_info['status'][0] != e_errors.OK):
                    Trace.log(e_errors.ERROR,
                              "write_to_tape: write to tape failed: can not get bfid info %s"%(bfid_info['status'],))
                    return False
            
            rc = self.complete_write_to_tape(dst_file_path, dst_dir, bfid_info['external_label'],
                                             bfid_list, dst_bfids, output_library_tag_str, original_pack_bfid)
            if not rc:
                return rc
            #########
                                                 
        else:
            raise e_errors.EnstoreError(None, "Write to tape failed: %s"%(res['status'][1],), res['status'][0])

        # The file from cache was successfully written to tape.
        # Remove temporary file
        self.clean_up_after_write(src_file_path)
        
        status_message = cache.messaging.mw_client.MWRArchived(orig_msg=rq)
        try:
            self._send_reply(status_message)
        except Exception, e:
            self.trace.exception("sending reply, exception %s", e)
            return False
        
        return True # completed successfully, the request will be acknowledged


    # helper method to update cross references in namespace and update file records in File Clerk
    # @param src_path - name_space full name of the temporary package file
    # @param dst_dir - name_space destination directory for a package file
    # @param external_label - tape label for a package file
    # @param bfid_list - list of bfids of files in a package
    # @param dst_bfids - list of bfid(s) of package(s) 
    # @param output_library_tag - libray tag for the package file
    # @param original_pack_bfid - bfid or the original package tag for the package file
    # exit code True / False 
    def complete_write_to_tape(self, src_path, dst_dir, external_label, bfid_list, dst_bfids, output_library_tag, original_pack_bfid):
        final_dst_dir = os.path.join(dst_dir, external_label)
        final_dst_path = os.path.join(final_dst_dir, os.path.basename(src_path))
        if not os.path.exists(final_dst_dir):
            os.makedirs(final_dst_dir)

        # move file to its final destination in the name space
        Trace.trace(10, "complete_write_to_tape: move package in name space from %s to %s"%
                    (src_path, final_dst_path))
        try:
            os.rename(src_path, final_dst_path)
        except:
            Trace.handle_error()
            return False

        Trace.log(e_errors.INFO, "renamed %s to %s"%(src_path, final_dst_path))
        # change file name in layer 4 of name space
        try:
            sfs = namespace.StorageFS(final_dst_path)
            xrefs = sfs.get_xreference() # xrefs will not get used, sfs will be used instead
            Trace.trace(10, "xrefs %s %s %s %s %s %s %s %s %s %s %s"%(sfs.volume,
                                                                      sfs.location_cookie,
                                                                      sfs.size,
                                                                      sfs.origff,
                                                                      sfs.origname,
                                                                      sfs.mapfile,
                                                                      sfs.pnfsid_file,
                                                                      sfs.pnfsid_map,
                                                                      sfs.bfid,
                                                                      sfs.origdrive,
                                                                      sfs.crc))

            sfs.origname = final_dst_path
            sfs.set_xreference(sfs.volume,
                               sfs.location_cookie,
                               sfs.size,
                               sfs.origff,
                               sfs.origname,
                               sfs.mapfile,
                               sfs.pnfsid_file,
                               sfs.pnfsid_map,
                               sfs.bfid,
                               sfs.origdrive,
                               sfs.crc)
        except:
            Trace.handle_error()
            return False

        package_files_count = len(bfid_list)
        bfid_list = bfid_list + dst_bfids
        update_time = time.localtime(time.time())
        records = []
        pack_records = []
        rec = {}
        for bfid in bfid_list:
            del(rec) # to avoid interference
            # read record
            rec = self.fcc.bfid_info(bfid)
            if (rec['status'][0] != e_errors.OK):
                Trace.log(e_errors.ERROR,
                          "write_to_tape: write to tape failed: can not get bfid info %s"%(rec['status'],))
                return False
            rec['archive_status'] = file_cache_status.ArchiveStatus.ARCHIVED
            rec['package_id'] = original_pack_bfid
            rec['package_files_count'] = package_files_count
            rec['active_package_files_count'] = package_files_count
            rec['archive_mod_time'] = time.strftime("%Y-%m-%d %H:%M:%S", update_time)
            if rec['bfid'] in dst_bfids:

                # change pnfs_name0
                rec['pnfs_name0'] = final_dst_path
                # and original library
                rec['original_library'] = output_library_tag
                # package_id for a copy is its own bfid
                if rec['bfid'] != original_pack_bfid:
                    rec['package_id'] = rec['bfid']
                pack_records.append(rec)
            else:
                records.append(rec)
            Trace.trace(10, "complete_write_to_tape: sending modify record %s"%(rec,))
            rc = self.fcc.modify(rec)
            Trace.trace(10, "complete_write_to_tape: modify record returned %s"%(rc,))
            
            if not rc:
                return False

        if len(pack_records) > 1:
            # multiple copies
            for dupl in pack_records:
               if dupl['bfid'] != original_pack_bfid:
                   # create new bit-files - refences to a copy of original
                   for rec in records:
                       Trace.trace(10, "complete_write_to_tape: creating duplicates %s"%(rec,))
                       rec['original_bfid'] = rec['bfid']
                       rec['package_id'] = dupl['bfid']
                       rec['cache_status'] = file_cache_status.CacheStatus.PURGED
                       del(rec['bfid'])
                       Trace.trace(10, "complete_write_to_tape: sending new_bit_file %s"%(rec,))
                       rc = self.fcc.new_bit_file({'fc':rec})
                       Trace.trace(10, "complete_write_to_tape:  new_bit_file returned %s"%(rc,))
                       if rc['status'][0] != e_errors.OK:
                           Trace.log(e_errors.ERROR, "complete_write_to_tape: new_bit_file returned %s"%(rc,))
                           return False
                       rec['bfid'] = rc['fc']['bfid']
                       Trace.trace(10, "complete_write_to_tape: sending modify record %s"%(rec,))
                       rc = self.fcc.modify(rec)
                       Trace.trace(10, "complete_write_to_tape: modify record returned %s"%(rc,))
                       if rc['status'][0] != e_errors.OK:
                           Trace.log(e_errors.ERROR, "complete_write_to_tape: modify record returned %s"%(rc,))
                           return False

        return True
            
    # check all conditions for purging the file
    # returns True if purge conditions are met
    def really_purge(self, f_info):
        try:
            if (f_info['status'][0] == e_errors.OK and
                (f_info['archive_status'] == file_cache_status.ArchiveStatus.ARCHIVED) and # file is on tape
                (f_info['cache_status'] == file_cache_status.CacheStatus.PURGING_REQUESTED)):
                # Enable to purge a file if it is in the write cache
                # and it is a time to purge it.
                # Do not consider watermarks
                # because we do not want files to hang in write pool if it is not
                # the same as a read pool.
                if self.data_area.path != self.archive_area.path:
                    if f_info['cache_location'] == f_info['location_cookie']: # same location
                        return True

                if self.purge_watermarks:
                    directory = f_info['cache_location']
                    try:
                        stats = os.statvfs(directory)
                        avail = long(stats[statvfs.F_BAVAIL])*stats[statvfs.F_BSIZE]
                        total = long(stats[statvfs.F_BAVAIL])*stats[statvfs.F_BSIZE]*1.
                        fr_avail = avail/total
                        if fr_avail > 1 - self.purge_watermarks[1]:
                            rc = True
                        else:
                            rc = False
                    except OSError:
                        rc = True # file was removed before, proceed with purge anyway
                else:
                    rc = True
            else:
                rc = False
        except Exception, detail:
            Trace.log(DEBUGLOG, "really_purge failed %s. Why? %s"%(detail, f_info,))
            rc = False
        Trace.trace(10, "really_purge %s %s"%(f_info['bfid'], rc))
        return rc

    # purge files from disk
    def purge_files(self, request):
        # save request
        rq = copy.copy(request)
        Trace.trace(10, "purge_files: request %s"%(rq.content,))
        request_list = rq.content['file_list']
        set_cache_params = []
        cur_package_id = -1
        for component in request_list:
            bfid = component['bfid']
            # Convert unicode to ASCII strings.
            if type(bfid) == types.UnicodeType:
                bfid = bfid.encode("utf-8")

            rec = self.fcc.bfid_info(bfid)
            if self.really_purge(rec):
                rec['cache_status'] = file_cache_status.CacheStatus.PURGING
                Trace.trace(10, "purge_files: purging %s"%(rec,))
                set_cache_params.append({'bfid': bfid,
                                         'cache_status': file_cache_status.CacheStatus.PURGING,
                                         'archive_status': None,        # we are not changing this
                                         'cache_location': rec['cache_location']})     
                if rec['package_id'] and rec['package_id'] != bfid and cur_package_id != rec['package_id']:
                    # append a package file itself
                    cur_package_id = rec['package_id']
                    set_cache_params.append({'bfid': cur_package_id,
                                             'cache_status': file_cache_status.CacheStatus.PURGING,
                                             'archive_status': None,        # we are not changing this
                                             'cache_location': rec['cache_location']})     
                    
                    

        rc = set_cache_status.set_cache_status(self.fcc, set_cache_params)
        Trace.trace(10, "purge_files: set_cache_status 1 returned %s"%(rc,))
        Trace.trace(e_errors.INFO, "Will purge files in cache")
               
        for item in set_cache_params:
            try:
                Trace.trace(10, "purge_files: removing %s"%(item['cache_location'],))
                os.remove(item['cache_location'])
            except OSError, detail:
                if detail.args[0] != errno.ENOENT:
                    Trace.trace(10, "purge_files: can not remove %s: %s"%(item['cache_location'], detail))
                    Trace.log(e_errors.ERROR, "purge_files: can not remove %s: %s"%(item['cache_location'], detail))
            except Exception, detail:
                Trace.trace(10, "purge_files: can not remove %s: %s"%(item['cache_location'], detail))
                Trace.log(e_errors.ERROR, "purge_files: can not remove %s: %s"%(item['cache_location'], detail))
                
            try:
                os.removedirs(os.path.dirname(item['cache_location']))
                item['cache_status'] = file_cache_status.CacheStatus.PURGED
                Trace.log(e_errors.INFO, "purge_files: purged %s"%(item['cache_location'],))
            except OSError, detail:
                if detail.args[0] != errno.ENOENT:
                    Trace.log(e_errors.ERROR, "purge_files: error removind directory: %s"%(detail,))
                    Trace.trace(10, "purge_files: error removind directory: %s"%(detail,))
                else:
                    item['cache_status'] = file_cache_status.CacheStatus.PURGED
                    Trace.log(e_errors.INFO, "purge_files: purged %s"%(item['cache_location'],))
                    
            except Exception, detail:
                Trace.log(e_errors.ERROR, "purge_files: error removind directory: %s"%(detail,))

        rc = set_cache_status.set_cache_status(self.fcc, set_cache_params)
        Trace.trace(10, "purge_files: set_cache_status 2 returned %s"%(rc,))

        status_message = cache.messaging.mw_client.MWRPurged(orig_msg=rq)
        try:
            self._send_reply(status_message)
        except Exception, e:
            self.trace.exception("sending reply, exception %s", e)
            return False
        
        return True # completed successfully, the request will be acknowledged


    # stage files from tape
    # helper method for read_from_tape
    def stage_files(self, files_to_stage, package, set_cache_params):
        # append a package file
        files_to_stage.append(package)
        package_id = package['bfid']
        set_cache_params.append({'bfid': package['bfid'],
                                 'cache_status':file_cache_status.CacheStatus.STAGING,
                                 'archive_status': None,        # we are not changing this
                                 'cache_location': None})       # we are not changing this yet
        #rc = self.fcc.set_cache_status(set_cache_params)
        Trace.trace(10, "stage_files: will stage %s"%(set_cache_params,))
        rc = set_cache_status.set_cache_status(self.fcc, set_cache_params)
        if rc['status'][0] != e_errors.OK:
            Trace.log(e_errors.ERROR, "Package staging failed %s %s"%(package_id, rc ['status']))
            return True # return True so that the message is confirmed

        # create a temporary directory for staging a package
        # use package name for this
        stage_fname = os.path.basename(package['pnfs_name0'])
        # file name looks like:
        # /pnfs/fs/usr/data/moibenko/d2/LTO3/package-2011-07-01T09:41:46.0Z.tar
        tmp_stage_dirname = stage_fname.split(".tar")[0]
        tmp_stage_dir_path = os.path.join(self.tmp_stage_area.remote_path, tmp_stage_dirname)
        if not os.path.exists(tmp_stage_dir_path):
            try:
                os.makedirs(tmp_stage_dir_path)
            except:
                Trace.handle_error()
                pass
        tmp_stage_file_path = os.path.join(tmp_stage_dir_path, stage_fname)

        # now stage the package file
        if not os.path.exists(tmp_stage_file_path):
            # stage file from tape if it does not exist
            args = ["encp", "--skip-pnfs", "--override-deleted", "--get-bfid", package['bfid'], tmp_stage_file_path]  
            Trace.trace(10, "stage_files: sending %s"%(args,))
            encp = encp_wrapper.Encp()
            try:
                rc = encp.encp(args)
            except:
                Trace.handle_error()
                Trace.log(e_errors.ERROR, "encp failed with exception")
                rc = -1

            Trace.trace(10, "stage_files: encp returned %s"%(rc,))
            if rc != 0:
                # cleanup directories
                try:
                    os.removedirs(tmp_stage_dir_path)
                except:
                    pass

                # change cache_status back
                for rec in set_cache_params:
                    rec['cache_status'] = file_cache_status.CacheStatus.PURGED
                #rc = self.fcc.set_cache_status(set_cache_params)
                rc = set_cache_status.set_cache_status(self.fcc, set_cache_params)
                return False

        # unpack files
        Trace.trace(10, "stage_files: changing directory to %s"%(tmp_stage_dir_path,))
        os.chdir(tmp_stage_dir_path)
        #if len(files_to_stage) > 1:
        # untar packaged files
        # if package contains more than one file
        Trace.trace(10, "unwinding %s"%(stage_fname,))
        if self.remote_aggregation_host:
            # run tar on the remote host
            Trace.trace(10, "will run tar on remote host %s"%(self.remote_aggregation_host,))
            tarcmd = 'export ENSSH=/usr/bin/ssh; enrsh %s "cd %s && tar -b %s --force-local -xf %s"'% \
                     (self.remote_aggregation_host,
                      tmp_stage_dir_path,
                      self.blocking_factor,
                      stage_fname)
        else:
            tarcmd = "tar -b %s --force-local -xf %s"%(self.blocking_factor, stage_fname,)
        Trace.trace(10, "tar cmd %s"%(tarcmd,))
        rtn = enstore_functions2.shell_command2(tarcmd)
        Trace.trace(10, "unwind returned %s"%(rtn,))

        if rtn[0] != 0 : # tar return code
            Trace.log(e_errors.ERROR, "Error unwinding package %s %s"(stage_fname, rtn[2])) # stderr
            # clean up
            try:
                rc = enstore_functions2.shell_command("rm -rf *")
                rc = enstore_functions2.shell_command("rm -rf .*")
            except:
                pass

            return False

        new_set_cache_params = []

        # move files to their original location
        for rec in files_to_stage:
            if rec['bfid'] != rec['package_id']:
                src = rec.get('location_cookie', None)

                if not self.stage_area:
                    # file gets staged into the path
                    # defined by location_cookie
                    dst = src
                src = src.lstrip("/")
                if self.stage_area:
                    # file gets staged into the path
                    # defined by location_cookie
                    # prepended by stage_area
                    dst = os.path.join(self.stage_area.remote_path, src)

                Trace.trace(10, "stage_files: renaming %s to %s"%(src, dst))
                # create a destination directory
                if not os.path.exists(os.path.dirname(dst)):
                    try:
                        Trace.trace(10, "stage_files creating detination directory %s for %s"
                                    %(os.path.dirname(dst), dst))
                        os.makedirs(os.path.dirname(dst))
                    except Exception, detail:
                        Trace.log(e_errors.ERROR, "Package staging failed %s %s"%(package_id, detail))
                        return False


                try:
                    os.rename(src, dst)
                except Exception, detail:
                    Trace.trace(10, "stage_files: exception renaming file %s %s %s"%(src, dst, detail))
                    # get stats
                    try:
                        stats = os.stat(src)
                    except Exception, detail:
                        if detail.args[0] != errno.ENOENT:
                            Trace.log(e_errors.ERROR, "Package staging failed while renaming files %s %s"%(package_id, detail))
                            # change cache_status back
                            for rec in new_set_cache_params:
                                rec['cache_status'] = file_cache_status.CacheStatus.PURGED
                            #rc = self.fcc.set_cache_status(new_set_cache_params)
                            rc = set_cache_status.set_cache_status(self.fcc, new_set_cache_params)
                            return False


                Trace.trace(10, "stage_files: appending  new_set_cache_params %s"%(rec['bfid'],))
                new_set_cache_params.append({'bfid': rec['bfid'],
                                             'cache_status':file_cache_status.CacheStatus.CACHED,
                                             'archive_status': None,        # we are not changing this
                                             'cache_location': dst})
        # This is for package file
        new_set_cache_params.append({'bfid': rec['package_id'],
                                     'cache_status':file_cache_status.CacheStatus.PURGED, # we do not read a package from cache
                                     'archive_status': None,        # we are not changing this
                                     'cache_location': None})


        #rc = self.fcc.set_cache_status(new_set_cache_params)
        rc = set_cache_status.set_cache_status(self.fcc, new_set_cache_params)
        if rc['status'][0] != e_errors.OK:
            Trace.log(e_errors.ERROR, "Package staging failed %s %s"%(package_id, rc ['status']))
            return True # return True so that the message is confirmed

        # remove the rest (README.1st, file_list)
        Trace.trace(10, "stage_files: current dir %s"%(os.getcwd(),))
        rc = enstore_functions2.shell_command("rm -rf *")
        rc = enstore_functions2.shell_command("rm -rf .*")
        # the following files are created
        # -rw-r--r-- 1 root root      0 Jul 12 11:29 .(use)(1)(.package-2011-07-12T11:03:51.0Z.tar)
        # -rw-r--r-- 1 root root      0 Jul 12 11:29 .(use)(2)(.package-2011-07-12T11:03:51.0Z.tar)
        # -rw-r--r-- 1 root root      0 Jul 12 11:29 .(use)(3)(.package-2011-07-12T11:03:51.0Z.tar)
        # -rw-r--r-- 1 root root      0 Jul 12 11:29 .(use)(4)(.package-2011-07-12T11:03:51.0Z.tar)


        #remove the temporary directory
        try:
            os.removedirs(tmp_stage_dir_path)
        except OSError, errno.ENOTEMPTY:
            Trace.trace(10, "stage_files: dir not empty %s"%(tmp_stage_dir_path))
            os.system("ls -l %s >> /tmp/migrator_stage_%s.out"%(tmp_stage_dir_path, self.name))
        return True

    # read aggregated file from tape
    def read_from_tape(self, request):
        # save request
        rq = copy.copy(request)
        self.state = PREPARING_READ_FROM_TAPE
        Trace.trace(10, "read_from_tape: request %s"%(rq.content,))
        request_list = rq.content['file_list']
        # the request list must:
        # 1. Have a single component OR if NOT
        # 2. Have the same package bfid

        bfid_info = []
        files_to_stage = []
        if len(request_list) == 1:
            # check if the package staging is requested
            bfid = request_list[0]['bfid']
            if type(bfid) == types.UnicodeType:
                bfid = bfid.encode("utf-8")
            rec = self.fcc.bfid_info(bfid)
            Trace.trace(10, "read_from_tape: rec %s"%(rec,))

            if rec['status'][0] != e_errors.OK:
                Trace.log(e_errors.ERROR, "Package staging failed %s"%(rec ['status'],))
                return True # return True so that the message is confirmed
            
            package_id = rec.get('package_id', None)
            if package_id == bfid:
                # request to stage a package
                # get all information about children
                rc = self.fcc.get_children(package_id)
                Trace.trace(10, "read_from_tape, bfid_data %s"%(rc,))
                if rc ['status'][0] != e_errors.OK:
                    Trace.log(e_errors.ERROR, "Package staging failed %s %s"%(package_id, rc ['status']))
                    return True # return True so that the message is confirmed
                else:
                    bfid_info = rc['children'] 
            else: # single file
                bfid_info.append(rec)

        else:
            package_id = None
            for component in request_list:
                bfid = component['bfid']
                # Convert unicode to ASCII strings.
                if type(bfid) == types.UnicodeType:
                    bfid = bfid.encode("utf-8")

                rec = self.fcc.bfid_info(bfid)
                if rec['status'][0] == e_errors.OK:
                    if not package_id:
                        # read the package id if the First file
                        package_id = rec.get('package_id', None)

                    if package_id != rec.get('package_id', None):
                        Trace.log(e_errors.ERROR,
                                  "File does not belong to the same package and will not be staged %s %s"%
                                  (rec['bfid'], rec['pnfs_name0']))
                    else:
                        bfid_info.append(rec)

        package = self.fcc.bfid_info(package_id) 
        set_cache_params = [] # this list is needed to send set_cache_status command to file clerk
        Trace.log(e_errors.INFO, "Will stage package %s"%(package,))
        self.migration_file = package['pnfs_name0']

        # Internal list of bfid data is built
        # Create a list of files to get staged
        for  component in bfid_info:
            bfid = component['bfid']
            Trace.trace(10, "read_from_tape: rec1 %s"%(component,))
            if component['archive_status'] == file_cache_status.ArchiveStatus.ARCHIVED:  # file is on tape and it can be staged
                # check the state of each file
                if component['cache_status'] == file_cache_status.CacheStatus.CACHED:
                    # File is in cache and available immediately.
                    continue
                elif component['cache_status'] == file_cache_status.CacheStatus.STAGING_REQUESTED:
                    # file clerk sets this when opens a file
                    if component['bfid'] != package_id: # we stage files in the package, not the package itself
                        files_to_stage.append(component)
                        set_cache_params.append({'bfid': bfid,
                                                 'cache_status':file_cache_status.CacheStatus.STAGING,
                                                 'archive_status': None,        # we are not changing this
                                                 'cache_location': None})       # we are not changing this yet
                elif component['cache_status'] == file_cache_status.CacheStatus.STAGING:
                    # File is being staged
                    # Log this for the further investigation in
                    # case the file was not staged.
                    Trace.log(e_errors.INFO, "File is being staged %s %s"%(component['bfid'], component['pnfs_name0']))
                    continue
                else:
                    continue

        Trace.trace(10, "read_from_tape:  files to stage %s %s"%(len(files_to_stage), files_to_stage))
        if len(files_to_stage) != 0:
            try:
                self.state = READING_FROM_TAPE
                rc = self.stage_files(files_to_stage, package, set_cache_params)
            except:
                Trace.handle_error()
                return False
            if not rc:
                # stage has failed
                return False
        status_message = cache.messaging.mw_client.MWRStaged(orig_msg=rq)
        try:
            self._send_reply(status_message)
        except Exception, e:
            self.trace.exception("sending reply, exception %s", e)
            return False

        return True

    # unpack aggregated file
    def unpack_files(self):
        pass

    # return migrator status
    def migrator_status(self):
        return self.status
    


    workers = {mt.MWC_ARCHIVE: write_to_tape,
               mt.MWC_PURGE:   purge_files,
               mt.MWC_STAGE:   read_from_tape,
               }

    # handle all types of requests
    def handle_request(self, message):
        Trace.trace(10, "handle_request received: %s"%(message))
        if self.work_dict.has_key(message.correlation_id):
            # the work on this request is in progress
            return False
        #self.work_dict[message.correlation_id] = message # remove after debug AM!!
        # prepare work:
        request_type = message.properties["en_type"]
        self.cur_id = message.correlation_id
        if request_type in (mt.MWC_ARCHIVE, mt.MWC_PURGE, mt.MWC_STAGE):
            self.work_dict[message.correlation_id] = message
            if request_type == mt.MWC_ARCHIVE:
                self.status = mt.ARCHIVING
            elif request_type == mt.MWC_PURGE:
                self.status = mt.PURGING
                self.state = mt.PURGING
            elif request_type ==mt.MWC_STAGE:
                self.status = mt.STAGING
            confirmation_message = cache.messaging.mw_client.MWRConfirmation(orig_msg=message,
                                                                             content=message.content,
                                                                             reply_to=self.queue_in_name,
                                                                             correlation_id=message.correlation_id)
            # reply now to report name of the queue for inquiry commands
            # such as MWC_STATUS
            try:
                Trace.trace(10, "Sending confirmation")
                self._send_reply(confirmation_message)
            except Exception, e:
                self.trace.exception("sending reply, exception %s", e)
                return False
            
            # run worker
            try:
                if self.workers[request_type](self, message):
                    # work has completed successfully
                    del(self.work_dict[message.correlation_id])
                    if request_type == mt.MWC_ARCHIVE:
                        self.status = mt.ARCHIVED
                    elif request_type == mt.MWC_PURGE:
                        self.status = mt.PURGED
                    elif request_type ==mt.MWC_STAGE:
                        self.status = mt.CACHED
                    rc = True
                    self.state = IDLE 
                else:
                    rc = False
                if self.draining:
                    Trace.log(e_errors.INFO, "Completed final assignment. Will exit")
                    self.shutdown = True # exit gracefully
                return rc
            except:
                exc, detail, tb = sys.exc_info()
                Trace.handle_error(exc, detail, tb)
                # send error message
                content = {"migrator_status":
                           mt.FAILED,
                           "detail": "exception %s detail %s"%(exc, detail),
                           "name": self.name}
                status_message = cache.messaging.mw_client.MWRStatus(orig_msg=message,
                                                                     content= content)
                
        elif request_type in (mt.MWC_STATUS): # there could more request of such nature in the future
            content = {"migrator_status": self.status, "name": self.name} # this may need more details
            if not self.work_dict.has_key(message.correlation_id):
                # know nothing about this work
                # may be caused by restart of the migrator
                content['migrator_status'] = None
            status_message = cache.messaging.mw_client.MWRStatus(orig_msg=message,
                                                                 content= content)
            Trace.trace(10, "Sending status %s"%(status_message,))

            try:
                self._send_reply(status_message)
            except Exception, e:
                Trace.trace(10, "exception sending reply %s"%(e,))
                self.trace.exception("sending reply, exception %s", e)
                return False
            # work has completed successfully
            if self.work_dict.has_key(message.correlation_id):
                del(self.work_dict[message.correlation_id])
            return True
        return True

    """
    Leave these here so far, as there may be an argument for have a separate handler for eact type of the message
     def handle_write_to_tape(self, message):
        Trace.trace(10, "handle_write_to_tape received: %s"%(message))
        if self.work_dict.has_key(message.correlation_id):
            # the work on this request is in progress
            return False
        self.work_dict[message.correlation_id] = message
        self.status = file_cache_status.ArchiveStatus.ARCHIVING
        # conifrm receipt of request
        confirmation_message = cache.messaging.mw_client.MWRConfirmation(orig_msg=message, content=message.content, reply_to=self.queue_in_name)
        self.trace.debug("WORKER reply=%s",confirmation_message)
        try:
            self._send_reply(confirmation_message)
            self.trace.debug("worker_purge() reply sent, reply=%s", confirmation_message)
        except Exception, e:
            self.trace.exception("worker_purge(), sending reply, exception")         
        if self.write_to_tape(message.content):
            # work has completed successfully
            del(self.work_dict[message.correlation_id])
            self.status = file_cache_status.ArchiveStatus.ARCHIVED
            return True
        else:
            return False

    def handle_purge(self, message):
        Trace.trace(10, "handle_purge received: %s"%(message))
        if self.work_dict.has_key(message.correlation_id):
            # the work on this request is in progress
            return False
        self.work_dict[message.correlation_id] = message
        self.status = file_cache_status.CacheStatus.PURGING

        # conifrm receipt of request
        confirmation_message = cache.messaging.mw_client.MWRConfirmation(orig_msg=message, content=message.content, reply_to=self.queue_in_name)
        self.trace.debug("WORKER reply=%s",confirmation_message)
        try:
            self._send_reply(confirmation_message)
            self.trace.debug("worker_purge() reply sent, reply=%s", confirmation_message)
        except Exception, e:
            self.trace.exception("worker_purge(), sending reply, exception")         
        if self.purge_files(message.content):
            # work has completed successfully
            del(self.work_dict[message.correlation_id])
            self.status = file_cache_status.CacheStatus.PURGED
            return True
        else:
            return False
            
        
    def handle_stage_from_tape(self, message):
        Trace.trace(10, "handle_stage_from_tape received: %s"%(message))
        if self.work_dict.has_key(message.correlation_id):
            # the work on this request is in progress
            return False
        self.work_dict[message.correlation_id] = message
        self.status = file_cache_status.CacheStatus.STAGING
        # conifrm receipt of request
        confirmation_message = cache.messaging.mw_client.MWRConfirmation(orig_msg=message, content=message.content, reply_to=self.queue_in_name)
        self.trace.debug("WORKER reply=%s",confirmation_message)
        try:
            self._send_reply(confirmation_message)
            self.trace.debug("worker_purge() reply sent, reply=%s", confirmation_message)
        except Exception, e:
            self.trace.exception("worker_purge(), sending reply, exception")         
        if self.read_from_tape(message.content):
            # work has completed successfully
            del(self.work_dict[message.correlation_id])
            self.status = file_cache_status.CacheStatus.CACHED
            return True
        else:
            return False
    
    # handle status command from migration dispatcher
    def handle_status(self, message):
        Trace.trace(10, "handle_status received: %s"%(message))
        self.work_dict[message.correlation_id] = message
        status_message = cache.messaging.mw_client.MWRStatus(orig_msg=message, content={"migrator_status": self.status, "name": self.name})
        self.trace.debug("WORKER status reply=%s", status_message)
        try:
            self._send_reply(status_message)
            self.trace.debug("worker_purge() reply sent, reply=%s", status_message)
        except Exception, e:
            self.trace.exception("worker_purge(), sending reply, exception")         

            # work has completed successfully
            del(self.work_dict[message.correlation_id])
            self.status = file_cache_status.CacheStatus.CACHED
            return True
        else:
            return False
    """

    ###################################
    ### enstore commands
    ###################################

    # send current status
    def get_status(self, ticket):
        ticket['state'] = self.migrator_status()
        ticket['time_in_state'] = time.time() - self.status_change_time
        ticket['internal_state'] = self.state
        ticket['time_in_internal_state'] = time.time() - self.state_change_time
        ticket['current_id'] = self.cur_id
        ticket['current_migration_file'] = self.migration_file
        
        ticket['status'] = (e_errors.OK, None)
        self.reply_to_caller(ticket)

    # quit_and_exit gracefully
    # do not exit if work is in progress
    def quit_and_exit(self, ticket):
        self.draining = True
        Trace.log(e_errors.INFO, "Starting draining")
        ticket['status'] = (e_errors.OK, None)
        self.reply_to_caller(ticket)
        if self.status in (None,
                           mt.ARCHIVED,
                           mt.PURGED,
                           mt.CACHED):
            # currently there is no work
            # can exit right away
            Trace.log(e_errors.INFO, "Exit requested while no active work. Will exit")
            sys.exit(0)
        
class MigratorInterface(generic_server.GenericServerInterface):
    def __init__(self):
        # fill in the defaults for possible options
        generic_server.GenericServerInterface.__init__(self)


    migrator_options = {}

    # define the command line options that are valid
    def valid_dictionaries(self):
        return generic_server.GenericServerInterface.valid_dictionaries(self) \
               + (self.migrator_options,)

    parameters = ["migrator"]

    # parse the options like normal but make sure we have a migrator
    def parse_options(self):
        option.Interface.parse_options(self)
        # bomb out if we don't have a migrator
        if len(self.args) < 1 :
            self.missing_parameter(self.parameters())
            self.print_help()
            sys.exit(1)
        else:
            self.name = self.args[0]
    
def do_work():
    # get an interface
    intf = MigratorInterface()

    # create  Migrator instance
    migrator = Migrator(intf.name, (intf.config_host, intf.config_port))
    migrator.handle_generic_commands(intf)

    #Trace.init(migrator.log_name, 'yes') # leave it in the code to turn on when debugging

    migrator.start() # start mw

    t_n = 'migrator'
    while True:
        try:
            if thread_is_running(t_n):
                pass
            else:
                if migrator.draining:
                    migrator.stop()
                    break
                Trace.log(e_errors.INFO, "migrator %s (re)starting %s"%(intf.name, t_n))
                #lm.run_in_thread(t_n, lm.mover_requests.serve_forever)
                dispatching_worker.run_in_thread(t_n, migrator.serve_forever)

            time.sleep(10)
        except SystemExit:
            os._exit(0)
        if migrator.draining:
           os._exit(0)
    if migrator.draining:
        os._exit(0)
    Trace.alarm(e_errors.ALARM,"migrator %s finished (impossible)"%(intf.name,))

        
# check if named thread is running
def thread_is_running(thread_name):
    threads = threading.enumerate()
    for thread in threads:
       if ((thread.getName() == thread_name) and thread.isAlive()):
          Trace.trace(10, "%s running"%(thread_name,))
          return True
       else:
          Trace.trace(10, "%s running"%(thread_name,))
          return False

if __name__ == "__main__":
    do_work()
