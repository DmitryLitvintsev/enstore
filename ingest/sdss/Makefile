SHELL=/bin/sh

# need a robust way of finding freeze, especially for non-kits version of python
FREEZE=`find $(PYTHON_DIR) -name freeze.py -print` 
#FREEZE=`ls $(PYTHON_DIR)/Python-*/Tools/freeze/freeze.py`
#PYMODULES=`find $(PYTHON_DIR) -name Modules -print`
PYMODULES=$(PYTHON_DIR)/Python-*/Modules

# No static version for SunOS for now
# No static version for any one any more ... since v3_0
# LDFLAGS2=`if [ "_SunOS" = _$(MACH_OS) ]; then echo "-dy"; else echo "-static"; fi`
LDFLAGS2=

OSV=`uname -s r`

# just for testing
setenvs:
	echo "uname =" `uname`
	echo "LDFLAGS2 =" $(LDFLAGS2)

all:
	@echo nothing to build

clean:
	@ $(ENSTORE_DIR)/bin/enstoreClean
	rm -f *.pyc
	- rm -rf SDSSCP_BIN
	- rm -rf SDSSCP_TEMP

check:
	$(ENSTORE_DIR)/tools/mylint.py ./*.py
	$(ENSTORE_DIR)/tools/check_pct.py -w ./*.py

sdsscp:
	(cd $(ENSTORE_DIR)/src; make get)

	- rm -rf SDSSCP_TEMP
	mkdir SDSSCP_TEMP
	- rm -rf SDSSCP_BIN
	mkdir SDSSCP_BIN

	python $(FREEZE) -e $(ENSTORE_DIR)/modules -e $(PYMODULES) -o SDSSCP_TEMP sdsscp.py
	(cd SDSSCP_TEMP; LDFLAGS=$(LDFLAGS2); export LDFLAGS; make -e;)

	cp SDSSCP_TEMP/sdsscp SDSSCP_BIN
	cp $(ENSTORE_DIR)/src/GET_BIN/get SDSSCP_BIN
	cp $(ENSTORE_DIR)/src/GET_BIN/enroute2 SDSSCP_BIN
	cp $(ENSTORE_DIR)/ups/chooseConfig SDSSCP_BIN
	sed -e 's/encp/sdsscp/g' -e 's/ENCP/SDSSCP/' $(ENSTORE_DIR)/ups/encp.table > SDSSCP_BIN/sdsscp.table
	- rm -rf SDSSCP_TEMP

# This install never works!
install: encp enstore_user
	cp encp $ENSTORE_DIR/bin
	cp enstore_user $ENSTORE_DIR/bin

