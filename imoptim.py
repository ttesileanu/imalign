#! /usr/bin/env python2
from __future__ import print_function

import ast
import sys

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

def create_anchor_matrix(img_anchors):
  # create matrix with anchors as columns
  extend = lambda v: np.asarray(v + (1, ))
  return np.asarray([extend(_) for _ in img_anchors]).T

def get_best_trafo(img_anchors, target_anchors):
  proj = {'a': np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 0.0]]),
          'b': np.asarray([[0, 1, 0], [-1,0, 0], [0, 0, 0.0]]),
          'dx':np.asarray([[0, 0, 1], [0, 0, 0], [0, 0, 0.0]]),
          'dy':np.asarray([[0, 0, 0], [0, 0, 1], [0, 0, 0.0]])}
  params = proj.keys()
  w0 = np.asarray([[0, 0, 0], [0, 0, 0], [0, 0, 1.0]]);

  gamma = np.eye(img_anchors.shape[1]);
  gamma_mt = np.dot(gamma, img_anchors.T)
  m_gamma_mt = np.dot(img_anchors, gamma_mt)
  rhs_mat = np.dot(target_anchors - np.dot(w0, img_anchors), gamma_mt)
  
  n_params = len(params)
  eqmat = np.zeros((n_params, n_params))
  rhs = np.zeros(n_params)
  for i in xrange(n_params):
    e_i = proj[params[i]]
    rhs[i] = np.trace(np.dot(e_i.T, rhs_mat))
    for j in xrange(n_params):
      e_j = proj[params[j]]
      eqmat[i][j] = np.trace(np.dot(np.dot(e_i.T, e_j), m_gamma_mt))

  soln = np.linalg.solve(eqmat, rhs)
  m = w0
  for i in xrange(n_params):
    m += soln[i]*proj[params[i]]

  return ({_: soln[i] for (i, _) in enumerate(params)}, m)

if __name__ == "__main__":
  all_anchors = read_anchors(sys.argv[1])[1]

  target_anchor_matrix = create_anchor_matrix(all_anchors[0])
  trafos = [get_best_trafo(create_anchor_matrix(_), target_anchor_matrix)
            for _ in all_anchors]

  if len(sys.argv) >= 3 and sys.argv[2] in ['--processed', '-p']:
    # XXX final image size should ideally be configurable...
    pad_x = 1000.0
    pad_y = 1000.0
    width = 5000.0
    height = 7000.0

    w2 = width/2.0
    h2 = height/2.0
    
    for i, trafo in enumerate(trafos):
      a = trafo[0]['a']
      b = trafo[0]['b']
      alpha = np.sqrt(a**2 + b**2)
      dx = trafo[0]['dx']
      dy = trafo[0]['dy']
      
      new_dict = {}
      new_dict['alpha'] = alpha
      new_dict['theta'] = np.arctan2(b, a)
      
      new_dict['x'] = ((a*(dx + pad_x*(1-a)) - b*(dy + pad_y + pad_x*b))/alpha +
          w2*(1 - a/alpha) + h2*b/alpha)
      new_dict['y'] = ((a*(dy + pad_y*(1-a)) + b*(dx + pad_x - pad_y*b))/alpha +
          h2*(1 - a/alpha) - w2*b/alpha)
      
#      new_dict['x'] = (a*trafo[0]['dx'] - b*trafo[0]['dy']) / new_dict['alpha']
#      new_dict['y'] = (a*trafo[0]['dy'] + b*trafo[0]['dx']) / new_dict['alpha']
      trafos[i] = (new_dict, ) + trafo[1:]
    params = ['alpha', 'x', 'y', 'theta']

    print('# pad = {}, dims = {}'.format((pad_x, pad_y), (width, height)))
  else:  
    params = trafos[0][0].keys()
  
  print('\t'.join(params))
  for trafo in trafos:
    print('\t'.join(str(trafo[0][p]) for p in params))
