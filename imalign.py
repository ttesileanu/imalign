#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import argparse
import ast
import os

import Tkinter as tk
import tkMessageBox
from PIL import Image, ImageTk

from multiprocessing import Process, Pipe

import datetime

def parse_command_line():
  parser = argparse.ArgumentParser(
    description="Select anchors for aligning image set.",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
  parser.add_argument('files', type=str, nargs='+',
                      help="a file in the image set.")
  parser.add_argument('-o', '--output', default='img_anchors.txt',
                      help="where to store anchor positions")

  args = parser.parse_args()

  return args

def load_thumbs(files, thumb_pos, pipe_end):
  for i, f in enumerate(files):
    pos = thumb_pos[i]

    img0 = Image.open(f)
    img0.draft(img0.mode, pos[2:])
    img = img0.resize(pos[2:], resample=Image.LANCZOS)

    msg = {
      'i':      i,
      'pixels': img.tobytes(),
      'size':   img.size,
      'mode':   img.mode
    }
    pipe_end.send(msg)

def load_image(f, i, image_pos, pipe_end):
  img0 = Image.open(f)
  im_w = image_pos[2] - image_pos[0]
  im_h = image_pos[3] - image_pos[1]
  img0.draft(img0.mode, (im_w, im_h))
  img = img0.resize((im_w, im_h), resample=Image.LANCZOS)

  msg = {
    'i':      i,
    'pos':    image_pos,
    'pixels': img.tobytes(),
    'size':   img.size,
    'mode':   img.mode
  }
  pipe_end.send(msg)

class Tag(tk.Frame):
  def __init__(self, variable=None, value=None, master=None, text="anchor",
               close_btn=True, before_close=None):
    tk.Frame.__init__(self, master=master)

    self.radio = tk.Radiobutton(master=self, variable=variable, value=value)
    self.radio.pack(side=tk.LEFT)

    self.tag = tk.Entry(master=self)
    self.tag.pack(side=tk.LEFT)
    self.tag.insert(0, text)

    def key_callback(event):
      if event.char == '\r':
        self.focus_set()

    self.tag.bind("<Key>", key_callback)

    if close_btn:
      self.close_btn = tk.Button(master=self, text=u"×", 
          command=lambda f=before_close: self.close_fct(f))
      self.close_btn.pack(side=tk.LEFT)
    else:
      self.close_btn = None

  def close_fct(self, before_close=None):
    if before_close is not None:
      b = before_close(self)
      if b is not None and not b:
        # cancel close
        return
    self.destroy()

class TagFrame(tk.Frame):
  def __init__(self, *args, **kwargs):
    self.n_files = kwargs.pop('n_files')
    self.add_callback = kwargs.pop('add_callback', None)
    self.del_callback = kwargs.pop('del_callback', None)
    self.out_file = kwargs.pop('out_file', None)

    tk.Frame.__init__(self, *args, **kwargs)

    self.radio_variable = tk.IntVar(value=0)
    self.tags = []
#    self.tags = [Tag(master=self, variable=self.radio_variable,
#                     value=1, text="anchor #1", close_btn=False)]
#    self.tags[0].pack(side=tk.TOP, pady=(32, 0), anchor=tk.W)

#    self.anchors = [[None for _ in xrange(self.n_files)]]
    self.anchors = []

    self.save_btn = tk.Button(master=self, text="save", command=self.save_tags)
    self.save_btn.pack(side=tk.BOTTOM, anchor=tk.NW, pady=(0, 15))

    self.add_btn = tk.Button(master=self, text="add anchor",
                             command=self.add_tag)
    self.add_btn.pack(side=tk.BOTTOM, anchor=tk.NW, pady=(0, 30))

    self.pack_propagate(0)

    self.next_i = 1

  def save_tags(self):
    if self.out_file == None:
      return

    with open(self.out_file, 'wt') as f:
      for i, tag in enumerate(self.tags):
        if i > 0:
          f.write("\t")
        f.write(tag.tag.get())

      f.write("\n")

      for k in xrange(self.n_files):
        for i, anchor_list in enumerate(self.anchors):
          if i > 0:
            f.write("\t")
          f.write(str(anchor_list[k]))

        f.write("\n")
      
    print("Saved anchors to {}.".format(self.out_file))

  def add_tag(self, text=None):
#    value = len(self.tags) + 1
    value = self.next_i
    if text is None:
      text = "anchor #{}".format(self.next_i)

    def cleanup(to_delete):
      i0 = None
      value0 = None
      for i, tag in enumerate(self.tags):
        if tag is to_delete:
          i0 = i
          value0 = to_delete.radio.config('value')[-1]
          break

      if i0 is not None:
        if any(_ is not None for _ in self.anchors[i0]):
          if not tkMessageBox.askyesno("Delete tag",
              "Some images have anchors saved for this tag. Are you sure you " +
              "want to delete it?"):
            return False

        self.tags.pop(i0)
        self.anchors.pop(i0)

        if self.radio_variable.get() == value0:
          i = min(i0, len(self.tags)-1)
          self.radio_variable.set(self.tags[i].radio.config('value')[-1])

        if self.del_callback is not None:
          self.del_callback()

    self.tags.append(Tag(master=self, variable=self.radio_variable,
                         value=value, text=text, before_close=cleanup,
                         close_btn=(value > 1)))
    self.tags[-1].pack(side=tk.TOP, anchor=tk.W,
        pady=(32, 0) if value == 1 else 0)

    self.anchors.append([None for _ in xrange(self.n_files)])
    self.next_i += 1

    if value == 1:
      self.radio_variable.set(1)

    if self.add_callback is not None:
      self.add_callback()

  def get_selected_idx(self):
    value = self.radio_variable.get()
    for i, tag in enumerate(self.tags):
      if value == tag.radio.config('value')[-1]:
        return i

    return None

  def set_selected_idx(self, i):
    i -= 1
    if i >= 0 and i < len(self.tags):
      self.radio_variable.set(self.tags[i].radio.config('value')[-1])
#      self.radio_variable.set(i)
    
  def get_current_anchor(self, file_idx):
    i0 = self.get_selected_idx()
    if i0 is not None:
      return self.anchors[i0][file_idx]
    else:
      return None

  def update_current_anchor(self, file_idx, data):
    self.update_some_anchor(file_idx, self.get_selected_idx(), data)

  def update_some_anchor(self, file_idx, anchor_idx, data):
    if anchor_idx is not None:
      self.anchors[anchor_idx][file_idx] = data

class Anchorer(object):
  def __init__(self, files, out_file=None):
    # sort the files before displaying
    self.files = list(files)
    self.files.sort()

    self.out_file = out_file

    self.thumb_handles = [None for _ in self.files]
    self.rect_handles = [None for _ in self.files]

    self.root_width = 1200
    self.root_height = 700
    self.tags_width = 250

    self.thumb_height = 128
    self.max_thumb_width = 600
    self.thumb_title_size = 10

    self.thumb_spacing = 16
    self.thumb_loader = None

    self.check_thumb_alarm = None
    self.thumb_pipe = None

    self.main_rectangle = None
    self.main_image_handle = None
    self.main_rect_handle = None
    self.main_spacing = 8
    self.selected_i = -1
    self.main_loader = None
    self.check_image_alarm = None
    self.anchor_size = 5

    self.canvas_anchors = None
    self.anchor_colors = ['black', '#a00', '#00d', '#080', '#d80']

    self.load_image_data_()

  def init_anchors(self, anchor_names, anchors):
    if anchor_names is not None and anchors is not None:
      for name in anchor_names:
        self.tag_frame.add_tag(name)

      for i, anchors_per_img in enumerate(anchors):
        for j, anchor in enumerate(anchors_per_img):
          self.tag_frame.update_some_anchor(i, j, anchor)
    else:
      self.tag_frame.add_tag("anchor #1")

  def load_image_data_(self):
    sys.stdout.write("Loading image sizes and dates... ")
    sys.stdout.flush()
    self.img_sizes = []
    self.img_dates = []
    for file in self.files:
      im = Image.open(file)
      self.img_sizes.append(im.size)
      date0 = datetime.datetime.strptime(im._getexif()[36867],
                                         '%Y:%m:%d %H:%M:%S')
      # for calculating time differences, set all datetimes to midnight
      # but set any time before 6am as referring to previous day
      date = date0.replace(hour=0, minute=0, second=0)
      if date0.hour < 6:
        date = date - datetime.timedelta(days=1)
      self.img_dates.append(date)
    sys.stdout.write("done.\n")
    sys.stdout.flush()

  def draw_placeholders_(self):
    x = self.thumb_spacing
    y_title = self.thumb_spacing
    y = int(y_title + 1.5*self.thumb_title_size)
    self.thumb_pos = []
    for i, size in enumerate(self.img_sizes):
      thumb_height = self.thumb_height
      thumb_width = int(float(size[0])*thumb_height/size[1])
      if thumb_width > self.max_thumb_width:
        thumb_width = self.max_thumb_width
        thumb_height = int(float(size[1])*thumb_width/size[0])

      if self.rect_handles[i] is not None:
        self.thumbnails.delete(self.rect_handles[i])
      self.rect_handles[i] = self.thumbnails.create_rectangle(
          (x-1, y-1, x+thumb_width, y+thumb_height))
      self.thumb_pos.append((x, y, thumb_width, thumb_height))

      # create title
      day = (self.img_dates[i] - self.img_dates[0]).days + 1
      title = "{}. Day {}".format(i+1, day)
      self.thumbnails.create_text((x + thumb_width/2, y_title),
                                  text=title,
                                  font=('Helvetica', self.thumb_title_size),
                                  anchor=tk.N)
      
      x = x + thumb_width + self.thumb_spacing

  def finalize_(self):
    if self.thumb_loader is not None and self.thumb_loader.is_alive():
      self.thumb_loader.terminate()

  def del_win_handler_(self):
    self.finalize_()
    self.root.destroy()

  def check_new_thumb_(self):
    if self.thumb_pipe is not None:
      if self.thumb_pipe[0].poll():
        img_src = self.thumb_pipe[0].recv()
        img0 = Image.frombytes(img_src['mode'], img_src['size'],
                               img_src['pixels'])

        i = img_src['i']
        self.thumb_handles[i] = ImageTk.PhotoImage(img0)

        pos = self.thumb_pos[i]
        self.thumbnails.create_image(pos[0], pos[1], anchor=tk.NW,
                                 image=self.thumb_handles[i])
        self.root.update_idletasks()

    # stop checking once all images have been loaded
    if any(_ == None for _ in self.thumb_handles):
      self.check_thumb_alarm = self.root.after(100, self.check_new_thumb_)
    else:
      print("Finished loading thumbnails.")

  def check_image_ready_(self):
    if self.image_pipe is not None:
      if self.image_pipe[0].poll():
        img_src = self.image_pipe[0].recv()
        img0 = Image.frombytes(img_src['mode'], img_src['size'],
                               img_src['pixels'])

        i = img_src['i']
        self.main_image_handle = ImageTk.PhotoImage(img0)

        pos = img_src['pos']
        self.main_canvas.create_image(pos[0], pos[1], anchor=tk.NW,
                                      image=self.main_image_handle)
        self.root.update_idletasks()
        print("Finished loading image {} ({})".format(i+1, self.files[i]))

        self.add_anchors()
        return

    self.check_image_alarm = self.root.after(100, self.check_image_ready_)

  def update_main_rectangle_(self, i):
    if self.selected_i == i and self.main_rect_handle is not None:
      return

    if self.main_loader is not None:
      self.main_loader.terminate()

    if self.check_image_alarm is not None:
      self.root.after_cancel(self.check_image_alarm)
    self.check_image_alarm = self.root.after(100, self.check_image_ready_)

    self.selected_i = i
    img_width, img_height = self.img_sizes[self.selected_i]
    ratio = min(float(self.main_canvas_width - self.main_spacing)/img_width,
                float(self.main_canvas_height - self.main_spacing)/img_height)

    disp_width = int(img_width*ratio)
    disp_height = int(img_height*ratio)

    self.main_rectangle = (
        (self.main_canvas_width - disp_width)/2,
        (self.main_canvas_height - disp_height)/2,
        (self.main_canvas_width + disp_width)/2,
        (self.main_canvas_height + disp_height)/2)

    self.delete_anchors()
    if self.main_image_handle is not None:
      self.main_canvas.delete(self.main_image_handle)
      self.main_image_handle = None
            
    print("Starting loading file {} ({}).".format(i+1, self.files[i]))
    self.image_pipe = Pipe()
    self.main_loader = Process(
        target=load_image, args=(self.files[i], i, self.main_rectangle,
        self.image_pipe[1]))
    self.main_loader.start()

    if self.main_rect_handle is not None:
      self.main_canvas.delete(self.main_rect_handle)
      self.main_rect_handle = None

    rect = (self.main_rectangle[0]-1, self.main_rectangle[1]-1,
            self.main_rectangle[2], self.main_rectangle[3])
    self.main_rect_handle = self.main_canvas.create_rectangle(rect)

    day = (self.img_dates[i] - self.img_dates[0]).days + 1
    title = "{}. Day {}".format(i+1, day)
    self.root.title("image aligner ({}, {})".format(
        title, os.path.basename(self.files[self.selected_i])))

  def thumbnail_click_callback_(self, event):
    self.main_canvas.focus_set()
    cx = self.thumbnails.canvasx(event.x)
    cy = self.thumbnails.canvasy(event.y)
    # XXX this is inefficient, but perhaps we don't care
    clicked_on = None
    for i, pos in enumerate(self.thumb_pos):
      if (cx >= pos[0] and cy >= pos[1] and
         cx - pos[0] < pos[2] and cy - pos[1] < pos[3]):
        clicked_on = i
        break

    if clicked_on is not None:
      self.update_main_rectangle_(i)

  def main_click_callback_(self, event):
    event.widget.focus_set()
    cx = self.main_canvas.canvasx(event.x)
    cy = self.main_canvas.canvasy(event.y)

    if self.main_image_handle is None or self.selected_i is None:
      return    # image not loaded yet

    if (cx < self.main_rectangle[0] or cy < self.main_rectangle[1] or
        cx >= self.main_rectangle[2] or cy >= self.main_rectangle[3]):
      return    # click outside image

    # convert to image coordinates
    im_w, im_h = self.img_sizes[self.selected_i]
    rect_w = self.main_rectangle[2] - self.main_rectangle[0]
    rect_h = self.main_rectangle[3] - self.main_rectangle[1]
    x = int(float(cx - self.main_rectangle[0])*im_w/rect_w)
    y = int(float(cy - self.main_rectangle[1])*im_h/rect_h)

    # draw anchor on screen
    selected_anchor_idx = self.tag_frame.get_selected_idx()
    self.update_anchor(self.tag_frame.get_selected_idx(), x, y)

    self.tag_frame.update_current_anchor(self.selected_i, (x, y))

  def update_anchor(self, i0, x, y):
    # convert to canvas coordinates
    im_w, im_h = self.img_sizes[self.selected_i]
    rect_w = self.main_rectangle[2] - self.main_rectangle[0]
    rect_h = self.main_rectangle[3] - self.main_rectangle[1]
    cx = self.main_rectangle[0] + int(float(x)*rect_w/im_w)
    cy = self.main_rectangle[1] + int(float(y)*rect_h/im_h)

    # check if this anchor already exists
    if self.canvas_anchors is None:
      self.canvas_anchors = [None for _ in self.tag_frame.anchors]

    if self.canvas_anchors[i0] is not None:
      if self.canvas_anchors[i0][:2] == (cx, cy):
        # anchor is already in the right place
        return
      else:
        # delete old anchor
        for h in self.canvas_anchors[i0][2:]:
          self.main_canvas.delete(h)

    # draw anchor, store line handles
    color = self.anchor_colors[i0 % len(self.anchor_colors)]
    h1a = self.main_canvas.create_line(
      cx - self.anchor_size, cy - self.anchor_size,
      cx + self.anchor_size + 1, cy + self.anchor_size + 1,
      fill='white', width=2)
    h1 = self.main_canvas.create_line(
      cx - self.anchor_size, cy - self.anchor_size,
      cx + self.anchor_size, cy + self.anchor_size,
      fill=color)
    h2a = self.main_canvas.create_line(
      cx + self.anchor_size + 1, cy - self.anchor_size,
      cx - self.anchor_size, cy + 1 + self.anchor_size,
      fill='white', width=2)
    h2 = self.main_canvas.create_line(
      cx + self.anchor_size, cy - self.anchor_size,
      cx - self.anchor_size, cy + self.anchor_size,
      fill=color)

    self.canvas_anchors[i0] = (cx, cy, h1, h2, h1a, h2a)

  def delete_anchors(self):
    if self.canvas_anchors is not None:
      for anchor in self.canvas_anchors:
        if anchor is not None:
          for h in anchor[2:]:
            self.main_canvas.delete(h)

    self.canvas_anchors = None

  def add_anchors(self):
    for i, anchor_list in enumerate(self.tag_frame.anchors):
      anchor = anchor_list[self.selected_i]
      if anchor is not None:
        self.update_anchor(i, *anchor)

  def add_anchor_callback(self):
    self.delete_anchors()
    self.add_anchors()

  def del_anchor_callback(self):
    self.delete_anchors()
    self.add_anchors()

  def setup(self):
    root = tk.Tk(className="Image aligner")
    self.root = root
    root.config(bg="white")

    self.top_frame = tk.Frame()
    self.bottom_frame = tk.Frame()

    self.top_frame.pack(side=tk.TOP)
    self.bottom_frame.pack(side=tk.TOP)

    # create thumbnail slider
    self.xscrollbar = tk.Scrollbar(self.bottom_frame, orient=tk.HORIZONTAL)
    self.xscrollbar.pack(side=tk.BOTTOM, fill=tk.X)

    self.thumb_slider_height = (self.thumb_height + self.thumb_spacing/2 +
        self.thumb_title_size)
    self.thumbnails = tk.Canvas(self.bottom_frame, width=self.root_width,
        height=self.thumb_slider_height, xscrollcommand=self.xscrollbar.set)
    self.thumbnails.pack(side=tk.TOP)
    self.xscrollbar.config(command=self.thumbnails.xview)

    self.draw_placeholders_()

    # XXX on Win: divide by 120; or just use the sign on both Mac&Win
    # XXX on Linux: bind to <Button-4> and <Button-5>, and divide or use sign
    def on_mousewheel_x(event):
      dx = -event.delta
      self.thumbnails.xview_scroll(int(dx), "units")

    self.thumbnails.config(scrollregion=self.thumbnails.bbox(tk.ALL))
    root.bind_all("<Shift-MouseWheel>", on_mousewheel_x)

    # start loading thumbnails in the background
    self.check_thumb_alarm = self.root.after(100, self.check_new_thumb_)

    root.protocol("WM_DELETE_WINDOW", self.del_win_handler_)

    self.thumb_pipe = Pipe()
    self.thumb_loader = Process(target=load_thumbs, args=(self.files,
                                    self.thumb_pos, self.thumb_pipe[1]))
    print("Starting to load thumbnails.")
    self.thumb_loader.start()

    # create picture canvas
    self.main_canvas_width = self.root_width - self.tags_width
    self.main_canvas_height = self.root_height - self.thumb_slider_height
    self.main_canvas = tk.Canvas(self.top_frame, width=self.main_canvas_width,
        height=self.main_canvas_height, highlightthickness=0)
    self.main_canvas.pack(side=tk.LEFT)

    self.update_main_rectangle_(0)

    self.thumbnails.bind("<Button-1>", self.thumbnail_click_callback_)
    self.main_canvas.bind("<Button-1>", self.main_click_callback_)

    # create tag text entries
    self.tag_frame = TagFrame(master=self.top_frame,
        height=self.main_canvas_height, width=self.tags_width,
        n_files=len(self.files), add_callback=self.add_anchor_callback,
        del_callback=self.del_anchor_callback, out_file=self.out_file)
    self.tag_frame.pack(side=tk.LEFT, fill=tk.BOTH)

    def key_callback(event):
      if not isinstance(event.widget, tk.Entry):
        if event.char >= '0' and event.char <= '9':
          self.tag_frame.set_selected_idx(ord(event.char) - ord('0'))
#        print("pressed", repr(event.char))

    self.root.bind("<Key>", key_callback)

  def run(self):
    tk.mainloop()

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

if __name__ == "__main__":
  args = parse_command_line()
  files = args.files

  app = Anchorer(args.files, out_file=args.output)
  app.setup()
  app.init_anchors(*read_anchors(args.output))
  app.run()
