#!/usr/bin/env python

import json
import os
import sqlite3
import sys

db = sqlite3.connect("images.db")


for image_hash in os.listdir(sys.argv[1]):
	print(image_hash)
	image_dir = os.path.join(sys.argv[1], image_hash)
	image_json = open(os.path.join(image_dir, "in.json")).read()
	image_data = json.loads(image_json)
	image_data["hash"] = image_hash
	timestamp = int(open(os.path.join(image_dir, "timestamp")).read().split(".")[0])
	image_data["submitted_at"] = timestamp
	image_data["completed_at"] = timestamp
	print(image_data)
	kvpairs = list(image_data.items())
	columns = ",".join(kv[0] for kv in kvpairs)
	qmarks = ",".join("?" for _ in kvpairs)
	values = [kv[1] for kv in kvpairs]
	db.execute("INSERT INTO images ({}) VALUES ({})".format(columns, qmarks), values)

db.commit()