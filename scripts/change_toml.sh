#!/bin/sh

REPLACE=DetectMateLibrary.git

if [ $# -eq 0 ]
then
	echo "No branch selected. Keeping original pyproject.toml"
	exit 0
fi

if [ "$1" != "main" ]
then
	BRANCH="development"
else
	BRANCH="main"
fi

echo "Using branch: $BRANCH"

sed -i "s/$REPLACE/$REPLACE@$BRANCH/g" pyproject.toml
