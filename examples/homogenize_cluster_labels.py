"""
Give same cluster labels to image
based on overall point proximities
to reference image
"""

import numpy as np
import matplotlib.pyplot as plt
import SimpleITK as sitk
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", help="Input MALDI image (imzML or nii)")
parser.add_argument("-r", "--reference", help="Reference image to copy labels")
parser.add_argument("-o", "--output", help="Output image (ITK format)")
args = parser.parse_args()

inputname = args.input
referencename = args.reference
outname = args.output


image = sitk.ReadImage(inputname, sitk.sitkUInt16)
reference = sitk.ReadImage(referencename, sitk.sitkInt16)

image_array = sitk.GetArrayFromImage(image).astype(np.int16)
reference_array = sitk.GetArrayFromImage(reference).astype(np.int16)

max_label = reference_array.max()
new_image_array = np.zeros_like(image_array)
for label in range(max_label+1):
    indices = np.where(reference_array == label)
    image_label = np.median(image_array[indices])
    print(image_label)
    indices_image = np.where(image_array == image_label)
    new_image_array[indices_image] = label

colors = "Set1"
fig, ax = plt.subplots(1,3)
ax[0].imshow(reference_array, cmap=colors)
ax[1].imshow(image_array, cmap=colors)
ax[2].imshow(new_image_array, cmap=colors)
plt.show()

plt.axis("off")
plt.imshow(new_image_array.T, cmap=colors)
plt.savefig(outname, transparent=True, bbox_inches='tight', pad_inches=0, dpi=150)
