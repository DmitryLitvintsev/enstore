#!/usr/bin/env python

import os
import sys
import string
import stat
import time
import shutil
import traceback
import socket

import e_errors
import timeofday
import hostaddr
import configuration_client
import verify_db

# path to database
db_path = "/diskc/check_database"

def print_usage():
    print "Usage:", sys.argv[0], "[--help]"
    print "  --help   print this help message"
    print "See configuration dictionary entry \"backup\" for defaults."

# check the status of a return ticket
def check_ticket(server, ticket,exit_if_bad=1):
	if not 'status' in ticket.keys():
		print timeofday.tod(),server,' NOT RESPONDING'
		if exit_if_bad:
			sys.exit(1)
		else:
			return 1
	if ticket['status'][0] == e_errors.OK:
		print timeofday.tod(), server, ' ok'
		return 0
	else:
		print timeofday.tod(), server, ' BAD STATUS',ticket['status']
		if exit_if_bad:
			sys.exit(1)
		else:
			return 1

# check if a directory or a file exists
def check_existance(the_file, plain_file):
	try:
		the_stat = os.stat(the_file)
	except:
		traceback.print_exc()
		print timeofday.tod(),'ERROR',the_file,'not found'
		sys.exit(1)
	if not plain_file:
		if not stat.S_ISDIR(the_stat[stat.ST_MODE]):
			print timeofday.tod(),'ERROR',the_file,'is not a directory'
			sys.exit(1)
	else:
		if not stat.S_ISREG(the_stat[stat.ST_MODE]):
			print timeofday.tod(),'ERROR',the_file,'is not a regular file'
			sys.exit(1)
	return the_stat

# get the configuration
def configure(configuration = None):
	csc = configuration_client.ConfigurationClient()
	backup = csc.get('backup',timeout=15,retry=3)
	check_ticket('Configuration Server',backup)
	inventory = csc.get('inventory',timeout=15,retry=3)
	check_ticket('Configuration Server',inventory)

	#Check both the FQDN and the ip.  On multihomed hosts only checking on
	# my lead to failed operations that would otherwise succed.
	backup_node = backup.get('hostip', 'MISSING')
	thisnode = hostaddr.gethostinfo(1)
	mynode = thisnode[2][0]
	backup_fqdn = socket.gethostbyaddr(backup_node)[0]
	mynode_fqdn = socket.gethostbyaddr(mynode)[0]
	if mynode != backup_node and backup_fqdn != mynode_fqdn:
		print timeofday.tod(),"ERROR Backups are stored", backup_node,
		print ' you are on',mynode,' - database check is not possible'
		sys.exit(1)
        
	backup_dir = backup.get('dir')
	if not backup_dir:
		print timeofday.tod(), "ERROR Backup directory is not determined"
		sys.exit(1)
	if configuration:
		check_existance(backup_dir,0)

	check_dir = backup.get('extract_dir')
	if not check_dir:
		print timeofday.tod(), "ERROR Extraction directory is not determined"
		sys.exit(1)

	dest_path = inventory.get('inventory_rcp_dir')
	if not dest_path:
		print timeofday.tod(), "ERROR rcp directory is not determined"

	# always check the existance
	check_existance(check_dir,0)
    
	current_dir = os.getcwd() #Remember the original directory

	print timeofday.tod(), 'Checking Enstore on', csc.get_address()[0], \
          'with timeout of', csc.get_timeout(), 'and retries of', \
          csc.get_retry()

	#Return the directory the backup file is in and the directory the backup
	# file will be ungzipped and untared to, respectively.  Lastly, return
	# the current directory.
	return backup_dir, check_dir, current_dir, backup_node, dest_path

# get the most recent backup file
def check_backup(backup_dir, backup_node):
	# backups are saved in separate files - get the most recent one
	bdirs = os.listdir(backup_dir)
	if len(bdirs) == 0:
		print timeofday.tod(),"ERROR NO Backups found on ", backup_node,
		print " directory", backup_dir, " Are the backups running?"
		sys.exit(1)
	bdirs.sort()
	current_backup_dir = bdirs[-1:][0]

	container = os.path.join(backup_dir, current_backup_dir, 'enstoredb.dmp')

	print "container:", container
	con_stat=check_existance(container,1)
	mod_time=con_stat[stat.ST_MTIME]
	for i in range(100):
		if time.time() - os.stat(container)[stat.ST_MTIME] < 60:
			print timeofday.tod(),"Too new - wait for a 15 seconds"
			time.sleep(15)
		else:
			break
	if time.time() - os.stat(container)[stat.ST_MTIME] < 60:
		print timeofday.tod(), "ERROR: Backup is too new. Give up after retries."
		print "Backup container",container,'last modified on', time.ctime(os.stat(container)[stat.ST_MTIME])
		sys.exit(1)
	else:
		print timeofday.tod(), "Checking container", container,
		print "last modified on", time.ctime(os.stat(container)[stat.ST_MTIME])

	return container

# start postmaster
def start_postmaster():
	pid = os.popen("ps -axw| grep postmaster | grep %s | awk '{print $1}'"%(db_path)).readline()
	pid = string.strip(pid)
	if pid:
		print timeofday.tod(), "postmaster has already been started"
	else:
		print timeofday.tod(), "Starting postmaster ..."
		# take care of left over pid info, if any
		pid_file = os.path.join(db_path, "postmaster.pid")
		if os.access(pid_file, os.F_OK):
			os.unlink(pid_file)

		# starting postmaster
		cmd = "postmaster -D %s &"%(db_path)
		os.system(cmd)
		time.sleep(15)

#stop postmaster
def stop_postmaster():
	pid = os.popen("ps -axw| grep postmaster | grep %s | awk '{print $1}'"%(db_path)).readline()
	pid = string.strip(pid)
	if pid:
		print timeofday.tod(), "Stopping postmaster"
		os.kill(int(pid))
	else:
		print timeofday.tod(), "postmaster is not running"
    
def extract_backup(check_dir, container):
	print timeofday.tod(), "Extracting database files from backup container",
	print container
    
	os.chdir(check_dir)
	os.system("dropdb backup")
	os.system("createdb backup")
	os.system("pg_restore -d backup -v "+container)

# the way to check it is to run file listing on all
def check_db(check_dir):
	out_file = os.path.join(check_dir, "COMPLETE_FILE_LISTING")
	print timeofday.tod(), "Listing all files ..."
	cmd = "psql -d backup -c "+'"'+"select bfid, label as volume, file_family, size, crc, location_cookie, pnfs_path as path from file, volume where file.volume = volume.id and not volume.label like '%.deleted' and deleted = 'n';"+'"'+" | sed -e 's/|/ /g' > "+out_file

	print cmd
	os.system(cmd)

if __name__ == "__main__":
	if "--help" in sys.argv:
		print_usage()
		sys.exit(0)
    
	(backup_dir, check_dir, current_dir, backup_node, dest_path) = configure(1) #non-None argument!
	#starting postmaster
	start_postmaster()
	extract_backup(check_dir, check_backup(backup_dir, backup_node))
	check_db(check_dir)
	stop_postmaster()
	# moving COMPLETE_FILE_LISTING to dest_path
	cmd = "enrcp %s %s"%(os.path.join(check_dir, "COMPLETE_FILE_LISTING"), dest_path)
	print timeofday.tod(), cmd
	os.system(cmd)
