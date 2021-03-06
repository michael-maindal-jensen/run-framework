#!/bin/bash


default="$(dirname $0)/../variables.sh"
variables_file=${VARIABLES_FILE:-$default}
echo "Using variables file = $variables_file" 
source $variables_file

if [ "$1" == "-h" -o "$1" == "--help" -o "$1" == "" ]; then
  echo "Usage: `basename $0` HOST KEY_FILE (default = ~/.ssh/ecs-key.pem)"
  exit 0
fi

prefix=$1
host=$2
keyfile=${3:-$HOME/.ssh/ecs-key.pem}
user=${4:-ec2-user}
remote_variables_file=${5:-/home/ec2-user/agief-project/variables/variables-ec2.sh}
port=${6:-22}
no_compress=${7:-False}
csv_output=${8:-False}

echo "Using prefix = " $prefix
echo "Using host = " $host
echo "Using keyfile = " $keyfile
echo "Using user = " $user
echo "Using remote_variables_file = " $remote_variables_file
echo "Using port =  " $port

ssh -v -p $port -i $keyfile ${user}@${host} -o 'StrictHostKeyChecking no' prefix=$prefix VARIABLES_FILE=$remote_variables_file no_compress=$no_compress csv_output=$csv_output 'bash --login -s' <<'ENDSSH'
	export VARIABLES_FILE=$VARIABLES_FILE
	source $VARIABLES_FILE

	upload_folder=$AGI_RUN_HOME/output/$prefix
	echo "Calculated upload-folder = " $upload_folder

	csv_files=""
	if [ "$csv_output" = "True" ]; then
		csv_files="$upload_folder/*.csv"
	fi

	if [ "$no_compress" = "False" ]; then
		output_big_folder=$AGI_RUN_HOME/output-big/
		mkdir -p $output_big_folder

		matching_files=( $(find $upload_folder -name '*data*.json') )
		zip -j $upload_folder/data.zip ${matching_files[0]} $csv_files
		mv -t $output_big_folder ${matching_files[0]} $csv_files
	fi

	cmd="aws s3 cp $upload_folder s3://agief-project/experiment-output/$prefix/output --recursive"
	echo $cmd >> remote-upload-cmd.log
	eval $cmd >> remote-upload-stdout.log 2>> remote-upload-stderr.log
ENDSSH

status=$?

if [ $status -ne 0 ]
then
	echo "ERROR: Could not complete remote upload through ssh." >&2
	echo "	Error status = $status" >&2
	echo "	Exiting now." >&2
	exit $status
fi