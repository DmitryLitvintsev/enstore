#!/bin/bash
#############################################################
#
#  $Id$
#
#############################################################
pnfs_path=""
user=""
data=""
if [ "${1:-}" = "-x" ] ; then set -xv; shift; fi
if [ "${1:-}" = "-p" ] ; then shift; pnfs_path=$1; shift; fi
if [ "${1:-}" = "-u" ] ; then shift; user=$1; shift; else user=`whoami`;fi
if [ "${1:-}" = "-d" ] ; then shift; data=$1; shift; fi
if [ "${1:-}" = "-c" ] ; then shift; node_list=$1; shfit;else node_list=/tmp/`whoami`/node_list;fi
if [ -z $data ]; then data="/scratch_dcache/cdfcaf";fi

if [ ! -f $node_list ]; then echo "no node_list"; exit 1;fi
cat $node_list | while read node;do echo $node;
    scp ~/.bashrc  ${user}@${node}:~/
    echo AAAA
    scp read.sh ${user}@${node}:~/bin
    echo BBB
    ssh ${user}@${node} "cd $data; rm -f read_$$.out; read.sh $pnfs_path > read_$$.out 2>&1&"
    echo CCC
done

