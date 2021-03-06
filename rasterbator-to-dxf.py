#!/usr/bin/env python3
# coding: utf-8

# MIT License
#
# Copyright (c) 2021 Christoph Schmied
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import os

import ezdxf as dx
import matplotlib.pyplot as plt
import numpy as np
import pdfplumber
from ezdxf import units
from scipy.spatial import distance
from svgpathtools import svg2paths
from svgpathtools.path import CubicBezier
from tqdm import tqdm

doc_out = dx.new('R2010')
doc_out.units = units.IN

diams = []
a0_points = [(0, 0), (46.8, 0), (46.8, 33.1), (0, 33.1)]
a4_points = [(0, 0), (11.7, 0), (11.7, 8.3), (0, 8.3)]
page_points = a0_points
min_diam = 1.5
pdftocairo_dpi = 72
coords = []

def get_page_points(path):
    """
    Return points coordinates for page extent
    :param path: pth to PDF file
    :return: extent points
    """
    with pdfplumber.open(path) as pdf:
        page_1 = pdf.pages[0]
        w = float(page_1.width) / pdftocairo_dpi
        h = float(page_1.height) / pdftocairo_dpi
        return [(0, 0), (w, 0), (w, h), (0, h)]


def is_valid_file(arg_parse, arg):
    """
    test if file is valid (pdf or dxf)
    :param arg_parse: argument parser
    :param arg: filename
    :return: filename if valid
    """
    if not os.path.exists(arg):
        arg_parse.error("The file %s does not exist!" % arg)
    elif os.path.splitext(arg)[-1] not in ['.pdf', '.dxf']:
        arg_parse.error("supported filetypes are .pdf and .dxf")
    else:
        return arg


def get_center_and_radius(points):
    """
    Calculate bounding box of points in polyline and return center and diameter of fitting circle
    :param points: Points in the polyline
    :return: center of circle (x,y) and radius
    """
    x_coordinates, y_coordinates = zip(*points)

    x_min = min(x_coordinates)
    x_max = max(x_coordinates)
    y_min = min(y_coordinates)
    y_max = max(y_coordinates)

    x_diff = (x_max - x_min) / 2
    y_diff = (y_max - y_min) / 2

    return (x_min + x_diff, y_min + y_diff), y_diff


def get_center_and_radius_svg(bbox):
    """
    calculate center and diameter of fitting circle from bounding box
    :param bbox: Bounding box of svg element
    :return: center of circle (x,y) and radius
    """
    x_min, x_max, y_min, y_max = [v / pdftocairo_dpi for v in bbox]
    y_max_new = max(page_points)[1] - y_min
    y_min_new = max(page_points)[1] - y_max

    x_diff = (x_max - x_min) / 2
    y_diff = (y_max_new - y_min_new) / 2

    return (x_min + x_diff, y_min_new + y_diff), y_diff


def add_circle_to_output(center, radius):
    """
    Adds a circle to the output file
    :param center: center coordinates (x,y)
    :param radius: radius of the circle
    """
    diam_mm = radius * 25.4 * 2
    diam_mm = round(diam_mm * 2) / 2

    if diam_mm >= min_diam:
        diams.append(diam_mm)
        coords.append((center[0] * 25.4, center[1] * 25.4, diam_mm / 2))
        doc_out.modelspace().add_circle(center, diam_mm / 2 / 25.4)


def polyline_to_circle(line):
    """
    Transform a circle consisting of a polyline into a DXF circle
    :param line: Polyline
    """
    with line.points('xy') as points:
        center, radius = get_center_and_radius(points)
        add_circle_to_output(center, radius)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='rasterbator-to-dxf',
                                     description='Convert a rasterbated PDF or a DXF file containing polyline-circle features to a DXF file containing circles.')
    parser.add_argument("-i", dest="infile", required=True,
                        help="PDF input file or DXF containing polyline circle features", metavar="FILE",
                        type=lambda x: is_valid_file(parser, x))
    parser.add_argument("-o", dest="outfile", required=False,
                        help="output file name", metavar="FILE", type=str)
    parser.add_argument('--hist', default=False, dest='plot_hist', help='plot histogram of circle diameters',
                        action='store_true')
    parser.add_argument('--min-diameter', type=float, default=1.5, dest='min_diam', help="minimum diameter of circle")
    args = parser.parse_args()

    min_diam = args.min_diam

    infile_name = os.path.splitext(args.infile)[0]
    infile_ext = os.path.splitext(args.infile)[1]
    is_pdf = True if infile_ext == ".pdf" else False

    if not args.outfile:
        args.outfile = infile_name + "_new.dxf"

    if not is_pdf:

        print(f'Parsing input file "{args.infile}" for polyline entities ...', end=' ')

        doc = dx.readfile(args.infile)
        doc.units = units.IN
        msp = doc.modelspace()

        num_entities = msp.query('LWPOLYLINE').__len__()

        print(f'{num_entities} entities of type "LWPOLYLINE" found!')

        for e in tqdm(msp):
            if e.dxftype() == 'LWPOLYLINE':
                polyline_to_circle(e)
    else:
        page_points = get_page_points(args.infile)
        temp_svg = os.path.dirname(args.infile) + '/temp.svg'
        print(f'Converting "{args.infile}" with tool "pdftocairo" to {temp_svg} ...', end=' ')
        os.system(f'pdftocairo -f 0 -l 0 -svg -origpagesizes {args.infile} {temp_svg}')

        paths, attrs = svg2paths(temp_svg)
        os.remove(temp_svg)

        print("DONE")

        print(f'Parsing input file "{args.infile}" for circular features ...', end=' ')
        circles = [get_center_and_radius_svg(p.bbox()) for p in paths if
                   all(map(lambda e: isinstance(e, CubicBezier), p._segments))]

        print(f'{len(circles)} features found!')

        for center, radius in tqdm(circles):
            add_circle_to_output(center, radius)

        # calculate distances between circle outlines
        coords = np.asarray(coords)
        coords[:, 2] = np.around(coords[:, 2] * 2) / 2

        rr, rrr = np.meshgrid(coords[:, 2], coords[:, 2])
        dists = np.abs(np.tril(distance.cdist(coords[:, :1], coords[:, :1]) - rr - rrr))
        dists = dists[dists != 0.0]

    doc_out.modelspace().add_lwpolyline(page_points, close=True)
    doc_out.saveas(args.outfile)
    print(f'Output file "{args.outfile}" saved!')

    print(f"Number of circles: {len(diams)}")
    print(f"Minimum diameter: {min(diams):.2f} mm")
    print(f"Maximum diameter: {max(diams):.2f} mm")
    print(f"Minimum distance: {np.min(dists):.2f} mm")
    print(f"Maximum distance: {np.max(dists):.2f} mm")
    print(f"Mean distance: {np.mean(dists):.2f} mm")

    if args.plot_hist:
        fig, ax = plt.subplots(1, 2, figsize=(16, 6))
        n, bins, patches = ax[0].hist(diams, 50, alpha=0.75)
        n, bins, patches = ax[1].hist(dists.flatten(), 50, alpha=0.75)

        ax[0].set_xlabel('Diameter')
        ax[0].set_ylabel('Count')
        ax[0].set_title('Histogram of the diameter of the circles to cut')
        ax[0].grid(True)

        ax[1].set_xlabel('Distances')
        ax[1].set_ylabel('Count')
        ax[1].set_title('Histogram of the distances between circles to cut')
        ax[1].grid(True)
        plt.tight_layout()
        plt.show()
