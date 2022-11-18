#!/usr/bin/env python

import torch
from diffusers import StableDiffusionPipeline
import json
import os
from io import BytesIO
import hashlib
import time
import logging
import requests
import socket
import base64

import hub

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

API_ENDPOINT = os.environ.get("API_ENDPOINT", "http://localhost:5000")
MODEL_ID = os.environ.get("MODEL_ID", "CompVis/stable-diffusion-v1-4")
WORKER_ID = os.environ.get(
    "WORKER_ID", "{}_{}".format(socket.gethostname(), int(time.time()))
)
SAFETY_CHECKER = os.environ.get("SAFETY_CHECKER", "y").lower() not in (
    "0",
    "off",
    "no",
    "n",
)
TORCH_DEVICE = os.environ.get(
    "TORCH_DEVICE", "cuda" if torch.cuda.is_available() else "cpu"
)


def update_status(message):
    log.info("Current status: {}".format(message))
    hub.update_status(WORKER_ID, timetamp=time.time(), message=message)


update_status("loading model")
pipe = StableDiffusionPipeline.from_pretrained(
    MODEL_ID, torch_dtype=torch.float32, local_files_only=False
)


update_status("moving pipeline to device ({})".format(TORCH_DEVICE))
pipe = pipe.to(TORCH_DEVICE)


if not SAFETY_CHECKER:
    pipe.safety_checker = lambda images, *args, **kwargs: (images, False)


def callback(step, progress_tensor, latents):
    percent = (1000 - progress_tensor.item()) // 10
    update_status("inferencing, step={}, percent={}".format(step + 1, percent))


while True:
    try:
        update_status("waiting from queue")
        while True:
          response = requests.post(API_ENDPOINT + "/queue/pull", data=dict(model=MODEL_ID, worker=WORKER_ID))
          work = response.json()
          if work: break
          time.sleep(1)
        update_status("inferencing, step=0, percent=0")
        kwargs = work.copy()
        kwargs.pop("model")
        if "seed" in kwargs:
          kwargs["generator"] = torch.Generator(TORCH_DEVICE).manual_seed(int(kwargs.pop("seed")))
        results = pipe(callback=callback, **kwargs)
        update_status("saving image")
        image_pil = results[0][0]
        image_io = BytesIO()
        image_pil.save(image_io, format="JPEG")
        image_io.seek(0)
        work["completed_at"] = int(time.time())
        requests.post(API_ENDPOINT + "/queue/done", data=work, files=dict(image=image_io))
        update_status("done")
    except Exception:
        log.exception("When trying to process item from queue:")
        log.warning("Waiting 10 seconds before retrying main loop.")
        time.sleep(10)
