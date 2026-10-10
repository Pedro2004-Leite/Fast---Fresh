from crop_planogram import crop_planogram

# One image per camera (earliest timestamp), flat output: output/crops/<camera_id>/<area_id>.png
#crop_planogram("dataset/planogram.json", "dataset", "output/crops", per_camera="first")

# Every image (the default): output/crops/<camera_id>/<timestamp>/<area_id>.png
crop_planogram("dataset/planogram.json", "dataset", "output/crops")

# One specific file name for every camera (if present): output/crops/<camera_id>/<area_id>.png
#crop_planogram("dataset/planogram.json", "dataset", "output/crops", image_name="1751001268.jpg") 


