#!/bin/sh
curl localhost:5000/queue/push --form-string "prompt=a drawing of a rainbow" --form-string num_inference_steps=10 --form-string model=test

