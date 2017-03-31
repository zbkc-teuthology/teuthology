#!/bin/bash
set -e

usage () {
	printf '%s: usage: %s TEST_DIR OUTPUT_DIR ZBKC_BUILD_TARBALL\n' "$(basename "$0")" "$(basename "$0")" 1>&2
	exit 1
}

TEST_DIR=$1
OUTPUT_DIR=$2
ZBKC_TARBALL=$3

if [ -z "$TEST_DIR" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$ZBKC_TARBALL" ]; then
	usage
fi

SHA1=`cat $TEST_DIR/zbkc-sha1`

mkdir -p $OUTPUT_DIR/zbkc

echo "Retrieving source and .gcno files..."
wget -q -O- "https://github.com/zbkc/zbkc/tarball/$SHA1" | tar xzf - --strip-components=1 -C $OUTPUT_DIR/zbkc
tar zxf $ZBKC_TARBALL -C $OUTPUT_DIR
cp $OUTPUT_DIR/usr/local/lib/zbkc/coverage/*.gcno $OUTPUT_DIR/zbkc/src
mkdir $OUTPUT_DIR/zbkc/src/.libs
cp $OUTPUT_DIR/usr/local/lib/zbkc/coverage/.libs/*.gcno $OUTPUT_DIR/zbkc/src/.libs
rm -rf $OUTPUT_DIR/usr
# leave zbkc tarball around in case we need to inspect core files

echo "Initializing lcov files..."
lcov -d $OUTPUT_DIR/zbkc/src -z
lcov -d $OUTPUT_DIR/zbkc/src -c -i -o $OUTPUT_DIR/base_full.lcov
lcov -r $OUTPUT_DIR/base_full.lcov /usr/include\* -o $OUTPUT_DIR/base.lcov
rm $OUTPUT_DIR/base_full.lcov
echo "Done."
