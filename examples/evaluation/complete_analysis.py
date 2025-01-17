"""
Gives a complete analysis of the
selected peaks and their annotation
Helps finding correspondences between different
samples

Generates a summary file (.xls)
"""
import argparse
import xlsxwriter
import csv
import pprint
import cv2
import numpy as np
import os
import SimpleITK as sitk
import matplotlib.pyplot as plt

from xlsxwriter.utility import xl_rowcol_to_cell, xl_col_to_name
from PIL import Image
from io import BytesIO

import esmraldi.imzmlio as imzmlio
import esmraldi.speciesrule as sr
import esmraldi.spectraprocessing as sp
import esmraldi.spectrainterpretation as si
from esmraldi.theoreticalspectrum import TheoreticalSpectrum

def get_col_widths(data):
    """
    Compute the maximum column width
    (in number of characters)

    Parameters
    ----------
    data: np.ndarray
        input data

    Returns
    ----------
    int
        max width
    """
    mylen = np.vectorize(len)
    lengths = mylen(data.astype('str'))
    maximum = np.amax(lengths, axis=1)
    return maximum

def split_name(name):
    """
    Split the species name
    to a readable format

    Example:
    Mol_Adduct_Modif is converted to:
    Mol Modif (Adduct)

    Parameters
    ----------
    name: str
        input name

    Returns
    ----------
    str
        split name
    """
    list_names = name.split("_")
    new_name = list_names[0] + ("." + ".".join(list_names[2:]) if len(list_names) > 2 else "") + " (" + list_names[1] + ")"
    return new_name

def dict_to_array(masses):
    """
    Converts a mz/name dict
    to a numpy array

    Parameters
    ----------
    masses: dict
        annotated species dictionary

    Returns
    ----------
    np.ndarray
        annotated species array
    """
    max_len = max([len(v) for k,v in masses.items()])
    mz = list(masses.keys())
    values = list(masses.values())
    values_array = [ [split_name(names[i]) if i < len(names) and names[i] != "" else None for names in values] for i in range(max_len)]
    data = np.vstack((mz, *values_array))
    return data

def write_mass_list(worksheet, column_names, masses, mean_spectrum):
    """
    Write annotated mass list to a spreadsheet

    Parameters
    ----------
    worksheet: xlsxwriter.Worksheet
        current worksheet
    column_names: list
        column header names
    masses: np.ndarray
        data array (mz, annotation)
    mean_spectrum: np.ndarray
        average intensity values for the species

    """
    headers = ["m/z", "Average intensities"] + column_names
    for i in range(len(headers)):
        worksheet.write(0, i, headers[i], header_format)

    worksheet.freeze_panes(1, 0)

    row = 1
    col = 0

    data = dict_to_array(masses)
    data = np.vstack((data[0], mean_spectrum, data[1:]))
    for d in data:
        worksheet.write_column(1, col, d)
        col+=1

    widths = get_col_widths(data)
    for i in range(widths.shape[0]):
        worksheet.set_column(i, i, int(widths[i]))


def add_table(worksheet, masses, image):
    """
    Add statistics table to a spreadsheet

    Parameters
    ----------
    worksheet: xlsxwriter.Worksheet
        current worksheet
    masses: np.ndarray
        data array (mz, annotation)
    image: np.ndarray
        MALDI image datacube

    """
    mz_curated = list(masses.keys())
    names_curated = list(masses.values())

    average_replicates = np.mean(np.mean(image, axis=1), axis=0)
    average_peaks = np.mean(np.mean(image, axis=0), axis=0)
    std_replicates = np.std(np.mean(image, axis=1), axis=0)
    std_peaks = np.std(np.mean(image, axis=0), axis=0)
    variability_replicates = np.divide(std_replicates, average_replicates)
    variability_peaks = np.divide(std_peaks, average_peaks)
    stats = np.vstack((mz_curated, variability_peaks, average_peaks, std_peaks, variability_replicates, average_replicates, std_replicates)).T
    worksheet.add_table(0, 0, stats.shape[0], stats.shape[1]-1, {"data":stats, 'columns':[
        {'header': 'm/z'},
        {'header': 'Variability samples'},
        {'header': 'Average samples'},
        {'header': 'Stddev samples'},
        {'header': 'Variability replicates'},
        {'header': 'Average replicates'},
        {'header': 'Stddev replicates'}]
    })

    for i in range(stats.shape[1]):
        worksheet.conditional_format(1, i, stats.shape[0], i,
                                     {'type': '3_color_scale',
                                      'min_color': "#92d050",
                                      'mid_color': "#ffcc00",
                                      'max_color': "#ed6161"})
    for i in range(stats.shape[0]):
        col_letter = xl_col_to_name(i+1)
        worksheet.write_url(i+1, 0, "internal:'Images'!"+col_letter+":"+col_letter, string=str(mz_curated[i]))

    widths = get_col_widths(stats)
    for i in range(widths.shape[0]):
        worksheet.set_column(i, i, int(widths[i]))


def insertable_image(image, size):
    """
    Converts an image to binary
    for insertion inside a spreadsheet

    Parameters
    ----------
    image: np.ndarray
        numpy image
    size: tuple
        new size

    Returns
    ----------
    BytesIO
        insertable image
    """
    image_i = ((image - image.min()) * (1/(image.max() - image.min()) * 255)).astype('uint8')
    new_im = np.array(Image.fromarray(image_i).resize(size))
    im, a_numpy = cv2.imencode(".png", new_im)
    a = a_numpy.tostring()
    image_data = BytesIO(a)
    return image_data

def add_images(worksheet, column_names, masses, image):
    """
    Add images in spreadsheet

    Parameters
    ----------
    worksheet: xlsxwriter.Worksheet
        spreadsheet
    column_names: list
        column header names
    masses: np.ndarray
        data: mz and annotation
    image: np.ndarray
        MALDI image datacube
    """
    data = dict_to_array(masses)
    for i in range(image.shape[-1]):
        image_i = image[..., i].T
        image_data = insertable_image(image_i, (number_samples*20, number_replicates*20))
        worksheet.insert_image(0, i+1, "", {'image_data': image_data, 'object_position': 4})


    headers = ["Sample #"+str(i+1) for i in range(number_replicates)] + ["m/z"] + column_names

    for i in range(len(headers)):
        worksheet.write(i, 0, headers[i], header_format)
    worksheet.freeze_panes(0, 1)

    for i in range(data.shape[0]):
        worksheet.write_row(number_replicates+i, 1, data[i], cell_format=left_format)

    widths = get_col_widths(data)
    width_headers = get_col_widths(np.array([headers]))
    worksheet.set_column(0, 0, width_headers[0])
    max_width = np.amax(widths.astype("int"))
    for i in range(data.shape[1]):
        worksheet.set_column(i+1, i+1, max_width)

def add_reduction(worksheet, reduction_dir):
    """
    Add dimension reduction analysis
    in a spreadsheet

    Parameters
    ----------
    worksheet: xlsxwriter.Worksheet
        spreadsheet
    reduction_dir: str
        directory containing dimension reduction results

    """
    files_reduction = os.listdir(reduction_dir)
    csv_name = [reduction_dir + os.path.sep + filename for filename in files_reduction if filename.endswith(".csv")][0]
    image_names = [reduction_dir + os.path.sep + filename for filename in files_reduction if filename.endswith(".png")]
    n = len(image_names) // 2
    gradients = gradient(n, 120, 255)
    formats = []
    for g in gradients:
        f = workbook.add_format({"fg_color":g})
        formats.append(f)

    with open(csv_name) as f:
        csv_reader = csv.reader(f, delimiter=";")
        i = 0
        for row in csv_reader:
            j = 0
            for cell in row:
                worksheet.write(i+12, j, cell, formats[j//3 if j//3 < len(formats) else -1])
                j += 1
            i += 1
    for i in range(0, len(image_names), 2):
        representative = image_names[i]
        score = image_names[i+1]
        np_representative = plt.imread(representative)[..., 0]
        h_representative, w_representative = np_representative.shape[0], np_representative.shape[1]
        w, h = int(number_replicates*20*w_representative/h_representative), number_replicates*20
        worksheet_representative = insertable_image(np_representative, (w, h))
        worksheet.insert_image(0, int(i*1.5), "", {'image_data': worksheet_representative, 'object_position': 4})


def gradient(n, start, end):
    """
    Gray-level gradient (hexadecimal)

    Parameters
    ----------
    n:  int
        number of colors
    start: int
        starting gray level
    end: int
        end gray level

    Returns
    ----------
    list
        graient list

    """
    g = []
    for i in range(n):
        gray_level = int(i * (end-start) / (n-1) + start)
        gray_hex = hex(gray_level).replace("0x", "")
        gray_code = "#" + gray_hex * 3
        g.append(gray_code)
    return g

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", help="MALDI image")

parser.add_argument("-a", "--annotation", help="Annotation (csv file)")
parser.add_argument("-r", "--reduction_dir", help="Dimension reduction analysis directory, as generated by analysis_reduction (optional)")
parser.add_argument("-m", "--mzs", help="MZS corresponding to MALDI image (optional)")
parser.add_argument("-o", "--output", help="Output .xlsx file")

args = parser.parse_args()

annotation_name = args.annotation
input_name = args.input
mzs_name = args.mzs
output_name = args.output
reduction_dir = args.reduction_dir

imzml = imzmlio.open_imzml(input_name)
spectra = imzmlio.get_spectra(imzml)
full_spectra = imzmlio.get_full_spectra(imzml)
max_x = max(imzml.coordinates, key=lambda item:item[0])[0]
max_y = max(imzml.coordinates, key=lambda item:item[1])[1]
max_z = max(imzml.coordinates, key=lambda item:item[2])[2]
image = imzmlio.get_images_from_spectra(full_spectra, (max_x, max_y, max_z))
observed_spectrum, intensities = imzml.getspectrum(0)

number_samples = image.shape[0]
number_replicates = image.shape[1]

masses = {}
with open(annotation_name, "r") as f:
    reader = list(csv.reader(f, delimiter=";"))

has_headers = reader[0][0] == ""
for row in reader[1 if has_headers else 0:]:
    k = float(row[0])
    v = [row[1+i] for i in range(len(row)-1)]
    masses[k] = v

max_len = max([len(v) for k,v in masses.items()])
if has_headers:
    column_names = [split_name(r) for r in reader[0][1:]]
else:
    column_names = ["Ion (#" +str(i+1) +")" for i in range(max_len)]

mean_spectrum = sp.spectra_mean(spectra)

masses_curated = {}
mean_spectrum_curated = []
index = 0
for k, v in masses.items():
    if any([value != "" for value in v]):
        masses_curated[k] = v
        mean_spectrum_curated.append(mean_spectrum[index])
    index += 1

mean_spectrum_curated = np.array(mean_spectrum_curated)

workbook = xlsxwriter.Workbook(output_name)

header_format = workbook.add_format({'bold': True,
                                     'align': 'center',
                                     'valign': 'vcenter',
                                     'fg_color': '#D7E4BC',
                                     'border': 1})

left_format = workbook.add_format({'align': 'left'})


worksheet = workbook.add_worksheet("Mass list")
worksheet2 = workbook.add_worksheet("Mass list (curated)")
worksheet3 = workbook.add_worksheet("Statistics")
worksheet4 = workbook.add_worksheet("Images")


write_mass_list(worksheet, column_names, masses, mean_spectrum)
write_mass_list(worksheet2, column_names, masses_curated, mean_spectrum_curated)
add_table(worksheet3, masses, image)
add_images(worksheet4, column_names, masses, image)

if reduction_dir:
    worksheet5 = workbook.add_worksheet("Reduction")
    add_reduction(worksheet5, reduction_dir)


workbook.close()

# pp = pprint.PrettyPrinter(indent=1)
# pp.pprint(keys_sorted)
