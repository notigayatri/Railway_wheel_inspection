
Wheel Defect Detection - v3 2024-08-01 5:41pm
==============================

This dataset was exported via roboflow.com on August 2, 2024 at 4:14 AM GMT

Roboflow is an end-to-end computer vision platform that helps you
* collaborate with your team on computer vision projects
* collect & organize images
* understand and search unstructured image data
* annotate, and create datasets
* export, train, and deploy computer vision models
* use active learning to improve your dataset over time

For state of the art Computer Vision training notebooks you can use with this dataset,
visit https://github.com/roboflow/notebooks

To find over 100k other datasets and pre-trained models, visit https://universe.roboflow.com

The dataset includes 867 images.
Cracks-sheeling-discoloration are annotated in YOLOv8 format.

The following pre-processing was applied to each image:
* Auto-orientation of pixel data (with EXIF-orientation stripping)
* Resize to 640x640 (Stretch)
* Auto-contrast via contrast stretching

The following augmentation was applied to create 3 versions of each source image:
* 50% probability of horizontal flip
* 50% probability of vertical flip
* Equal probability of one of the following 90-degree rotations: none, clockwise, counter-clockwise, upside-down
* Randomly crop between 0 and 1 percent of the image
* Random rotation of between -15 and +15 degrees
* Random shear of between -1° to +1° horizontally and -1° to +1° vertically
* Random brigthness adjustment of between -1 and +1 percent
* Random exposure adjustment of between -1 and +1 percent
* Random Gaussian blur of between 0 and 0.1 pixels
* Salt and pepper noise was applied to 0.02 percent of pixels


