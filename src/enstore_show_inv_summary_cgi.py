#!/usr/bin/env python

import os
import sys
import string
import socket

inv_dir = "/enstore/tape_inventory"

host = string.split(socket.gethostname(), '.')[0]
if host[:3] == "rip":
	cluster = "rip"
elif host[:3] == "stk":
	cluster = "stken"
elif host[:3] == "d0e":
	cluster = "d0en"
elif host[:3] == "cdf":
	cluster = "cdfen"
else:
	cluster = host

special = ['TOTAL_BYTES_ON_TAPE', 'VOLUMES', 'VOLUMES_DEFINED.html', 'VOLUMES_TOO_MANY_MOUNTS', 'VOLUME_QUOTAS', 'VOLUME_SIZE', 'LAST_ACCESS', 'NOACCESS', 'CLEANING', 'VOLUME_CROSS_CHECK', 'COMPLETE_FILE_LISTING', 'DECLARATION_ERROR', 'MIGRATED_VOLUMES', 'RECYCLABLE_VOLUMES', 'WRITE_PROTECTION_ALERT', 'WEEKLY_SUMMARY', 'TAB_FLIPPING_WATCH']

if cluster == "d0en":
	special.append('TAB_FLIPPING_WATCH-samlto2')
	special.append('AML2-VOLUMES.html')
	special.append('STK-VOLUMES.html')
	special.append('MIGRATION_SUMMARY')
elif cluster == "stken":
	special.append('TAB_FLIPPING_WATCH-CD-LTO3')
	special.append('SL8500-VOLUMES.html')
	special.append('AML2-VOLUMES.html')
	special.append('STK-VOLUMES.html')
	special.append('MIGRATION_STATUS')
	special.append('QUOTA_ALERT')
	special.append('VOLUME_QUOTAS_UPDATE')
	special.append('CMS_VOLUMES_WITH_ONLY_DELETED_FILES')
elif cluster == "cdfen":
	special.append('TAB_FLIPPING_WATCH-CDF-LTO3')
	special.append('SL8500-VOLUMES.html')
	special.append('STK-VOLUMES.html')

# in the beginning ...

print "Content-type: text/html"
print

# taking care of the header

print '<html>'
print '<head>'
print '<title>Tape Inventory Summary on '+cluster+'</title>'
print '</head>'
print '<body bgcolor="#ffffd0">'
print '<font size=7 color="#ff0000">Enstore Tape Inventory Summary on '+cluster+'</font>'
print '<hr>'

# handle special files

print '<p><font size=4>'
for i in special:
	if i == 'COMPLETE_FILE_LISTING':
		print '<a href="enstore_file_listing_cgi.py">', string.split(i, '.')[0], '</a>&nbsp;&nbsp;'
	else:
		print '<a href="'+os.path.join(inv_dir, i)+'">', string.split(i, '.')[0], '</a>&nbsp;&nbsp;'
	print '<br>'
print '<p><a href="'+inv_dir+'">Raw Directory Listing</a>'
print '<p></font>'
print '</body>'
print '</html>'
