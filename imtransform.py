#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import ast
import os
import math

from PIL import Image

import numpy as np

def read_anchors(fname):
  try:
    with open(fname, 'rt') as f:
      header = f.readline().strip()
      anchor_names = [_.strip() for _ in header.split('\t')]
      anchors = []
      while True:
        line = f.readline()
        if len(line) == 0:
          break

        anchors_str = [_.strip() for _ in line.strip().split('\t')]
        anchors_tup = [ast.literal_eval(_) for _ in anchors_str]
        anchors.append(anchors_tup)
  except IOError:
    return (None, None)

  return (anchor_names, anchors)

def parse_command_line():
  parser = argparse.ArgumentParser(
    description="Align image set.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('files', type=str, nargs='+',
                      help="a file in the image set.")
  parser.add_argument('-o', '--output', default=None,
                      help="folder where to store anchor positions")
  parser.add_argument('-p', '--params', help="file containing transformation "+
                      "parameters.")
  parser.add_argument('-a', '--anchors', default=None,
                      help="file containing untransformed anchor positions")
  parser.add_argument('--crop', default=None,
                      help="crop area (four numbers separated by commas, "
                          +"x0, y0, x1, y1)")
  parser.add_argument('-s', '--final-size', default="720,1280",
                      help="final image size (two numbers separated by comma)")

  args = parser.parse_args()

  return args

def parse_key_tuple(s, key):
  idx1 = s.find(key)
  if idx1 >= 0:
    expr = s[idx1+len(key):].strip()
    if expr[0] == '=':
      expr = expr[1:].strip()
      if expr[0] == '(':
        idx1e = expr.find(')')
        if idx1e >= 0:
          expr = expr[:idx1e+1]
          return ast.literal_eval(expr)

  return None

def read_trafos(fname):
  with open(fname, 'rt') as f:
    trafos = []
    first_comment = None
    header = None
    pad_x = 0
    pad_y = 0
    width = 5500
    height = 3500
    while True:
      line = f.readline().strip()
      if len(line) == 0:
        break
      
      if line[0] == '#':
        if first_comment is None:
          first_comment = line
          pad_value = parse_key_tuple(first_comment, "pad")
          dims_value = parse_key_tuple(first_comment, "dims")
          
          if pad_value is not None and len(pad_value) == 2:
            pad_x, pad_y = pad_value
          if dims_value is not None and len(dims_value) == 2:
            width, height = dims_value
          
        continue

      params_str = [_.strip() for _ in line.split('\t')]
      if header is None:
        header = params_str
      else:
        trafo = {param: float(params_str[i]) for i, param in enumerate(header)}
        trafo['pad'] = (pad_x, pad_y)
        trafo['dims'] = (width, height)
        trafos.append(trafo)

    return trafos

def transform(files, trafos, out_dir, anchors, crop=None, final_size=None):
  i = 0
  n = min(len(files), len(trafos))
  crop_region = crop
  final_size_mod = None
  for fname, trafo in zip(files, trafos):
    base_name, ext = os.path.splitext(os.path.basename(fname))
#    out_fname = base_name + '_trans' + ext
#    out_path = os.path.join(out_dir, out_fname)
    out_path = os.path.join(out_dir, 'img{:05}.jpg'.format(i))

    print("Image {} of {}.".format(i+1, n))

    img0 = Image.open(fname)
    if anchors is not None:
      n_anchors = len(anchors[i])
      for j in xrange(n_anchors):
        anchor = np.asarray(anchors[i][j])
        img0.putpixel(anchor, (255, 0, 0))
        for k in xrange(-8, 8):
          for l in xrange(-8, 8):
            img0.putpixel(anchor + (k, l), (255, 0, 0))

    if crop_region is None:
      fraction = 1.0
      final_width = img0.size[0]*fraction
      final_height = img0.size[1]*fraction
      crop_region = (0, 0, final_width, final_height)

    if final_size_mod is None and final_size is not None:
      final_width = float(crop_region[2] - crop_region[0])
      final_height = float(crop_region[3] - crop_region[1])
      ratio = min(final_size[0]/final_width, final_size[1]/final_height)
      final_size_mod = (int(round(final_width*ratio)),
                        int(round(final_height*ratio)))

    if sorted(trafo.keys()) == sorted(['alpha','x', 'y', 'theta', 'pad',
          'dims']):
      raise Exception('Not supported')
    elif sorted(trafo.keys()) == sorted(['a', 'b', 'dx', 'dy', 'pad', 'dims']):
      alpha = math.sqrt(trafo['a']**2 + trafo['b']**2)
      theta = math.atan2(trafo['b'], trafo['a'])
      dx = trafo['dx']
      dy = trafo['dy']

      # first scale
      img1 = img0.resize((int(round(alpha*_)) for _ in img0.size),
                          Image.ANTIALIAS)
      
      # next rotate, expanding as necessary
      img2 = img1.rotate(180.0*theta/math.pi, resample=Image.BICUBIC,
                         expand=True)

      # then we would need to shift by (dx, dy), plus some amount because we
      # rotate around center instead of corner
      # and crop around the center of the resulting image
      # that means that we need to crop around img2.size/2 - (dx, dy)

      # now crop
      c = math.cos(theta)
      s = math.sin(theta)
      rot_x = -img2.size[0]/2.0 + img1.size[0]/2.0*c + img1.size[1]/2.0*s
      rot_y = -img2.size[1]/2.0 + img1.size[1]/2.0*c - img1.size[0]/2.0*s
      corner_x = -dx - rot_x
      corner_y = -dy - rot_y
      crop_region_crt = (int(round(corner_x + crop_region[0])),
                         int(round(corner_y + crop_region[1])),
                         int(round(corner_x + crop_region[2])),
                         int(round(corner_y + crop_region[3])))
      img3 = img2.crop(crop_region_crt)

      if final_size_mod is not None:
        img4 = img3.resize(final_size_mod, Image.ANTIALIAS)
        img_final = Image.new(img4.mode, final_size)
        img_final.paste(img4, tuple(
            (img_final.size[_] - img4.size[_])/2 for _ in xrange(2)))
      else:
        img_final = img3
      
      # ...and finally save
      img_final.save(out_path)
    else:
      raise Exception("Unrecognized transformation parameters.");

    i += 1

if __name__ == "__main__":
  args = parse_command_line()
  files = list(args.files)
  files.sort()
  out_dir = (args.output if args.output is not None else
              os.path.dirname(files[0]))
  trafos = read_trafos(args.params)
  anchors = None if args.anchors is None else read_anchors(args.anchors)[1]

  if len(files) < len(trafos):
    print("WARNING: There are more transformations than files.")
    print("         Some transformations will be ignored.")

  if len(files) > len(trafos):
    print("WARNING: There are more files than transformations.")
    print("         Some files will be ignored.")
  
  transform(files, trafos, out_dir=out_dir, anchors=anchors,
            crop=None if args.crop is None else 
                  tuple(int(word) for word in args.crop.split(',')),
            final_size=tuple(int(word) for word in args.final_size.split(',')))
