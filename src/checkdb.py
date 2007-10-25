#!/usr/bin/env python

import os
import sys
import string
import stat
import time
import traceback
import socket
import signal

import e_errors
import timeofday
import hostaddr
import configuration_client

import pg

EXCLUDED_STORAGE_GROUP = ['backups', 'CLEAN', 'null', 'test', 'none']

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

	db_path = backup.get('check_db_area')
	if not db_path:
		# to be backward compatible
		db_path = '/diskc/check-database'

	current_dir = os.getcwd() #Remember the original directory

	print timeofday.tod(), 'Checking Enstore on', csc.get_address()[0], \
          'with timeout of', csc.get_timeout(), 'and retries of', \
          csc.get_retry()

	#Return the directory the backup file is in and the directory the backup
	# file will be ungzipped and untared to, respectively.  Lastly, return
	# the current directory.
	return backup_dir, check_dir, current_dir, backup_node, dest_path, db_path

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
def start_postmaster(db_path):
	cmd = "ps -axw| grep postmaster | grep %s | grep -v grep | awk '{print $1}'"%(db_path)
	pid = os.popen(cmd).readline()
	pid = string.strip(pid)
	if pid:
		print timeofday.tod(), "postmaster has already been started -- pid =", pid
	else:
		print timeofday.tod(), "Starting postmaster ..."
		# take care of left over pid info, if any
		pid_file = os.path.join(db_path, "postmaster.pid")
		if os.access(pid_file, os.F_OK):
			os.unlink(pid_file)

		# starting postmaster
		cmd = "postmaster -h '' -D %s &"%(db_path)
		os.system(cmd)
		time.sleep(15)

#stop postmaster
def stop_postmaster(db_path):
	pid = os.popen("ps -axw| grep postmaster | grep %s | grep -v grep | awk '{print $1}'"%(db_path)).readline()
	pid = string.strip(pid)
	if pid:
		print timeofday.tod(), "Stopping postmaster"
		os.kill(int(pid), signal.SIGTERM)
	else:
		print timeofday.tod(), "postmaster is not running"
    
def extract_backup(check_dir, container):
	print timeofday.tod(), "Extracting database files from backup container",
	print container
    
	os.chdir(check_dir)
	os.system("dropdb backup")
	os.system("createdb backup")
	# os.system("pg_restore -d backup -v "+container)
	os.system("psql backup -c 'create sequence volume_seq;'")
	os.system("psql backup -c 'create sequence state_type_seq;'")
	os.system("pg_restore -d backup -v -s -t bad_file "+container)
	os.system("pg_restore -d backup -v -s -t file "+container)
	os.system("pg_restore -d backup -v -s -t media_capacity "+container)
	os.system("pg_restore -d backup -v -s -t migration "+container)
	os.system("pg_restore -d backup -v -s -t migration_history "+container)
	os.system("pg_restore -d backup -v -s -t no_flipping_storage_group "+container)
	os.system("pg_restore -d backup -v -s -t option "+container)
	os.system("pg_restore -d backup -v -s -t qa "+container)
	os.system("pg_restore -d backup -v -s -t quota "+container)
	os.system("pg_restore -d backup -v -s -t sg_count "+container)
	os.system("pg_restore -d backup -v -s -t state "+container)
	os.system("pg_restore -d backup -v -s -t state_type "+container)
	os.system("pg_restore -d backup -v -s -t tc "+container)
	os.system("pg_restore -d backup -v -s -t volume "+container)
	os.system("pg_restore -d backup -v -s -t no_flipping_file_family "+container)
	os.system("pg_restore -d backup -v -s -t file_copies_map "+container)
	os.system("pg_restore -d backup -v -a "+container)
        os.system("psql backup -c 'alter table only volume add constraint volume_pkey primary key (id);'")
	os.system("psql backup -c 'create index volume_storage_group_idx on volume(storage_group);'")
	os.system("psql backup -c 'create index volume_system_inhibit_0_idx on volume(system_inhibit_0);'")

LISTING_FILE = "COMPLETE_FILE_LISTING"

# the way to check it is to run file listing on all
def check_db(check_dir):
	out_file = os.path.join(check_dir, LISTING_FILE)
	f = open(out_file, 'w')
	time_stamp = time.ctime(time.time())
	f.write("Listed at %s\n\n"%(time_stamp))
	f.close()

	print timeofday.tod(), "Listing all files ... (old style)"
	cmd = "psql -d backup -A -F ' ' -c "+'"'+"select bfid, label as volume, file_family, size, crc, location_cookie, pnfs_path as path from file, volume where file.volume = volume.id and volume.system_inhibit_0 != 'DELETED' and deleted = 'n';"+'"'+" >> "+out_file
	print cmd
	os.system(cmd)

	db = pg.DB(dbname='backup')
	# get all storage groups
        q = "select distinct storage_group from volume where not storage_group like '%CLN%';"
	res = db.query(q).getresult()
	del db
	for i in res:
		sg = i[0]
		if sg in EXCLUDED_STORAGE_GROUP:
			continue
		out_file = LISTING_FILE+'_'+sg
		f = open(out_file, 'w')
		f.write("-- Listed at %s\n--\n"%(time_stamp))
		f.write("-- STORAGE GROUP: %s\n--\n"%(sg))
		f.close()
		print timeofday.tod(), "Listing %s files ... "%(sg)
	
		cmd = "psql -d backup -A -F ' ' -c "+'"'+"select storage_group, file_family, label as volume, location_cookie, bfid, size, crc, pnfs_path as path from file, volume where storage_group = '%s' and file.volume = volume.id and volume.system_inhibit_0 != 'DELETED' and deleted = 'n' order by storage_group, file_family, label, location_cookie;"%(sg)+'"'+" >> "+out_file
		print cmd
		os.system(cmd)

	# generate pnfs dictionary
	print timeofday.tod(), "Generating PNFS.XREF ..."
	pnfs_dict_file = os.path.join(check_dir, 'PNFS.XREF')
	cmd = "psql -d backup -A -F ' ' -c "+'"'+"select pnfs_id, bfid, size, pnfs_path from file where deleted = 'n' and not pnfs_path is null"+'"'+" -o %s"%(pnfs_dict_file)

	print cmd
	os.system(cmd)

if __name__ == "__main__":
	if "--help" in sys.argv:
		print_usage()
		sys.exit(0)
    
	(backup_dir, check_dir, current_dir, backup_node, dest_path, db_path) = configure(1) #non-None argument!
	# checking for the directories
	if not os.access(check_dir, os.F_OK):
		os.makedirs(check_dir)
	check_existance(check_dir, 0)
	if not os.access(db_path, os.F_OK):
		os.makedirs(db_path)
		# create database area
		cmd = "initdb -D %s"%(db_path)
		os.system(cmd)
	#starting postmaster
	start_postmaster(db_path)
	extract_backup(check_dir, check_backup(backup_dir, backup_node))
	check_db(check_dir)
	stop_postmaster(db_path)
	# moving COMPLETE_FILE_LISTING to dest_path
	cmd = "enrcp %s %s"%(os.path.join(check_dir, "COMPLETE_FILE_LISTING*"), dest_path)
	print timeofday.tod(), cmd
	os.system(cmd)
	cmd = "enrcp %s %s"%(os.path.join(check_dir, "PNFS.XREF"), dest_path)
	print timeofday.tod(), cmd
	os.system(cmd)
