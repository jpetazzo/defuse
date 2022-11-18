#!/usr/bin/env python
import requests
from io import BytesIO

image = BytesIO(open("test_image.jpg", "rb").read())

response = requests.post(
	"http://localhost:5000/queue/done",
	data=dict(
		model="test",
		prompt="test",
		num_inference_steps=10,
		seed=42,
	),
	files=dict(
		image=image,
	)
)
print(response.text)
