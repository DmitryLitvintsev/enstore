#
# restore.py
#

import db
import os
import sys
import string

# similar to db.DbTable, without automatic journaling and backup up.

class DbTable(db.DbTable):

	# __init__() is almost the same as db.DbTable.__init__()
	# plus a "deletes" list containing the deleted keys

	def __init__(self, dbname, dbHome, jouHome, indlst=[]):
		db.DbTable.__init__(self, dbname, dbHome, jouHome, indlst, 0)

		# Now let's deal with all the journal files

		jfile = self.jouHome+"/"+dbname+".jou"
		cmd = "ls -1 "+jfile+".* 2>/dev/null"
		jfiles = os.popen(cmd).readlines()
		jfiles.append(jfile+"\012")	# to be same as the rest
		self.dict = {}
		for jf in jfiles:
			jf = jf[:-1]		# trim \012
			try:
				f = open(jf,"r")
			except IOError:
				print(jf+": not found")
				sys.exit(0)
			while 1:
				l = f.readline()
				if len(l) == 0: break
				exec(l)
			f.close()

		# read it twice to get the deletion list

		self.deletes = []
		for jf in jfiles:
			jf = jf[:-1]
			try:
				f = open(jf,"r")
			except IOError:
				print(jf+": not found")
				sys.exit(0)
			while 1:
				l = f.readline()
				if len(l) == 0: break
				if l[0:3] == 'del':
					k = string.split(l, "'")[1]
					if not self.dict.has_key(k):
						self.deletes.append(k)
			f.close()
			
	# cross_check() cross check journal dictionary and database

	def cross_check(self):

		error = 0

		# check if the items in db has the same value of that
		# in journal dictionary

		for i in self.dict.keys():
			if not self.has_key(i):
				print 'M> key('+i+') is not in database'
				error = error + 1
			elif `self.dict[i]` != `self.__getitem__(i)`:
				print 'C> database and journal disagree on key('+i+')'
				print 'C>  journal['+i+'] =', self.dict[i]
				print 'C> database['+i+'] =', self.__getitem__(i)
				error = error + 1
		# check if the deleted items are still in db

		for i in self.deletes:
			if self.has_key(i):
				print 'D> database['+i+'] should be deleted'
				error = error + 1

		return error

	# fix_db() fix db according to journal dictionary

	def fix_db(self):

		error = 0

		# check if the items in db has the same value of that
		# in journal dictionary

		for i in self.dict.keys():
			if not self.has_key(i):
				# add it
				print 'M> key('+i+') is not in database'
				self.__setitem__(i, self.dict[i])
				error = error + 1
				print 'F> database['+i+'] =', self.dict[i]
			elif `self.dict[i]` != `self.__getitem__(i)`:
				print 'C> database and journal disagree on key('+i+')'
				print 'C>  journal['+i+'] =', self.dict[i]
				print 'C> database['+i+'] =', self.__getitem__(i)
				self.__setitem__(i, self.dict[i])
				print 'F> database['+i+'] =', self.dict[i]
				error = error + 1
		# check if the deleted items are still in db

		for i in self.deletes:
			if self.has_key(i):
				print 'D> database['+i+'] should be deleted'
				self.__delitem__(i)
				print 'F> delete database['+i+']'
				error = error + 1

		return error

import interface

class Interface(interface.Interface):

	def __init__(self):
		interface.Interface.__init__(self)

	def options(self):
		return self.config_options()

if __name__ == "__main__":		# main

	import configuration_client
	import hostaddr

	intf = Interface()

	# find dbHome and jouHome
	try:
		dbInfo = configuration_client.ConfigurationClient(
			(intf.config_host, intf.config_port)).get(
			'database')
        	dbHome = dbInfo['db_dir']
        	try:  # backward compatible
			jouHome = dbInfo['jou_dir']
		except:
			jouHome = dbHome
	except:
		dbHome = os.environ['ENSTORE_DIR']
		jouHome = dbHome

	# find backup host and path
	backup_config = configuration_client.ConfigurationClient(
		(intf.config_host,
		intf.config_port)).get('backup')

	local_host = hostaddr.gethostinfo()[0]
	try:
		bckHost = backup_config['host']
	except:
		bckHost = local_host

	bckHome = backup_config['dir']

	print " dbHome = "+dbHome
	print "jouHome = "+jouHome
	print "bckHost = "+bckHost
	print "bckHome = "+bckHome

	# find the last backup
	# so far, we only deal with the last backup
	# In theory, if it is not good, we should go all the way back
	# to the "last good backup"

	cmd = "rsh "+bckHost+" ls -1t "+bckHome+" | head -1"
	bckHome = bckHome+"/"+os.popen(cmd).readline()[:-1]

	print "restore from "+bckHost+":"+bckHome

	# databases
	dbs = ['file', 'volume']

	# go to dbHome
	os.chdir(dbHome)
	print "cd "+dbHome

	# save the current (bad?) database
	print "Save current (bad?) database files ..."
	for i in dbs:
		cmd = "mv "+i+" "+i+".saved"
		try:	# if it doesn't succeed, never mind
			os.system(cmd)
			print cmd
		except:
			pass

	# save all log.* files
	print "Save current (bad?) log files"
	cmd = "ls -1 log.*"
	logs = os.popen(cmd).readlines()
	for i in logs:
		i = i[:-1]	# trim \012
		cmd = "mv "+i+" "+i+".saved"
		try:	# if it doesn't succeed, never mind
			os.system(cmd)
			print cmd
		except:
			pass

	# check the type of compression

	compression = os.popen("rsh -n "+bckHost+" ls "+bckHome+"/dbase.tar*").readline()[-2:-1]
	if compression == "z" or compression == "Z":	# decompress them first
		cmd = "rsh -n "+bckHost+" gunzip "+bckHome+"/*"
		print "decompressing the backup files ..."
		print cmd
		os.system(cmd)

	# get the database file from backup

	print "Retriving database file from backup ("+bckHost+":"+bckHome+")"

	cmd = "rsh -n "+bckHost+" dd if="+bckHome+"/dbase.tar bs=20b | tar xvBfb - 20"
	print cmd
	os.system(cmd)

	# run db_recover to put the databases in consistent state

	print "Synchronize database using db_recover"
	os.system("db_recover")

	# get the journal files in place
	# basically, we only need current journal file to restore the
	# databases from the previous backup. Just to be paranoid,
	# we still get some previous journal files ...

	os.chdir(jouHome)
	print "cd "+jouHome

	print "Retriving journal files from backup ("+bckHost+":"+bckHome+")"
	for i in dbs:
		cmd = "rsh -n "+bckHost+" dd if="+bckHome+"/"+i+\
			".tar bs=20b | tar xvBfb - 20 '"+i+".jou*'"
		os.system(cmd)
		print cmd

	print "Restoring databse ..."
	for i in dbs:
		print "dbHome", dbHome
		print "jouHome", jouHome
		d = DbTable(i, dbHome, jouHome, [])
		print "Checking "+i+" ... "
		err = d.cross_check()
		if err:
			print "Fixing "+i+" ... "
			d.fix_db()
		else:
			print i+" is OK"
