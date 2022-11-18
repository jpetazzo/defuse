#!/bin/sh
curl localhost:5000/queue/pull --form-string worker=test --form-string model=test
