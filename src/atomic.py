#!/usr/bin/env python
#
# $Id$
#

import os
#import sys
import stat
import errno
#import delete_at_exit
#import exceptions
import time
import Trace

def _open1(pathname,mode=0666):
    #delete_at_exit.register(pathname)
    fd = os.open(pathname, os.O_CREAT|os.O_EXCL|os.O_RDWR, mode)
    return fd

##  From man open(2)
##       O_EXCL  When used with O_CREAT, if the file already exists
##               it is an error and the open will fail.  O_EXCL  is
##               broken on NFS file systems, programs which rely on
##               it for performing locking  tasks  will  contain  a
##               race   condition.   The  solution  for  performing
##               atomic file locking using a lockfile is to  create
##               a  unique file on the same fs (e.g., incorporating
##               hostname and pid), use link(2) to make a  link  to
##               the  lockfile.  If  link()  returns 0, the lock is
##               successful.  Otherwise, use stat(2) on the  unique
##               file  to  check if its link count has increased to
##               2, in which case the lock is also successful.


def unique_id():
    t=time.time()
    dp=("%10.9f"%(t-int(t),)).split('.')[1]
    a=time.ctime(t).split(" ")
    b="."
    c=b.join((a[4],dp))
    a[4]=c
    b=" "
    tm=b.join(a)
    return tm.replace(" ", "_")

    
def _open2(pathname,mode=0666):
    __pychecker__ = "unusednames=i"

    #Create a unique temporary filename.
    #tmpname = "%s_%s_%s_%s_%s_%s_%s_lock" % (
    #    os.uname()[1], os.getpid(), os.getuid(), os.getgid(),
    #    os.geteuid(), os.getegid(), time.ctime(time.time()).replace(" ", "_"))
    tmpname = "%s_%s_%s_%s_%s_%s_%s_lock" % (
        os.uname()[1], os.getpid(), os.getuid(), os.getgid(),
        os.geteuid(), os.getegid(), unique_id())
    tmpname = os.path.join(os.path.dirname(pathname), tmpname)

    #Record encp to delete this temporary file on (failed) exit.
    #delete_at_exit.register(tmpname)

    #Create and open the temporary file.
    try:
        Trace.trace(5, "atomic.open 0 %s"%(tmpname,))
        fd_tmp = os.open(tmpname, os.O_CREAT|os.O_EXCL|os.O_RDWR, mode)
    except OSError, msg:
        Trace.trace(5, "atomic.open 1 %s"%(msg,))
        #If the newly created file exists, try opening it without the
        # exclusive create.  This is probably a symptom of the O_EXCL
        # race condition mentioned above.  Since, this is a unique filename
        # two encps can not be attempting to create the temporary file
        # simultaniously.  Thus, this error should be ignored; though any
        # errors from this os.open() are real.
        if getattr(msg, "errno", None) == errno.EEXIST:
            fd_tmp = os.open(tmpname, os.O_RDWR)
        else:
            #delete_at_exit.delete()
            raise OSError, msg

    ok = 0
    s = None #initalize
    #delete_at_exit.register(pathname)
    try:
        os.link(tmpname, pathname)
        ok = 1
    except OSError, detail:
        Trace.trace(5, "atomic.open 2 %s"%(detail,))
        #If the output file already exists, we should be able to stop now.
        # However, EEXIST is given for three cases.
        # 1) The first is that the file does already exist.
        # 2) The second occurs from a race condition inherent to the NFS
        #    V2 protocol.  The link() call fails, but the infact does
        #    succeed to create the directory entry and increase the link
        #    count to two.
        # 3) There is a bug in pnfs that the directory entry is
        #    successfully created, but the link count fails to be
        #    increased from one to two.
        #
        #Unfortunately, this means that we need to enter the following
        # loop for both cases to determine which case it is.

        try:
            #There are timeout issues with pnfs... keep trying.
            for i in range(5):
                s = os.stat(tmpname)
                if s and s[stat.ST_NLINK]==2:
                    #We know it is case 2.
                    ok = 1
                    break
                
                time.sleep(1)
            else:
                if detail.args[0] == errno.EEXIST:
                    #We now know it is case 1.
                    raise OSError, detail
        except OSError, detail:
            Trace.trace(5, "atomic.open 3 %s"%(detail,))
            #ok = 0
            os.close(fd_tmp)
            os.unlink(tmpname)
            #delete_at_exit.unregister(pathname)
            #delete_at_exit.delete()
            raise OSError, detail

    if ok:
        try:
            fd=os.open(pathname, os.O_RDWR, mode)
            os.unlink(tmpname)
            os.close(fd_tmp)
            return fd
        except OSError, detail:
            Trace.trace(5, "atomic.open 4 %s"%(detail,))
            raise OSError, detail
    else:
        #delete_at_exit.unregister(pathname)
        """
        if os.path.basename(pathname) in os.listdir(os.path.dirname(pathname)):
            #Check if the filesystem is corrupted.  If there is a file
            # listed in a directory that does not point to a valid inode the
            # directory is corrupted.  When the user tries to write a file
            # with the same name as the corrupted file the link operation
            # will (now) fail.  To test for this case get the full directory
            # listing and check to see if it is there.  If so, corrupted
            # directory.  If not, some other error occured.
            rtn_errno = getattr(errno, str("EFSCORRUPTED"), errno.EIO)
            msg = os.strerror(rtn_errno) + ": " + "Filesystem is corrupt" \
                  + ": " + pathname
        """
        
        if s and s[stat.ST_NLINK] > 2:
            #If there happen to be more than 2 hard links to the same file.
            # This should never happen.
            rtn_errno = getattr(errno, str("EMLINK"),
                                getattr(errno, str("EIO")))
            msg = os.strerror(rtn_errno) + ": " + str(s[stat.ST_NLINK]) \
                  + ": " + pathname
        elif s:
            try:
                s2 = os.stat(pathname)
            except OSError:
                s2 = None
                
            if s2 and s[stat.ST_NLINK] == 1 and s2[stat.ST_NLINK] == 1 \
                       and s[stat.ST_INO] == s2[stat.ST_INO]:
                #We know it is case 3.
                rtn_errno = errno.EAGAIN
                msg = os.strerror(rtn_errno) + ": " + "Filesystem is corrupt"

                os.close(fd_tmp)
                #This case is different.  Since there are two directory
                # entries pointing to the file with a link count of 1, we
                # need to delete correct path.  This will leave the
                # temporary lock file as a ghost file.
                os.unlink(pathname)

                raise OSError(rtn_errno, msg) #This case is different.
            else:
                #If there is only one link to the file.  In this case the link
                # failed.  The use of "ENOLINK" is for Linux, IRIX and SunOS.
                # The "EFTYPE" is for OSF1.
                rtn_errno = getattr(errno, str("ENOLINK"),
                                    getattr(errno, str("EFTYPE")))
                msg = os.strerror(rtn_errno) + ": " + str(s[stat.ST_NLINK]) \
                      + ": " + pathname
        else:
            #If we get here, then something really bad happened.
            rtn_errno = getattr(errno, str("ENOLINK"),
                                getattr(errno, str("EFTYPE")))
            msg = os.strerror(rtn_errno) + ": " + "Unknown" \
                  + ": " + pathname
            
        os.close(fd_tmp)
        os.unlink(tmpname)
        #return -(detail.errno) #return errno values as negative.
        #delete_at_exit.delete()
        raise OSError(rtn_errno, msg)

#Since the point of this modules is to override the default open function,
# we want to suppress the "shadows builtin" warning message.
__pychecker__ = "no-shadowbuiltin"
open = _open2

