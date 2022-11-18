create TABLE images (
  hash string NOT NULL PRIMARY KEY,
  submitted_at timestamp NOT NULL,
  completed_at timestamp NOT NULL,
  model string NOT NULL,
  prompt string NOT NULL,
  num_inference_steps integer NOT NULL,
  seed integer
);

create TABLE tags (
  hash string NOT NULL,
  tag string,
  PRIMARY KEY (hash, tag)
);

create TABLE queue (
  id integer PRIMARY KEY AUTOINCREMENT,
  submitted_at timestamp NOT NULL,
  model string NOT NULL,
  prompt string NOT NULL,
  num_inference_steps integer NOT NULL,
  seed integer NOT NULL,
  generation integer,    -- Used to force generation of multiple images with same parameters
  worker string,         -- Which worker has been assigned to it
  requeue_at timestamp,  -- Time after which we estimate that the worker has crashed/won't do it
  UNIQUE (model, prompt, num_inference_steps, seed, generation)
);