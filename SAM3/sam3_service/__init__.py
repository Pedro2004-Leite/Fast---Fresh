"""HTTP service around a resident SAM 3: submit an image and a prompt, get masks back.

One worker process per GPU holds the model for the life of the service.  Jobs
go through a single shared queue, so a free GPU takes the next job.  Inside a
worker, three threads overlap so the GPU is not left waiting on the CPU:

    loader  : decode + resize the image, copy it to the GPU on a side stream
    gpu     : backbone encode + prompt forward (the only thread that runs the model)
    post    : map masks back to the original frame, NMS, write result files

The service runs the *generic pass* only -- one image, an optional text prompt,
optional external reference images with positive/negative boxes.  It does not
run the vein or grain pipelines and never reads the exemplar registry.

The SAM 3 plumbing (visual tokens, joint prompting, mask NMS) is the
``conceptseg`` package, imported as an installed library and not modified.
"""
