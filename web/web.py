#!/usr/bin/env python

from flask import Flask, g, redirect, request, render_template, url_for
import hashlib
import json
import os
import random
import sqlite3
import time


DATABASE = "images.db"
IMAGES_DIR = "images"
INDEX_URI = "/mraaa"

app = Flask(__name__, static_folder=IMAGES_DIR)


# See https://flask.palletsprojects.com/en/latest/patterns/sqlite3/
def db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def cursor_to_dicts(cursor):
    keys = [ x[0] for x in cursor.description ]
    dicts = []
    for row in cursor.fetchall():
        dicts.append(dict(zip(keys, row)))
    return dicts


@app.route("/queue/push", methods=["POST"])
def queue_push():
    model = request.form.get("model", "CompVis/stable-diffusion-v1-4")
    prompt = request.form["prompt"]
    steps = request.form.get("num_inference_steps", 50)
    seed = request.form.get("seed", "")
    if seed:
        seed = int(seed)
    else:
        seed = random.randint(1, 1<<31)
    cursor = db().execute(
        "SELECT * FROM queue WHERE model=? AND prompt=? and num_inference_steps=? and seed=? LIMIT 1",
        [ model, prompt, steps, seed ]
    )
    if cursor.fetchone():
        return "DUPLICATE"
    db().execute(
        "INSERT INTO queue (model, prompt, num_inference_steps, seed, submitted_at) VALUES (?, ?, ?, ?, ?)",
        [ model, prompt, steps, seed, int(time.time()) ]
    )
    db().commit()
    return "OK"


@app.route("/queue/pull", methods=["POST"])
def queue_pull():
    worker = request.form["worker"]
    model = request.form["model"]
    cursor = db().execute("""
        SELECT * FROM queue
        WHERE model=? 
              AND
              (worker IS NULL
               OR
               (worker IS NOT NULL
                AND
                (requeue_at < ?)))
        LIMIT 1
        """, [ model, int(time.time()) ])
    row = cursor.fetchone()
    if not row: #FIXME content type?
        return "{}"
    db().execute(
        "UPDATE queue SET worker=?, requeue_at=? WHERE id=?",
        [ worker, int(time.time())+3600, row["id"] ]
    )
    db().commit()
    return json.dumps(dict(
        model=row["model"],
        prompt=row["prompt"],
        num_inference_steps=row["num_inference_steps"],
        seed=row["seed"],
    ))


@app.route("/queue/<queue_id>", methods=["DELETE"])
def queue_delete(queue_id):
    cursor = db().execute("SELECT * from queue WHERE id=?", [queue_id])
    if cursor.fetchone():
        db().execute("DELETE FROM queue WHERE ID=?", [queue_id])
        db().commit()
        return "OK"
    return "NOT FOUND" # FIXME status code


@app.route("/queue/done", methods=["POST"])
def queue_done():
    model = request.form["model"]
    prompt = request.form["prompt"]
    steps = request.form["num_inference_steps"]
    seed = request.form["seed"]
    completed_at = int(time.time())
    image = request.files["image"].stream.read()
    image_hash = hashlib.sha256(image).hexdigest()
    cursor = db().execute(
        "SELECT id, submitted_at FROM queue WHERE model=? AND prompt=? AND num_inference_steps=? AND seed=? LIMIT 1",
        [model, prompt, steps, seed]
    )
    row = cursor.fetchone()
    if row:
        _id, submitted_at = row
        db().execute("DELETE FROM queue WHERE id=?", [_id])
    else:
        submitted_at = completed_at
    cursor = db().execute("SELECT * FROM images where hash=?", [image_hash])
    if cursor.fetchone():
        # Duplicate, do nothing
        # (This should probably be handled better!)
        #log.warning("Duplicate hash ({}), prompt={} seed={} steps={}".format(image_hash, prompt, seed, steps))
        db().commit()
        return "DUPLICATE"
    db().execute(
        "INSERT INTO images (hash, model, prompt, num_inference_steps, seed, submitted_at, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [ image_hash, model, prompt, steps, seed, submitted_at, completed_at ]
    )
    image_directory = os.path.join(IMAGES_DIR, image_hash)
    os.makedirs(image_directory)
    with open(os.path.join(image_directory, "out.jpg"), "wb") as f:
        f.write(image)
    db().commit()
    return "OK"

 
@app.route(INDEX_URI)
def index():
    query = request.values.get("q", "")
    limit = request.values.get("pagesize", 20)
    page = int(request.values.get("page", 1))
    if page < 1:
        page = 1
    offset = (page - 1) * limit
    if query:
        sql_query = "SELECT * FROM images WHERE " + " AND ".join(["prompt LIKE ?" for w in query.split()])
        sql_values = ["%{}%".format(word) for word in query.split()]
    else:
        sql_query = "SELECT * FROM images"
        sql_values = []
    sql_query += " ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    sql_values += [ limit, offset ]
    return show(sql_query, sql_values)


@app.route("/image/<image_hash>/tags")
def tags(image_hash):
    cursor = db().execute("SELECT tag FROM tags WHERE hash=?", (image_hash,))
    return json.dumps([row[0] for row in cursor.fetchall()])


@app.route("/image/<image_hash>/tag/<tag>")
def tag(image_hash, tag):
    cursor = db().execute("SELECT 1 FROM tags WHERE hash=? AND tag=?", (image_hash, tag))
    if cursor.fetchone():
        return "OK"
    db().execute("INSERT INTO tags (hash, tag) VALUES (?, ?)", (image_hash, tag))
    db().commit()
    return "OK"


@app.route("/image/<image_hash>/untag/<tag>")
def untag(image_hash, tag):
    db().execute("DELETE FROM tags WHERE hash=? AND tag=?", (image_hash, tag))
    db().commit()
    return "OK"


def show(sql_query, sql_values=()):
    html = "<!DOCTYPE html>"
    html += "<head>"
    html += "<title>Stable Diffusion Frontend</title>\n"
    html += """<style type="text/css">
        div.image {
            position: relative;
            width: 512px;
            float: left;2
        }
        div.image p {
            position: absolute;
            z-index: 1;
            background: yellow;
            padding: 1em;
            bottom: 0;
            left: 1em;
        }
        div.image ul {
            position: absolute;
            z-index: 1;
            background: white;
            padding: 0.1em;
            top: 0;
            left: 1em;
        }
        div.image ul li {
            display: inline;
            font-size: 2em;
            padding: 0.1em;
        }
        td {
            background: #ddd9;
        }
    </style>"""
    html += """<script type="text/javascript">
    function queue_delete(id) {
            fetch("/queue/"+id, {method: "DELETE"}).then(response => {
                 document.getElementById("queue_"+id).style.display = "none"; 
            });
    }
    </script>"""
    html += "</head>"
    html += "<body>"

    html += "<h1>Search</h1>\n"
    html += "<form method=GET action=/>\n"
    html += "<input type=text name=q>\n"
    html += "<input type=submit>\n"
    html += "</form>\n"

    html += "<h1>Add request to queue</h1>\n"
    html += "<form method=POST action=/queue/push>\n"
    html += "Prompt:<input type=text name=prompt>\n"
    html += "Seed:<input type=text name=seed>\n"
    html += "Steps:<input type=text name=num_inference_steps value=50>\n"
    html += "Model:<input type=text name=model value=CompVis/stable-diffusion-v1-4>\n"
    html += "<input type=submit>\n"
    html += "</form>\n"

    html += "<h1>Requests in queue</h1>\n"
    html += "<table>\n"
    html += "<tr><th>Delete</th><th>Worker</th><th>Expiration</th><th>Model</th><th>Steps</th><th>Seed</th><th>Prompt</th></tr>\n"
    cursor = db().execute("SELECT * FROM queue")
    for row in cursor.fetchall():
        html += "<tr id=queue_{id}><td><button onclick=\"queue_delete({id})\">X</button><td>{worker}</td><td>{requeue_at}</td><td>{model}</td><td>{num_inference_steps}</td><td>{seed}</td><td>{prompt}</td></tr>\n".format(**row)
    html += "</table>\n"

    html += "<h1>Output</h1>\n"
    cursor = db().execute(sql_query, sql_values)
    images = []
    for row in cursor.fetchall():
        image = dict(row)
        image["url"] = url_for("static", filename=os.path.join(image["hash"], "out.jpg"))
        images.append(image)
        image["caption"] = caption(image)
    for image in images[:]:
        html += """
<div class="image">
<img src="{url}" alt="{prompt} ({hash})">
<p>{caption}</p>
<ul>
<li><a href="#" onClick>❤️</a></li>
<li><a href="#">➕</a></li>
<li><a href="#">✨</a></li>
<li><a href="#">🚮</a></li>
</ul>
</div>
""".format(**image)
    html += "</body>"
    html += "</html>"
    return html


def caption(image):
    caption = image["prompt"]
    extras = []
    model = image["model"]
    model = {
        "CompVis/stable-diffusion-v1-4": "SD-1.4",
    }.get(model, model)
    extras.append(model)
    if "num_inference_steps" in image:
        extras.append("{num_inference_steps} steps".format(**image))
    if "seed" in image:
        extras.append("seed={seed}".format(**image))
    if extras:
        caption += " (" + ", ".join(extras) + ")"
    return caption


app.run(host="0.0.0.0", debug=True)
