#!/bin/sh
echo $RANDOM | convert -size 512x512 text:- test_image.jpg
