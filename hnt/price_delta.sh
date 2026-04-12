#!/bin/bash

LOG=~/run/logs/price.log
ERR=~/run/logs/error.log
SHMEM=~/run/shm/price
THRESH_FILE=~/run/shm/threshold
PAUSED_FILE=~/run/shm/paused
#BAL=39826
BAL=46254

ABS="define abs(i) {
    if (i < 0) return (-i)
    return (i)
}"

timestamp()
{
 date +"%Y/%m/%d %H:%M"
}

# Read threshold from file if present, else default to 4
if [ -f $THRESH_FILE ]
then
    LIMIT=`cat $THRESH_FILE`
else
    LIMIT=4
fi

DOL_LIMIT=10000
KEY=e3ee7fc553f5815a7e505c84177249d360d81f9f5ZsXLT78uXgM5ZwOtfiEyJShF
export PHONE=6465154570
export MSG_KEY=e3ee7fc553f5815a7e505c84177249d360d81f9f5ZsXLT78uXgM5ZwOtfiEyJShF
export DATE=`date +"%m-%d %H:%M:%S"`

# if the shmem does not exist, create it now and put in 1
if [ ! -f $SHMEM ]
then
	echo "$(timestamp) Creating..." >> $LOG
    echo 1 > $SHMEM
fi

OLD_PRICE=`cat $SHMEM`
CUR_PRICE=`curl -fs  "https://api.coingecko.com/api/v3/simple/price?ids=helium&vs_currencies=usd" | jq '.helium.usd'`
if [ $? -ne 0 ] || [ -z "$CUR_PRICE" ]; then
  echo "Error: failed to fetch or parse price" >&2
  exit 1
fi


DELTA=`echo "scale=3; ($CUR_PRICE - $OLD_PRICE)/($OLD_PRICE)*100" | bc -l`
DELTA=`printf %0.1f $DELTA`
ALPHA=`echo "$ABS; abs($DELTA)" | bc -l`
ALPHA=`printf %0.0f $ALPHA`
BETA=`printf %0.0f $DELTA`
VAL=`echo "scale=0; $CUR_PRICE * $BAL" | bc -l | sed -r ':L;s=\b([0-9]+)([0-9]{3})\b=\1,\2=g;t L'`
DOL=`echo "($CUR_PRICE - $OLD_PRICE) * $BAL" | bc -l`
DOL=`echo "$ABS; abs($DOL)" | bc -l`
DOL=`awk -F. '{print $1}' <<< $DOL`

if [ $1 ]
then
	echo -n "$CUR_PRICE "
	echo "$DELTA% \$$VAL"
fi

if [ $ALPHA -gt $LIMIT ]
#if [ $DOL -gt $DOL_LIMIT ]
then
	if [ $ALPHA -eq $BETA ]
	then
		DIR="Up"
	else
		DIR="DOWN"
	fi

	echo "$(timestamp) Updating ($OLD_PRICE) to ($CUR_PRICE) \$$VAL" >> $LOG
	echo $CUR_PRICE > $SHMEM

	# Only send SMS if alerts are not paused
	if [ -f $PAUSED_FILE ]
	then
		echo "$(timestamp) Paused — skipped SMS ($DIR $DELTA%)" >> $LOG
	else
		quota=`curl -s https://textbelt.com/quota/$KEY | jq '.quotaRemaining'`
		export PHONE=6465154570
		curl -s -X POST https://textbelt.com/text \
     		--data-urlencode phone=$PHONE \
            --data-urlencode message="Helium Price $CUR_PRICE $DIR $DELTA%  \$$VAL (Quota = $quota)" \
     		-d key=$MSG_KEY >> $ERR
		echo "" >> $ERR
	fi
fi

#--data-urlencode message="[$DATE] $CUR_PRICE $DELTA% (Quota = $quota)" \
