#
# Classes to create the enstore plots.
#
##############################################################################
# system import
import string
import os
import time
import calendar
import stat

# enstore imports
import enstore_functions
import enstore_files
import enstore_constants
import Trace

YES = 1
NO = 0
WRITE = "to"

# file extensions
PTS = ".pts"
GNU = ".gnuplot"

HOURS_IN_DAY = ["00", "01", "02", "03", "04", "05", "06", "07", "08", \
                "09", "10", "11", "12", "13", "14", "15", "16", \
                "17", "18", "19", "20", "21", "22", "23"]

STAMP_JPG = "%s%s"%(enstore_constants.STAMP, enstore_constants.JPG)

def sort_stamp_files(tmp_stamps):
    # sort the stamp files so that all mount per hour stamps are at the end in
    # descending date order.  first get the other plots to the front.
    jpg_stamp_files = []
    tmp_stamps.sort()
    # now move all list elements that are not mph stamps to new list, & delete them
    # from the old
    i = 0
    num_stamps = len(tmp_stamps)
    while i < num_stamps:
	if string.find(tmp_stamps[i][0], enstore_constants.MPH_FILE) == -1:
	    # this is not an mph stamp 
	    jpg_stamp_files.append(tmp_stamps.pop(i))
	    num_stamps = num_stamps - 1
	else:
	    # this is mph file, leave it here for later sorting, skip to next stamp
	    i = i + 1
    # now we should have jpg_stamp_files full of non mph stamps and only mph stamps
    # left in tmp_stamps.  reverse sort these and add them at end of other stamps
    tmp_stamps.reverse()
    jpg_stamp_files = jpg_stamp_files + tmp_stamps
    return (jpg_stamp_files)

def ignore_file(file, ignore):
    for ignore_string in ignore:
	if not string.find(file, ignore_string) == -1:
	    # this file has a string meaning 'ignore this file' in it
		return YES
    else:
	return NO

def find_files(files, dir, ignore):
    # find all files with ".jpg" in them. fill
    # in the lists above with those files with and without the "_stamp" 
    # string from this group. also find the ps files
    tmp_stamps = []
    jpg_files = []
    ps_files = []
    for file in files:
	if ignore_file(file, ignore) == YES:
	    continue
	if not string.find(file, enstore_constants.JPG) == -1:
	    # this file has '.jpg' in it
	    if not string.find(file, STAMP_JPG) == -1:
		# this is a postage stamp file
		tmp_stamps.append((file, 
				   os.stat("%s/%s"%(dir, file))[stat.ST_MTIME]))
	    else:
		jpg_files.append((file,
				  os.stat("%s/%s"%(dir, file))[stat.ST_MTIME]))
	elif not string.find(file, enstore_constants.PS) == -1:
	    # this file has '.ps' in it
            ps_files.append((file, os.stat("%s/%s"%(dir, file))[stat.ST_MTIME]))
    return (jpg_files, tmp_stamps, ps_files)

def find_jpg_files(dir):
    # given the directory to look in, find all files with ".jpg" in them. fill
    # in the lists above with those files with and without the "_stamp" 
    # string from this group. also find the ps files
    files = os.listdir(dir)
    ignore = [enstore_constants.MPH,]
    jpg_files, stamp_files, ps_files = find_files(files, dir, ignore)
    jpg_files.sort()
    ps_files.sort()
    jpg_stamp_files = sort_stamp_files(stamp_files)
    return (jpg_files, jpg_stamp_files, ps_files)

def convert_to_jpg(psfile, file_name):
    os.system("convert -rotate 90 -geometry 120x120 -modulate -20 %s %s%s"%(psfile,
									 file_name,
									 STAMP_JPG))
    #JPG_STAMP_FILES.append("%s%s"%(file_name, STAMP_JPG))
    os.system("convert -rotate 90 %s %s%s"%(psfile, file_name, 
					    enstore_constants.JPG))
    #JPG_FILES.append("%s%s"%(file_name, enstore_constants.JPG))

# return the time to be included in the title of the plots
def plot_time():
    return "(Plotted: %s)"%(enstore_functions.format_time(time.time()),)

class EnPlot(enstore_files.EnFile):

    def __init__(self, dir, name):
	enstore_files.EnFile.__init__(self, dir+"/"+name)
	self.name = name
	self.dir = dir
	self.ptsfile = self.file_name+PTS
	self.psfile = self.file_name+enstore_constants.PS
	self.gnufile = self.file_name+GNU

    def install(self, dir):
        # create the ps file, copy it to the users dir
	os.system("gnuplot %s;cp %s %s;"%(self.gnufile, self.psfile, dir))
	# make a jpg version of the file including a postage stamp sized one
	convert_to_jpg(self.psfile, "%s/%s"%(dir, self.name))

    def open(self, mode='w'):
	Trace.trace(10,"enfile open "+self.file_name)
	self.openfile = open(self.ptsfile, mode)

    def cleanup(self, keep, pts_dir):
        if not keep:
            # delete the gnu command file and the data points file
            os.system("rm %s;rm %s*"%(self.gnufile, self.ptsfile))
        else:
            if pts_dir:
                # move these files somewhere
                os.system("mv %s %s;mv %s* %s"%(self.gnufile, pts_dir,
                                                self.ptsfile, pts_dir))

class MphGnuFile(enstore_files.EnFile):

    def write(self, gnuinfo):
	self.openfile.write("set terminal postscript color\n"+ \
	                   "set xlabel 'Hour'\nset yrange [0 : ]\n"+ \
	                   "set xrange [ : ]\nset ylabel 'Mounts'\nset grid\n")
	for info in gnuinfo:
	    self.openfile.write("set output '"+info[3]+ \
			       "'\nset title 'Mount Count For "+info[0]+ \
	                       " (Total = "+info[1]+") "+plot_time()+"'\nplot '"+info[2]+ \
	                       "' using 1:2 t '' with impulses lw 20\n")

class MphDataFile(EnPlot):

    def __init__(self, dir):
	EnPlot.__init__(self, dir, enstore_constants.MPH_FILE)

    # do not do the actual open here, we will do it when plotting because we
    # may need to open more than one file.  
    def open(self):
	pass

    # same for close as open. all files are already closed.
    def close(self):
	pass

    def install(self, dir):
        # create the ps file, copy it to the users dir
	os.system("gnuplot %s;"%(self.gnufile,))
	# now copy each created ps file and make a jpg version of each of 
	# the file including a postage stamp sized one
	for (psfile, day) in self.psfiles:
	    os.system("cp %s %s;"%(psfile, dir))
	    convert_to_jpg(psfile, "%s/%s.%s"%(dir, self.name, day))

    # make the mounts per hour plot file
    def plot(self, data):
	# sum the data together based on hour boundaries. we will only plot 1
	# day per plot though.
	date_only = {}
	ndata = {}
	gnuinfo = []
	self.psfiles = []
	self.total_mounts = {}
	for [dev, time, strt] in data:
	    if strt == enstore_files.MMOUNT:
	        # this was the record of the mount having been done
	        adate = time[0:13]
	        date_only[time[0:10]] = 0
	        try:
	            ndata[adate] = ndata[adate] + 1
	        except:
	            ndata[adate] = 1
	# open the file for each day and write out the data points
	days = date_only.keys()
	days.sort()
	for day in days:
	    fn = self.ptsfile+"."+day
	    pfile = open(fn, 'w')
	    total = 0
	    for hour in HOURS_IN_DAY:
	        tm = day+":"+hour
	        try:
	            pfile.write(hour+" "+repr(ndata[tm])+"\n")
	            total = total + ndata[tm]
	        except:
	            pfile.write(hour+" 0\n")
	    else:
	        # now we must save info for the gnuplot file
		self.psfile =  "%s.%s%s"%(self.file_name, day, enstore_constants.PS)
	        gnuinfo.append([day, repr(total), fn, self.psfile])
		self.psfiles.append((self.psfile, day))
	        pfile.close()

		# save the info in order to use it to update the file containing the
		# information on total mounts/day that have been done up to this 
		# day.
		self.total_mounts[day] = total
	else:
	    # we must create our gnu plot command file too
	    gnucmds = MphGnuFile(self.gnufile)
	    gnucmds.open('w')
	    gnucmds.write(gnuinfo)
	    gnucmds.close()


class MpdGnuFile(enstore_files.EnFile):

    def write(self, outfile, ptsfile, total_mounts):
	self.openfile.write("set terminal postscript color\n"+ \
			    "set xlabel 'Date'\n"+\
			    "set timefmt \"%Y-%m-%d\"\n"+ \
			    "set yrange [0 : ]\n"+ \
			    "set xrange [ : ]\n"+ \
			    "set xdata time\n"+ \
			    "set format x \"%y-%m-%d\"\n"+ \
			    "set ylabel 'Mounts'\n"+\
			    "set grid\n"+ \
			    "set output '"+outfile+"'\n"+\
			    "set title 'Mounts/Day (Total = "+\
			    total_mounts+") "+plot_time()+"'\n"+\
			    "plot '"+ptsfile+"' using 1:2 t '' with impulses lw 20\n")

class MpdDataFile(EnPlot):

    def __init__(self, dir):
	EnPlot.__init__(self, dir, enstore_constants.MPD_FILE)

    def get_all_mounts(self, new_mounts_d):
	today = time.strftime("%Y-%m-%d",time.localtime(time.time()))
	mounts_l = []
	total_mounts = 0
	if self.openfile:
	    mounts_l = self.openfile.readlines()
	    for line in mounts_l:
		[day, count] = string.split(string.strip(line))
		if new_mounts_d.has_key(day):
		    # if this is today replace the old count with the new value
		    if day == today:
			mounts_l.remove(line)
			mounts_l.append("%s %s\n"%(day, new_mounts_d[day]))
			total_mounts = total_mounts + new_mounts_d[day]
		    else:
			total_mounts = total_mounts + string.atoi(count)
		    del new_mounts_d[day]
		else:
		    total_mounts = total_mounts + string.atoi(count)

	# now add to list any of the new days that were not present in the old list
	for day in new_mounts_d.keys():
	    mounts_l.append("%s %s\n"%(day, new_mounts_d[day]))
	    total_mounts = total_mounts + new_mounts_d[day]
	return (mounts_l, total_mounts)

    def open(self):
	if os.path.isfile(self.ptsfile):
	    EnPlot.open(self, 'r')

    # make the mounts per day plot file
    def plot(self, new_mounts_d):
	# the data passed to us is a dict of total mount counts for the days that
	# were just plotted.  in effect this is new data that must be merged with
	# the data currently in the total mount count file.  will read in current
	# data and add any new stuff to it.  if the file contains data for today, 
	# we will overwrite it with our new data which is presumed to be more 
	# recent.
	(mounts_l, total_mounts) = self.get_all_mounts(new_mounts_d)
	if self.openfile:
	    self.openfile.close()
	self.openfile = open(self.ptsfile, 'w')
	for line in mounts_l:
	    self.openfile.write(line)
	# don't need to close the file as it is closed by the caller

	# now create the gnuplot command file
	gnucmds = MpdGnuFile(self.gnufile)
	gnucmds.open('w')
	gnucmds.write(self.psfile, self.ptsfile, repr(total_mounts))
	gnucmds.close()


class MlatGnuFile(enstore_files.EnFile):

    def write(self, outfile, ptsfile):
	self.openfile.write("set output '"+outfile+"\n"+ \
                           "set terminal postscript color\n"+ \
                           "set title 'Mount Latency in Seconds "+plot_time()+"'\n"+ \
                           "set xlabel 'Date'\n"+ \
                           "set timefmt \"%Y-%m-%d:%H:%M:%S\"\n"+ \
                           "set logscale y\n"+ \
	                   "set xdata time\n"+ \
	                   "set xrange [ : ]\n"+ \
	                   "set ylabel 'Latency'\n"+ \
	                   "set grid\n"+ \
	                   "set format x \"%m-%d\"\n"+ \
	                   "plot '"+ptsfile+"' using 1:2 t '' with points\n")

class MlatDataFile(EnPlot):

    def __init__(self, dir):
	EnPlot.__init__(self, dir, enstore_constants.MLAT_FILE)

    # make the mount latency plot file
    def plot(self, data):
        # mount data (mount requests and the actual mounting) are not 
	# necessarily time ordered when read from the files.  2 or more 
	# mount requests may occur before any actual volume has been mounted.
	# also, since log files are closed/opened on day boundaries with no
	# respect as to whats going on in the system, a log file may begin
	# with several mount satisfied messages which have no matching 
	# requests in the file.  also the file may end with several requests
	# that are not satisfied until the next day or the next log file.
	# to make things simpler for us to plot, the data will be ordered 
	# so that each mount request is immediately followed by the actual
        # mount satisfied message.
	data.sort()
	last_mount_req = ""
	# write out the data points
	for [dev, time, strt] in data:
	    if strt == enstore_files.MMOUNT:
	        # this was the record of the mount having been done
	        if not last_mount_req == "":
	            # we have recorded a mount req 
	            ltnc = self.latency(last_mount_req, time)
	            self.openfile.write(time+" "+repr(ltnc)+"\n")

	            # initialize so any trailing requests are not plotted
	            last_mount_req == ""
	    else:
	        # this was the mount request
	        last_mount_req = time
	# we must create our gnu plot command file too
	gnucmds = MlatGnuFile(self.gnufile)
	gnucmds.open('w')
	gnucmds.write(self.psfile, self.ptsfile)
	gnucmds.close()

    # subtract two times and return their difference
    def latency(self, time1, time2):
	# first convert each time into a tuple of the form -
	#  (year, month, day, hour, minutes, seconds, 0, 0, -1)
	# then convert the tuple into a seconds value and subtract the
	# two to get the latency in seconds
	t1 = (string.atoi(time1[0:4]), string.atoi(time1[5:7]), \
	      string.atoi(time1[8:10]), string.atoi(time1[11:13]), \
	      string.atoi(time1[14:16]), string.atoi(time1[17:]), 0, 0, -1)
	t2 = (string.atoi(time2[0:4]), string.atoi(time2[5:7]), \
	      string.atoi(time2[8:10]), string.atoi(time2[11:13]), \
	      string.atoi(time2[14:16]), string.atoi(time2[17:]), 0, 0, -1)
	return (time.mktime(t2) - time.mktime(t1))

class XferGnuFile(enstore_files.EnFile):

    def write(self, outfile1, outfile2, ptsfile1, ptsfile2):
	self.openfile.write("set output '"+outfile2+"'\n"+ \
	                   "set terminal postscript color\n"+ \
	                   "set title 'Individual Transfer Activity "+plot_time()+"'\n"+ \
	                   "set xlabel 'Date'\n"+ \
	                   "set timefmt \"%Y-%m-%d:%H:%M:%S\"\n"+ \
	                   "set xdata time\n"+ \
	                   "set xrange [ : ]\n"+ \
	                   "set ylabel 'Bytes per Transfer'\n"+ \
	                   "set grid\n"+ \
	                   "set format x \"%y-%m-%d\"\n"+ \
	                   "set logscale y\n"+ \
	                   "plot '"+ptsfile1+\
	                   "' using 1:4 t 'reads' with points 3 1, "+ 
			   "'"+ptsfile1+\
			   "' using 1:3 t 'writes' with points 1 1\n"+ 
	                   "set output '"+outfile1+"'\n"+ \
	                   "set pointsize 2\n"+ \
	                   "set nologscale y\n"+ \
	                   "set yrange [0: ]\n"+ \
			   "plot '"+ptsfile1+"' using 1:2 t '' w impulses, "+\
			   "'"+ptsfile2+\
	                   "' using 1:7 t 'mean file size' w points 3 5\n")

class XferDataFile(EnPlot):

    def __init__(self, dir, bpdfile):
	self.bpdfile = bpdfile
	EnPlot.__init__(self, dir, enstore_constants.XFER_FILE)
	self.logfile = enstore_constants.XFERLOG_FILE+enstore_constants.PS

    # make the file with the plot points in them
    def plot(self, data):
	# write out the data points
	for [xpt, ypt, type] in data:
	    if type == WRITE:
		# this was a write request
		self.openfile.write("%s %s %s\n"%(xpt, ypt, ypt))
	    else:
		# this was a read request
		self.openfile.write("%s %s 0 %s\n"%(xpt, ypt, ypt))

	# we must create our gnu plot command file too
	gnucmds = XferGnuFile(self.gnufile)
	gnucmds.open('w')
	gnucmds.write(self.psfile, self.logfile, self.ptsfile, self.bpdfile)
	gnucmds.close()

    def install(self, dir):
        EnPlot.install(self, dir)
	os.system("cp %s %s"%(self.logfile, dir))
	convert_to_jpg(self.logfile, "%s/%s%s"%(dir, self.name, 
						enstore_constants.LOG))
	

class BpdGnuFile(enstore_files.EnFile):

    def write(self, outfile, ptsfile, total, meansize, xfers, read_xfers, write_xfers):
	psfiler = string.replace(outfile, enstore_constants.BPD_FILE,
				 enstore_constants.BPD_FILE_R)
	psfilew = string.replace(outfile, enstore_constants.BPD_FILE,
				 enstore_constants.BPD_FILE_W)
	self.openfile.write("set output '"+outfile+"'\n"+ \
	                   "set terminal postscript color\n"+ \
	                   "set title 'Total Bytes Transferred Per Day "+plot_time()+"'\n"+ \
	                   "set xlabel 'Date'\n"+ \
	                   "set timefmt \"%Y-%m-%d\"\n"+ \
	                   "set xdata time\n"+ \
	                   "set xrange [ : ]\n"+ \
	                   "set ylabel 'Bytes'\n"+ \
	                   "set grid\n"+ \
	                   "set yrange [0: ]\n"+ \
	                   "set format x \"%m-%d\"\n"+ \
			   "set key right top Right samplen 1 title \"Total Bytes : "+\
			      "%.2e"%(total,)+"\\nMean Xfer Size : "+
			      "%.2e"%(meansize,)+"\\n Number of Xfers : "+
			      repr(xfers)+"\"\n"+\
	                   "plot '"+ptsfile+"' using 1:2 t 'reads' w impulses lw 20 3 1, '"+ptsfile+\
			          "' using 1:4 t 'writes' w impulses lw 20 1 1\n"+
			    "set output '"+psfiler+"'\n"+ \
			    "set title 'Total Bytes Read Per Day "+plot_time()+"'\n"+ \
			    "set pointsize 2\n"+ \
			    "set key right top Right samplen 1 title \"Total Bytes : "+\
			      "%.2e"%(total,)+"\\n Number of Xfers : "+\
			      repr(read_xfers)+"\"\n"+\
			    "plot '"+ptsfile+"' using 1:2 t 'total' w points 4 7, '"+ptsfile+\
			          "' using 1:3 t 'reads' w impulses lw 20 1 1\n"+
			    "set output '"+psfilew+"'\n"+ \
			    "set title 'Total Bytes Written Per Day "+plot_time()+"'\n"+ \
			    "set key right top Right samplen 1 title \"Total Bytes : "+\
			       "%.2e"%(total,)+"\\n Number of Xfers : "+\
			       repr(write_xfers)+"\"\n"+\
			    "plot '"+ptsfile+"' using 1:2 t 'total' w points 4 7, '"+ptsfile+\
			          "' using 1:4 t 'writes' w impulses lw 20 1 1\n"
			    )

class BpdDataFile(EnPlot):

    def __init__(self, dir):
	EnPlot.__init__(self, dir, enstore_constants.BPD_FILE)

    # init the following hash from the first date given to the last date
    def init_date_hash(self, sdate, edate):
	ndate = {}
	ndate[sdate[0:10]] = 0.0
	ndate[edate[0:10]] = 0.0
	imon = string.atoi(sdate[5:7])
	iday = string.atoi(sdate[8:10])
	iyr = string.atoi(sdate[0:4])
	is_leap = calendar.isleap(iyr)
	emon = string.atoi(edate[5:7])
	eday = string.atoi(edate[8:10])
	while 1:
	    if (imon == emon) and (iday == eday):
	        break
	    iday = iday + 1
	    if imon == 2:
		mday = calendar.mdays[imon] + is_leap 
	    else:
		mday = calendar.mdays[imon]
	    if iday <= mday:
	        tmp = "%i-%02i-%02i" % (iyr, imon, iday)
	        ndate[tmp] = 0.0
	        continue
	    else:
	        imon = imon + 1
	        iday = 0
	        if imon > 12:
	            imon = 1
	            iyr = iyr + 1
		    is_leap = calendar.isleap(iyr)
	return ndate

    # make the file with the bytes per day format, first we must sum the data
    # that we have based on the day
    def plot(self, data):
	# initialize the new data hash
	ndata = self.init_date_hash(data[0][0], data[len(data)-1][0])
	reads = self.init_date_hash(data[0][0], data[len(data)-1][0])
	writes = self.init_date_hash(data[0][0], data[len(data)-1][0])
	# sum the data together based on day boundaries. also save the largest
	# smallest and average sizes and sum up reads and writes separately
	mean = {}
	smallest = {}
	largest = {}
	ctr = {}
	read_ctr = 0
	write_ctr = 0
	for [xpt, ypt, type] in data:
	    adate = xpt[0:10]
	    fypt = string.atof(ypt)
	    if mean.has_key(adate):
	        mean[adate] = mean[adate] + fypt
	        ctr[adate] = ctr[adate] + 1
	    else:
	        mean[adate] = fypt
	        ctr[adate] = 1
	    if largest.has_key(adate):
	        if fypt > largest[adate]:
	            largest[adate] = fypt
	    else:
	        largest[adate] = fypt
	    if smallest.has_key(adate):
	        if fypt < smallest[adate]:
	            smallest[adate] = fypt
	    else:
	        smallest[adate] = fypt
	    ndata[adate] = ndata[adate] + fypt
	    if type == WRITE:
		dict = writes
		write_ctr = write_ctr + 1
	    else:
		dict = reads
		read_ctr = read_ctr + 1
	    dict[adate] = dict[adate] + fypt
	# write out the data points
	keys = ndata.keys()
	keys.sort()
	numxfers = 0
	total = 0
	for key in keys:
	    if not ndata[key] == 0:
	        self.openfile.write(key+" "+repr(ndata[key])+" "+\
				    repr(reads[key])+" "+\
				    repr(writes[key])+" "+\
				    repr(smallest[key])+" "+\
				    repr(largest[key])+" "+\
				    repr(mean[key]/ctr[key])+"\n")
	    else:
		# all data is 0
	        #self.openfile.write(key+" "+repr(ndata[key])+" "+\
		#		            repr(ndata[key])+" "+\
		#		            repr(ndata[key])+"\n")
	        self.openfile.write(key+"\n")
	    # now find the total bytes transferred over all days and the mean
	    # size of all transfers.
	    total = total + ndata[key]
	    # there may not be any transfers on a certain date, so check the key
	    # first.  above ndata has all dates initialized to 0 so no check is
	    # necessary.
	    numxfers = numxfers + ctr.get(key, 0)
	    
	# we must create our gnu plot command file too
	gnucmds = BpdGnuFile(self.gnufile)
	gnucmds.open('w')
	gnucmds.write(self.psfile, self.ptsfile, total, total/numxfers, numxfers,
		      read_ctr, write_ctr)
	gnucmds.close()

    def install(self, dir):
	EnPlot.install(self, dir)
	filer = string.replace(self.name, enstore_constants.BPD_FILE,
			       enstore_constants.BPD_FILE_R)
	psfiler = "%s/%s%s"%(self.dir, filer, enstore_constants.PS)
	filew = string.replace(self.name, enstore_constants.BPD_FILE,
			       enstore_constants.BPD_FILE_W)
	psfilew = "%s/%s%s"%(self.dir, filew, enstore_constants.PS)
	os.system("cp %s %s %s"%(psfiler, psfilew, dir))
	convert_to_jpg(psfiler, "%s/%s"%(dir, filer))
	convert_to_jpg(psfilew, "%s/%s"%(dir, filew))
