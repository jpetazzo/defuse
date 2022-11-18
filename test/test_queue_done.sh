#!/bin/sh
curl localhost:5000/queue/done --form-string model=test --form-string prompt=test --form-string num_inference_steps=10 --form-string seed=1 --form image=@test_image.jpg
