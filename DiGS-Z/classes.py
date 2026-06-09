'''
DiGS-Z is a Python GUI application for data acquisition using a diffraction grating spectrometer with ZWO ASI cameras.
Copyright (C) 2026 Collin Tower

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Additional Permission: This program is permitted to link against the 
proprietary ZWO ASI Camera SDK as specified in the repository's LICENSE file.
'''

#gui
import tkinter as tk
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox

#image manipulation
import PIL,PIL.Image,PIL.ImageTk,PIL.ImageOps
import cv2

#data manipulation
import numpy as np
import copy

#graphing
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk) #NavigationToolbar2Tk or NavigationToolbar2TkAgg
import matplotlib.backends.backend_tkagg as tkagg

#threading
import threading
import time

#ZWO ASI python binding
import zwoasi

####################
# Thread decorator #
####################
def threaded(fn):
	def wrapper(*args, **kwargs):
		thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
		thread.start()
		return thread
	return wrapper

		
class ScrollableFrame(ttk.Frame):
	def __init__(self,parent):
		super().__init__(parent) #parent get passed to inherit class  (ie ttk.Frame)
		# Create a canvas and a vertical scrollbar
		self.canvas = tk.Canvas(self)
		scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
		# Create an interior frame that will hold the content
		self.scrollable_frame = ttk.Frame(self.canvas)

		# Bind the Configure event of the interior frame to update the scroll region
		self.scrollable_frame.bind(
			"<Configure>",
			lambda e: self.canvas.configure(
				scrollregion=self.canvas.bbox("all"),
				width=self.scrollable_frame.winfo_width()
			)
		)

		# Add the interior frame to the canvas using create_window
		self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

		# Configure the canvas to use the scrollbar
		self.canvas.configure(yscrollcommand=scrollbar.set)

		# Pack the canvas and scrollbar into the ScrollableFrame
		self.canvas.pack(side="left", fill="both", expand=True)
		scrollbar.pack(side="right", fill="y")

		self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

	def on_mousewheel(self,event):
	    if event.delta > 0:
	        self.canvas.yview_scroll(-1, "units")
	    else:
	        self.canvas.yview_scroll(1, "units")

class RoiCanvas(ttk.Frame):
	def __init__(self,parent,controller,linked_graph = None):
		super().__init__(parent) #parent gets passes to ttk.Frame
		self.parent = parent #where roi frame will be placed
		self.controller = controller #main window where variables are stored
		self.linked_graph = linked_graph

		self.img_tkinter = None # needed for pythons garbage collection
		self.start_x = None
		self.start_y = None
		self.canvas_rectangle = None

		self.canvas = tk.Canvas(self)
		self.canvas.pack(fill = "both", expand = True)
		self.image_container = self.canvas.create_image(0,0,anchor="nw")
		self.canvas.bind('<Configure>', lambda e: [self.canvas_update(controller.ccd_bitmap),
												   self.roi_rectangle_update(controller.canvas_rectangle_coords,controller.ccd_bitmap)])        
		self.canvas.bind("<ButtonPress-1>",lambda event: self.on_click_canvas(event))
		self.canvas.bind("<B1-Motion>", lambda event: self.on_move_canvas(event))
		self.canvas.bind("<ButtonRelease-1>", lambda event: self.on_click_release_canvas(controller,event,controller.ccd_bitmap))

	def canvas_update(self,ccd_bitmap):
		self.canvas.update_idletasks()
		canvas_width, canvas_height = self.canvas.winfo_width(),self.canvas.winfo_height()

		#account for bitmap having negative values (for ex: after background subtraction)
		#shift the bitmap values up until they are positive
		img = ccd_bitmap.copy()
		img = cv2.resize(img, (canvas_width, canvas_height),interpolation = cv2.INTER_AREA)
		img = img.astype(np.float32)
		min_img = np.min(img)

		#print(f"min max {np.min(img)}  {np.max(img)}")
		#nested if statements to avoid copying large bitmap
		#if min_img < 0:
		img -= min_img
		#print(f"min = {np.min(img)}")
		if self.controller.roi_set_frame.log_ccd_var.get() == 1:
			img = np.log(img + 1)
			#print(f"min max {np.min(img)}  {np.max(img)}")

		self.img_tkinter = PIL.Image.fromarray(255 * (img / np.max(img)))
		#print(f"min max {np.min(255 * (img / np.max(img)))}  {np.max(255 * (img / np.max(img)))}")
		self.img_tkinter = PIL.ImageTk.PhotoImage(self.img_tkinter)

		#self.canvas.image = img_tkinter # needed for pythons garbage collection
		self.canvas.itemconfig(self.image_container,image=self.img_tkinter)

	def on_click_canvas(self,event):
		self.canvas.delete("rectangle")
		# save mouse drag start position
		self.start_x = event.x
		self.start_y = event.y
		#print(f"start x: {self.start_x}, start y:{self.start_y}")

		self.canvas_rectangle = self.canvas.create_rectangle(0, 0, 1, 1,outline='red', width=3 ,tags="rectangle")

	def on_move_canvas(self,event):
		curX, curY = (event.x, event.y)

		# expand rectangle as you drag the mouse
		self.canvas.coords(self.canvas_rectangle, self.start_x, self.start_y, curX, curY)

	def on_click_release_canvas(self,controller,event,ccd_bitmap):
		#make rectange fill the whole width

		end_x = event.x
		end_y = event.y

		canvas_width = self.canvas.winfo_width()
		canvas_height = self.canvas.winfo_height()
		bitmap_width = np.shape(ccd_bitmap)[1]
		bitmap_height = np.shape(ccd_bitmap)[0]

		scale_y = bitmap_height / canvas_height

		if end_x != self.start_x:
			self.canvas.coords(self.canvas_rectangle, 0, self.start_y, canvas_width, end_y)
			controller.canvas_rectangle_coords[0] = min(int(self.start_y*scale_y), int(end_y*scale_y))
			controller.canvas_rectangle_coords[1] = max(int(self.start_y*scale_y), int(end_y*scale_y))
			if type(self.linked_graph) != type(None):
				self.linked_graph.plot_bin(controller,
											controller.ccd_bitmap[controller.canvas_rectangle_coords[0]:controller.canvas_rectangle_coords[1]])
			# print(Variables.canvas_rectangle_coords)
			# img = cv2.resize(Variables.bitmap[Variables.canvas_rectangle_coords[0]:Variables.canvas_rectangle_coords[1]], (canvas_width, abs( widget.end_y-widget.start_y)),interpolation = cv2.INTER_AREA)
			# img = PIL.Image.fromarray(255 * (img / np.max(img)))
			# img.show()

			#set 
			roi_center = float( (controller.canvas_rectangle_coords[0] + controller.canvas_rectangle_coords[1]) / 2 )
			roi_height = (controller.canvas_rectangle_coords[1] - controller.canvas_rectangle_coords[0] )
			self.controller.roi_set_frame.center_label.configure(text=str(roi_center))
			self.controller.roi_set_frame.height_label.configure(text=str(roi_height))
			#print("roi_canvas =",controller.canvas_rectangle_coords[0],controller.canvas_rectangle_coords[1] )

		else:
			#Variables.canvas_rectangle_coords = [0,Variables.bitmap]
			self.canvas.coords(self.canvas_rectangle, 0, 0, canvas_width, canvas_height)
			controller.canvas_rectangle_coords[0] = 0
			controller.canvas_rectangle_coords[1] = bitmap_height
			if type(self.linked_graph) != type(None):
				self.linked_graph.plot_bin(controller,
											controller.ccd_bitmap[controller.canvas_rectangle_coords[0]:controller.canvas_rectangle_coords[1]])
			# print(Variables.canvas_rectangle_coords)

			roi_center = float( (controller.canvas_rectangle_coords[0] + controller.canvas_rectangle_coords[1]) / 2 )
			roi_height = (controller.canvas_rectangle_coords[1] - controller.canvas_rectangle_coords[0] )
			self.controller.roi_set_frame.center_label.configure(text=str(roi_center))
			self.controller.roi_set_frame.height_label.configure(text=str(roi_height))
			#print("roi_canvas =",controller.canvas_rectangle_coords[0],controller.canvas_rectangle_coords[1] )

	def roi_rectangle_update(self,canvas_rectangle_coords,ccd_bitmap):
		self.canvas.delete("rectangle")
		if type(canvas_rectangle_coords[0]) != type(None):
			canvas_width = self.canvas.winfo_width()
			canvas_height = self.canvas.winfo_height()
			bitmap_width = np.shape(ccd_bitmap)[1]
			bitmap_height = np.shape(ccd_bitmap)[0]
			scale_y = canvas_height / bitmap_height
			
			self.canvas_rectangle = self.canvas.create_rectangle(0, int(canvas_rectangle_coords[0]*scale_y), canvas_width,  int(canvas_rectangle_coords[1]*scale_y)
				,outline='red', width=3 ,tags="rectangle")

class GraphCanvas(ttk.Frame):
	def __init__(self,parent,controller):
		super().__init__(parent)

		self.controller = controller

		self.spectra_figure = Figure(tight_layout=True) 
		self.ax = self.spectra_figure.add_subplot(1,1,1)
		self.ax.set_ylabel("y",fontsize=15)
		self.ax.set_xlabel("x",fontsize=15)
		self.ax.grid(visible=True)
		#self.spectra_figure.tight_layout()
		graph_frame = tk.LabelFrame(self, text="")
		graph_frame.grid(row=0,column=0,sticky="NEWS")
		self.graph_canvas = FigureCanvasTkAgg(self.spectra_figure, graph_frame)
		self.graph_canvas.get_tk_widget().pack(expand = True, fill ="both")

		toolbar_frame = tk.LabelFrame(self, text="")
		toolbar_frame.grid(row=1,column=0,sticky="NEWS")
		#home_button = tk.Button(toolbar_frame,text="AH",command=self.auto_home)
		#home_button.pack(side="left")
		#toolbar = tkagg.NavigationToolbar2Tk(self.graph_canvas, toolbar_frame,pack_toolbar=False)
		toolbar = CustomToolbar(self.graph_canvas, toolbar_frame,self)
		toolbar.update()
		toolbar.pack(expand = True, fill ="both")

		#get position on graph
		self.spectra_figure.canvas.mpl_connect('button_press_event', self.on_click)

	def plot(self,x,y,colour):
		markersize = 5

		for item in list(self.ax.lines):
			item.remove()

		if type(x) == type(None):
			self.ax.plot(y,colour,markersize=markersize)
		else:
			self.ax.plot(x,y,colour, markersize=markersize)

		self.graph_canvas.draw_idle()


	def plot_bin(self,controller,ccd_bitmap):
		ccd_bitmap = ccd_bitmap.astype(np.float64)
		spectra = np.sum(ccd_bitmap, axis=0)

		controller.y = spectra /  np.shape(ccd_bitmap)[0]

		self.plot(controller.x,controller.y,"r-")
		self.auto_home()

	def auto_home(self):
			self.ax.relim() 
			self.ax.autoscale()
			self.graph_canvas.draw_idle()

	def on_click(self,event):

		if self.controller.calibration_window is not None:

			if self.controller.calibration_window.winfo_exists() and event.dblclick:
				radio_button_number = self.controller.calibration_frame.peaks_radiobutton_var.get()
				self.controller.calibration_frame.data_peaks_entry_list[radio_button_number].set(str(event.xdata))
				self.controller.calibration_window.lift()

class CustomToolbar(tkagg.NavigationToolbar2Tk): #fix default home button not updating xlim,ylim
	def __init__(self,canvas,frame,graph_class):
		super().__init__(canvas,frame)
		self.graph_class = graph_class

	def home(self): #change default home button
		GraphCanvas.auto_home(self.graph_class)

class Bitmap:
	def __init__(self, filename=None, controller=None):
		self.filename = filename
		self.controller = controller

	def uint16_header_read(self):
		#get image size from header

		f = open(self.filename,"rb")
		magic = f.readline().decode().strip().split("=")[-1]
		width = int(f.readline().decode().strip().split("=")[-1])
		height = int(f.readline().decode().strip().split("=")[-1])

		#removes header from image
		header_break = False
		while header_break == False:
			line = f.readline() 
			if not line:
				break
			elif "HeaderEnd" in line.decode():
				break

		bitmap = np.fromfile(f, dtype=np.uint16)
		#bitmap = np.fromfile(f, dtype=np.float64)
		bitmap = bitmap.reshape((height,width))
		f.close()

		return bitmap

	def open_bitmap(self,bitmap_select): #bitmap_select = "ccd_bitmap" or "ccd_bitmap_background"
		file_path = filedialog.askopenfilename(title="Select a file",
											   filetypes=(("image files:", "*.raw *.png"),("Raw:", "*.raw"), ("png:", "*.png"))
											   )

		file_type = file_path.split(".")[-1]
		self.filename = file_path
		print(file_path,file_type)

		try:

			if file_type.lower() == "raw":
				bitmap = self.uint16_header_read()
			elif file_type.lower() == "png":

				img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
				if len(img.shape) > 2:
					img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE) 

				bitmap = img

			if bitmap_select == "ccd_bitmap":
				self.controller.ccd_bitmap = bitmap
			elif bitmap_select == "ccd_bitmap_background":
				self.controller.ccd_bitmap_background = bitmap

				#subtract the background from currently loaded bitmap
				if self.controller.ccd_bitmap is not None:
					ccd_width = np.shape(self.controller.ccd_bitmap)[1]
					ccd_height = np.shape(self.controller.ccd_bitmap)[0]
					background_width = np.shape(self.controller.ccd_bitmap_background)[1]
					background_height = np.shape(self.controller.ccd_bitmap_background)[0]

					if (ccd_width == background_width) and (ccd_height == background_height):
						self.controller.ccd_bitmap = (self.controller.ccd_bitmap.astype(np.float64))-self.controller.ccd_bitmap_background


			#reset roi
			self.controller.canvas_rectangle_coords[0], self.controller.canvas_rectangle_coords[1] = None,None
			self.controller.canvas_graph_update()

		except:
			messagebox.showwarning("Image Read Error!", "Count not read image.")

	def save_bitmap(self,bitmap,camera=None):
		if bitmap is None:
			messagebox.showinfo("", "No bitmap to save.")
			return
		else:
			img = bitmap.copy()

		#make sure img does not exceed uint16 
		min_bitmap = np.min(img)

		if min_bitmap < 0:
			print("bitmap values < 0")
			img -= min_bitmap

		max_bitmap = np.max(img)

		if max_bitmap > ((2**16) - 1): 
			print("bitmap values > 2^16 - 1")
			img *= (((2**16) - 1) / max_bitmap)

		img = img.astype(dtype = np.uint16)
		#img = img.astype(dtype = np.float16) #max representable int only 2048
		#img = img.astype(dtype = np.float32) #max representable int 16,777,216 

		bitmap_width = np.shape(bitmap)[1]
		bitmap_height = np.shape(bitmap)[0]

		save_name = filedialog.asksaveasfilename(
	    											title="Save File",
	   												defaultextension=".raw",
	    											filetypes=(("image files:", "*.raw *.png"),("Raw:", "*.raw"), ("png:", "*.png"))
	    											)
		file_type = save_name.split(".")[-1]
		
		if file_type.lower() == "raw":
			binary_array = img.reshape(-1)
			#print(binary_array)

			file = open(save_name, "wb")

			#create custom header
			header = "Magic=raw\n"
			header += f"Width={bitmap_width}\n"
			header += f"Height={bitmap_height}\n"
			#header += f"ByteOrder=C\n"
			#header += f"BitDepth=16\n"
			if camera is not None:
				try:
					camera_info = camera.get_camera_property()
					camera_name = camera_info["Name"]
					camera_bin = camera.get_roi_format()[2]
					
					header += "[Settings]\n"
					header +=f"CameraName={camera_name}\n"
					header +=f"PixelBin={camera_bin}\n"

					if self.controller is not None:
						exposure_time = self.controller.image_take_frame.exposure_entry_var.get()
						average = self.controller.image_take_frame.average_entry_var.get()
						gain = self.controller.image_take_frame.gain_entry_var.get()

						header +=f"ExposureSeconds={exposure_time}\n"
						header +=f"Average={average}\n"
						header +=f"Gain={gain}\n"
				except:
					pass
			header +="HeaderEnd\n"

			file.write(header.encode("ascii"))
			file.write(binary_array.tobytes())
			file.close()

		elif file_type.lower() == "png":
			#print(img)
			
			cv2.imwrite(save_name, img)

		#print(max_bitmap,min_bitmap)
		#print(img.dtype)

class CameraSelect(ttk.LabelFrame):
	def __init__(self,parent,controller,text):
		super().__init__(parent,text=text)

		self.controller = controller
		self.camera_list = ["Select a Camera"]

		#dropdown
		self.camera_select_frame = ttk.Frame(self)
		self.camera_select_frame.grid(row=0,column=0,sticky="news")

		camera_select_label = ttk.Label(self.camera_select_frame,text="camera: ")
		camera_select_label.grid(row=0,column=0,sticky="ew")

		self.camera_dropdown_var = tk.StringVar(value=self.camera_list[0])
		self.camera_dropdown = ttk.OptionMenu(self.camera_select_frame, self.camera_dropdown_var, *self.camera_list,
										 command=lambda camera_name: self.camera_select(camera_name) )
		self.camera_dropdown.grid(row=0,column=1,sticky="ew")
		self.camera_dropdown.config(width=15)

		camera_list_refresh_button = ttk.Button(self.camera_select_frame, text="refresh",command = self.refresh_camera_list)
		camera_list_refresh_button.grid(row=0,column=2,sticky="ew")

		#status
		camera_status_frame = ttk.Frame(self)
		camera_status_frame.grid(row=1,column=0,sticky="news")

		camera_status_label_static = ttk.Label(camera_status_frame,text="Camera Status: ")
		camera_status_label_static.grid(row=0,column=0, sticky = 'w')
		self.camera_status_label = ttk.Label(camera_status_frame,text="disconnected",foreground="red")
		self.camera_status_label.grid(row=0,column=1, sticky = 'w')

		self.refresh_camera_list()

	def camera_select(self,camera_name):
		if camera_name in zwoasi.list_cameras():
			#do not reconnect to connected camera
			if (self.controller.camera is not None) and (camera_name == self.controller.camera.get_camera_property()["Name"]):
				print("camera already connected")
				return

			camera_id = zwoasi.list_cameras().index(camera_name)

			#try to connect camera
			try:
				selected_camera = zwoasi.Camera(camera_id)

			except:
				print("could not connect")
				return

			self.camera_status_label.configure(text="connected",foreground="green")

			#get camera info and try to set pixel binning to 1 and set mode to 16 bit
			camera_info = selected_camera.get_camera_property()
			supported_bins = camera_info["SupportedBins"]
			ccd_width = camera_info["MaxWidth"]
			ccd_height = camera_info["MaxHeight"]

			if 1 in supported_bins:
				camera_bin = 1
			else:
				camera_bin = selected_camera.get_roi_format()[2] #use the default pixel bining

			selected_camera.set_roi_format(ccd_width, ccd_height, camera_bin, zwoasi.ASI_IMG_RAW16)
			print(f"camera info: name={camera_name} width={ccd_width} height={ccd_height} bin={camera_bin}")
			#set camera for main frame
			self.controller.camera = selected_camera

			#print(selected_camera.get_roi_format())
			'''
			-bin setting info
			number of pixels to bin together ie: if bin = 2 each pixel in bitmap is a 2x2 block of actual ccd pixels 
			grouped together this program tries to force bin = 1 so each pixel of the ccd is returned
			'''
			
	def refresh_camera_list(self):
		self.controller.camera = None
		self.camera_status_label.configure(text="disconnected",foreground="red")
		number_of_cameras = zwoasi.get_num_cameras()

		if number_of_cameras == 0:
			self.camera_list = ["Select a Camera","no cameras found"]
		else:
			self.camera_list = ["Select a Camera"]
			self.camera_list.extend(zwoasi.list_cameras())

		#have to recreate dropdown or it does not update

		self.camera_dropdown_var = tk.StringVar(value=self.camera_list[0])
		self.camera_dropdown = ttk.OptionMenu(self.camera_select_frame, self.camera_dropdown_var, *self.camera_list,
										 command=lambda camera_name: self.camera_select(camera_name) )
		self.camera_dropdown.grid(row=0,column=1,sticky="ew")
		self.camera_dropdown.config(width=15) 

class ImageTake(ttk.LabelFrame):
	def __init__(self,parent,controller,label_frame_text=""):
		super().__init__(parent,text=label_frame_text)

		self.controller = controller

		self.save_file_name = None

		#image thread started (starts set ie true because the .wait() command waits until event returns true)
		# ie: if event flag is true thread is not running
		self.image_thread_event = threading.Event()
		self.image_thread_event.set()

		self.cosmic_ray_thread_event = threading.Event()
		self.cosmic_ray_thread_event.set()
		self.cosmic_ray_array = None

		#set up progress bar threading
		self.progress_bar_thread_event = threading.Event()
		self.progress_bar_thread_event.set()
		self.progress_bar_thread = None

		entry_frame = ttk.Frame(self)
		entry_frame.grid(row=0,column=0,sticky="news")

		#exposure settings
		exposure_label = ttk.Label(entry_frame,text = "exp (s): ")
		exposure_label.grid(row=0,column=0,sticky="w")

		self.exposure_entry_var = tk.StringVar(value="1")
		exposure_entry = ttk.Entry(entry_frame,width=10,textvariable=self.exposure_entry_var)
		exposure_entry.grid(row=0,column=1,sticky="w")

		#average settings
		average_label = ttk.Label(entry_frame,text = "average: ")
		average_label.grid(row=1,column=0,sticky="w")

		self.average_entry_var = tk.StringVar(value="1")
		average_entry = ttk.Entry(entry_frame,width=10,textvariable=self.average_entry_var)
		average_entry.grid(row=1,column=1,sticky="w")

		#gain settings
		gain_label = ttk.Label(entry_frame,text = "gain: ")
		gain_label.grid(row=2,column=0,sticky="w")

		self.gain_entry_var = tk.StringVar(value="100")
		gain_entry = ttk.Entry(entry_frame,width=10,textvariable=self.gain_entry_var)
		gain_entry.grid(row=2,column=1,sticky="w")

		#buttons
		button_frame = ttk.Frame(self)
		button_frame.grid(row=1,column=0,pady = 10,sticky="news")

		run_button = ttk.Button(button_frame, text="run",command = self.run)
		run_button.grid(row=0,column=0)

		run_continuous_button = ttk.Button(button_frame, text="run continuous",command = self.run_continuous)
		run_continuous_button.grid(row=0,column=1)

		run_save_button = ttk.Button(button_frame, text="run/save",command = self.run_save)
		run_save_button.grid(row=0,column=2)

		take_background_button = ttk.Button(button_frame, text="take bg",command = self.take_background)
		take_background_button.grid(row=1,column=0,sticky="news")

		undo_background_button = ttk.Button(button_frame, text="undo bg",command = self.undo_background)
		undo_background_button.grid(row=1,column=1,sticky="news")

		stop_button = ttk.Button(button_frame, text="stop",command = self.stop)
		stop_button.grid(row=2,column=0,pady=5,sticky="news")

		#get list of buttons excluding the the stop button for enabling and disabling buttons while scannings
		self.image_buttons_list = []
		for widget in button_frame.winfo_children():
			if isinstance(widget, ttk.Button) and (widget.cget("text") != "stop"):
				self.image_buttons_list.append(widget)

		#progress labels
		progress_label_frame = ttk.Frame(self)
		progress_label_frame.grid(row=2,column=0,sticky="news")

		progress_label_static = ttk.Label(progress_label_frame,text="scan: ")
		progress_label_static.grid(row=0,column=0, columnspan=1, sticky = 'w')
		self.progress_label = ttk.Label(progress_label_frame,text="",foreground="black")
		self.progress_label.grid(row=0,column=1, columnspan=2, sticky = 'w')

		eta_label_static = ttk.Label(progress_label_frame,text="eta (s): ")
		eta_label_static.grid(row=1,column=0, columnspan=1, sticky = 'w')
		self.eta_label = ttk.Label(progress_label_frame,text="",foreground="black")
		self.eta_label.grid(row=1,column=1, columnspan=2, sticky = 'w')

		#progressbar
		self.progress_bar_var = tk.DoubleVar(value=0.0)

		progress_bar_frame = ttk.Frame(self)
		progress_bar_frame.grid(row=3,column=0,pady = 5,sticky="news")

		self.progress_bar = ttk.Progressbar(progress_bar_frame,mode="determinate"
											,variable=self.progress_bar_var,orient="horizontal",length=250,maximum=1)
		self.progress_bar.grid(row=0,column=0)

		#cosmic ray removal check button
		cosmic_ray_frame = ttk.Frame(self)
		cosmic_ray_frame.grid(row=4,column=0,pady = 5,sticky="news")

		self.cosmic_ray_var = tk.IntVar(value=0)
		cosmic_ray_checkbutton = ttk.Checkbutton(cosmic_ray_frame, text = "cosmic ray removal (roi only)", 
									variable = self.cosmic_ray_var, onvalue = 1, offvalue = 0)
		cosmic_ray_checkbutton.grid(row=0,column=0,sticky="w")

		threshold_label = ttk.Label(cosmic_ray_frame,text = "threshold: ")
		threshold_label.grid(row=0,column=1,sticky="w")

		self.threshold_entry_var = tk.StringVar(value="6")
		gain_entry = ttk.Entry(cosmic_ray_frame,width=5,textvariable=self.threshold_entry_var)
		gain_entry.grid(row=0,column=2,sticky="w")

	def image_buttons_state(self,state): # enables and disables buttons while scanning
		if state == "disable":
			for i in range(len(self.image_buttons_list)):
				self.image_buttons_list[i].configure(state=tk.DISABLED)
		elif state == "enable":
			for i in range(len(self.image_buttons_list)):
				self.image_buttons_list[i].configure(state=tk.NORMAL)

	@threaded
	def time_estimates(self,average_scan_time,current_scan_number,total_scan_number):
		#self.progress_bar_thread_bool = True
		self.progress_bar_thread_event.clear()

		total_time_estimate = average_scan_time * total_scan_number
		time_left_estimate = average_scan_time * (total_scan_number - current_scan_number)

		sleep_time = 0.1
		while self.progress_bar_thread_event.is_set() == False:
			if total_time_estimate != 0:
				self.progress_bar_var.set( (1-(time_left_estimate / total_time_estimate)) )
				self.eta_label.configure(text=f"{round(time_left_estimate, 1)}")
				time_left_estimate -= sleep_time
			time.sleep(sleep_time)

	@threaded
	def run(self):
		print("run")

		self.image_thread_event.clear()
		setup_time_start = time.time()

		#check if camera is connected
		if self.controller.camera == None:
			messagebox.showinfo("", "No camera connected.")
			print("camera not connected")
			return

		try:
			camera_info = self.controller.camera.get_camera_property()
			ccd_width = camera_info["MaxWidth"]
			ccd_height = camera_info["MaxHeight"]
		except:
			messagebox.showwarning("Camera Error", "Could not communicate with selected camera.")
			return

		#check if background is active and correct size
		if self.controller.ccd_bitmap_background is not None:

			background_width = np.shape(self.controller.ccd_bitmap_background)[1]
			background_height = np.shape(self.controller.ccd_bitmap_background)[0]

			if (background_width !=ccd_width) and (background_height !=ccd_height):
				messagebox.showinfo("Incompatible background", f"background w,h = {background_width},{background_height}\n camera w,h = {ccd_width},{ccd_height}")
				return
		#check calibration is correct size
		if (self.controller.x is not None) and (len(self.controller.x ) != ccd_width ):
			messagebox.showinfo("Incompatible calibration", f"calibration length = {len(self.controller.x )} ccd width = {ccd_width}")
			return

		self.image_buttons_state("disable") #disable buttons while scanning

		exposure_time = float(self.exposure_entry_var.get()) #user enters in seconds, gets converted to microseconds for zwo asi
		average_number = float(self.average_entry_var.get())
		gain = float(self.gain_entry_var.get())

		self.controller.camera.set_control_value(zwoasi.ASI_EXPOSURE, int(exposure_time*1e6))
		self.controller.camera.set_control_value(zwoasi.ASI_GAIN, int(gain))


		bitmap_averaged = np.zeros((ccd_height,ccd_width)) #make array for ccd image type of "bitmap" is now float 64 to do math operations on

		bitmap_background = self.controller.ccd_bitmap_background

		setup_time_end = time.time()
		setup_time = setup_time_end-setup_time_start
		print(f"set up time = {setup_time}")
		average_image_time = 0

		count = 0 #use a count incase there is an error getting bitmap and a scan is skipped
		lost_scans = 0
		for i in range(int(average_number)):
			scan_time_start = time.time()

			#update time labels
			self.progress_label.configure(text=f"{count+1} / {int(average_number-lost_scans)}",foreground="black")
			if average_image_time == 0:
				self.eta_label.configure(text=f"{exposure_time*average_number}")
				self.progress_bar_thread = self.time_estimates(exposure_time,count,average_number-lost_scans)
			else:
				#self.progress_bar_thread_bool = False
				self.progress_bar_thread_event.set()
				self.progress_bar_thread.join() #wait for previous progress bar to finish before starting another
				self.progress_bar_thread = self.time_estimates(average_image_time,count,average_number-lost_scans)

			try:
				bitmap = self.controller.camera.capture(initial_sleep=None, poll=None)
			except:
				if lost_scans == 0: #only print error once
					#messagebox.showwarning("Camera Error!", "Count not recieve ccd bitmap from camera.\n frame skipped.")
					if self.image_thread_event.is_set() == False:
						self.show_non_modal_message(self, "Camera Error!", "Could not recieve ccd bitmap from camera.\n frame skipped.") #warning that does not stop the run loop
				print("scan skipped")
				lost_scans += 1
				if self.image_thread_event.is_set() == True: #if program is closed end function
					#self.progress_bar_thread_bool = False
					self.progress_bar_thread_event.set()
					return
				else:
					continue


			if self.image_thread_event.is_set() == True: #if the program wants to stop the thread (on closing of the stop button)
				#self.progress_bar_thread_bool = False
				self.progress_bar_thread_event.set()
				self.progress_bar_thread.join() #wait for previous progress bar to finish before starting another
				self.progress_bar_var.set( 0 )
				self.eta_label.configure(text=f"{0}")
				self.progress_label.configure(text=f"scan stopped",foreground="red")
				return

			#cosmic ray removal on current bin
			if self.cosmic_ray_var.get() == 1:
				bitmap = bitmap.astype('float64')
				img_bin_array = bitmap[self.controller.canvas_rectangle_coords[0] : self.controller.canvas_rectangle_coords[1]]
				#self.cosmic_ray_thread_event = threading.Event()
				self.cosmicdd(img_bin_array, th=float(self.threshold_entry_var.get()), asy=0.6745, m=5) #spectrapepper library
				self.cosmic_ray_thread_event.wait()
				try:
					bitmap[self.controller.canvas_rectangle_coords[0] : self.controller.canvas_rectangle_coords[1]] = self.cosmic_ray_array
				except:
					if self.image_thread_event.is_set() == False:
						self.show_non_modal_message(self, "Camera Error!", f"Could not remove cosmic rays.\n Cosmic ray removal skipped for scan: {i+1}.")

			bitmap_averaged *= count #undo the averaging division
			bitmap_averaged += bitmap
			bitmap_averaged /= count+1

			if bitmap_background is not None:
				self.controller.ccd_bitmap = (bitmap_averaged-bitmap_background)
				print("background_subtraction")
			else:
				self.controller.ccd_bitmap = (bitmap_averaged)
			
			self.controller.canvas_graph_update()

			scan_time_stop = time.time()
			scan_time = scan_time_stop - scan_time_start
			average_image_time *= count
			average_image_time += scan_time
			average_image_time /= count+1

			count+=1
			print(f"average scan time = {average_image_time}")
			if self.save_file_name is not None: #save spectra each loop if run/save button clicked
				self.save_spectra()


		#set image states back to original values
		self.progress_bar_thread_event.set()
		self.progress_bar_thread.join()
		self.progress_bar_var.set( 1 )
		self.eta_label.configure(text=f"{0}")
		self.image_thread_event.set()

		self.image_buttons_state("enable") #re-enable buttons after scanning

	@threaded
	def run_continuous(self): #function will only stop when program closed or stop button pressed
		if self.controller.camera == None:
			messagebox.showinfo("", "No camera connected.")
			print("camera not connected")
			return
		self.image_thread_event.clear()
		while (self.image_thread_event.is_set() == False):
			current_scan = self.run()
			current_scan.join()

	@threaded
	def run_save(self):
		if self.controller.camera == None:
			messagebox.showinfo("", "No camera connected.")
			print("camera not connected")
			return
		self.save_file_name = filedialog.asksaveasfilename(defaultextension=".csv")

		if not self.save_file_name:
			return

		current_scan = self.run()
		current_scan.join()

		self.save_file_name = None

	def save_spectra(self):
		file = open(self.save_file_name, "w")

		# if type(header) != type(None):
		#     file.write(header+"\n")

		if self.controller.x is None:
			x = np.arange(1,len(self.controller.y)+1)
		else:
			x = self.controller.x
		y = self.controller.y

		for i in range(len(y)):
			file.write(str(x[i])+","+str(y[i])+","+"\n")

		file.close()

	@threaded
	def cosmicdd(self, y, th=100, asy=0.6745, m=5): #modified cosmic ray removal from spectrapepper
		"""
		modified CR removal from python library spectrapepper
		Grau-Luque et al., (2021). spectrapepper: A Python toolbox for advanced analysis
 		of spectroscopic data for materials and devices. Journal of Open Source Software,
 		6(67), 3781, https://doi.org/10.21105/joss.03781
		
		cosmicdd identifies CRs by detrended differences, the differences between a
		value and the next (D. A. Whitaker and K. Hayes, https://doi.org/10.1016/j.chemolab.2018.06.009).
		"""
		self.cosmic_ray_thread_event.clear() #reset thread event
		data = copy.deepcopy(y)

		diff = list(np.array(data))  # diff data

		for i in range(len(data)):  # for each spectra
			if self.image_thread_event.is_set() == True:
				self.cosmic_ray_thread_event.set()
				return
			for j in range(len(data[0])-1):  # for each step
				if self.image_thread_event.is_set() == True:
					self.cosmic_ray_thread_event.set()
					return
				diff[i][j] = abs(data[i][j]-data[i][j+1])  # diff with the next one

		zt = []  # Z scores
		for i in diff:  # for each diff. vector
			if self.image_thread_event.is_set() == True:
				self.cosmic_ray_thread_event.set()
				return
			z = []  # temporal z score
			temp = []  # temporal MAD (median absolute deviation)
			med = np.median(i)  # just median

			for j in i:  # for each step in each diff. spectra
				temp.append(abs(j-med))  # calculate MAD
			mad = np.median(temp)  # save MAD

			for j in i:  # for each step in each diff. spectra
				z.append(asy*(j - med)/mad)  # calculate Z score
			zt.append(z)  # save Z score

		for i in range(len(data)):  # for each spectra
			if self.image_thread_event.is_set() == True:
				self.cosmic_ray_thread_event.set()
				return
			for j in range(len(data[i])-1):  # in all its len. except the last (range)
				if self.image_thread_event.is_set() == True:
					self.cosmic_ray_thread_event.set()
					return
				if abs(zt[i][j]) > th:  # if it is larger than the th. then it is CR
					data[i][j] = (sum(data[i][j-m:j]) + sum(data[i][j+1:j+m+1]))/(2*m)  # avg, of neighbors
		
		self.cosmic_ray_array =  data
		self.cosmic_ray_thread_event.set()

	@threaded
	def take_background(self): # use the run scan to save ccd image then set this to the backgound
		if self.controller.camera == None:
			messagebox.showinfo("", "No camera connected.")
			print("camera not connected")
			return
		self.controller.ccd_bitmap_background = None

		background_scan = self.run()
		background_scan.join()
		self.controller.ccd_bitmap_background = self.controller.ccd_bitmap

	def load_background(self):
		Bitmap(controller=self.controller).open_bitmap()

	def save_background(self):
		Bitmap(controller=self).save_bitmap(self.controller.ccd_bitmap_background,camera=self.controller.camera)

	def undo_background(self):
		
		if self.controller.ccd_bitmap is not None:
			ccd_width = np.shape(self.controller.ccd_bitmap)[1]
			ccd_height = np.shape(self.controller.ccd_bitmap)[0]
			background_width = np.shape(self.controller.ccd_bitmap_background)[1]
			background_height = np.shape(self.controller.ccd_bitmap_background)[0]

			if (ccd_width == background_width) and (ccd_height == background_height):
				self.controller.ccd_bitmap = (self.controller.ccd_bitmap.astype(np.float64))+self.controller.ccd_bitmap_background
				self.controller.canvas_graph_update()
		self.controller.ccd_bitmap_background = None

	@threaded
	def stop(self):
		try:
			self.controller.camera.stop_exposure()
		except:
			#message box only if camera was supposed to be scanning
			if self.image_thread_event.is_set() == False:
				messagebox.showinfo("", "Camera is not scanning.")
		self.image_thread_event.set()
		self.save_file_name = None
		self.image_buttons_state("enable")

	def show_non_modal_message(self, parent, title, message):
		"""Creates a non-modal Toplevel window."""
		dialog = tk.Toplevel(parent)
		dialog.title(title)
		# Makes the Toplevel transient to its parent
		dialog.transient(parent)
		
		label = ttk.Label(dialog, text=message, padding=20)
		label.pack()

		# Optional: Add a simple 'OK' button to close just the dialog
		ok_button = ttk.Button(dialog, text="OK", command=dialog.destroy)
		ok_button.pack(pady=10)

class Calibration(ttk.LabelFrame):
	def __init__(self,parent,controller,label_frame_text=""):
		super().__init__(parent,text=label_frame_text)

		self.controller = controller

		self.peaks_radiobutton_var = tk.IntVar(value=0)
		
		self.data_peaks_entry_list = []
		self.calibration_peaks_entry_list = []

		self.raman_shift_var = tk.IntVar(value=0)
		self.laser_wavelength_var = tk.StringVar(value="532.2")

		peaks_setup_frame = ttk.Frame(self)
		peaks_setup_frame.grid(row=0,column=0,sticky="news")

		#calibration peaks info
		calibration_peaks_label = ttk.Label(peaks_setup_frame,text = "# of calibration peaks: ")
		calibration_peaks_label.grid(row=0,column=0,sticky="w")

		self.calibration_peaks_entry_var = tk.StringVar(value="2")
		calibration_peaks_entry = ttk.Entry(peaks_setup_frame,width=4,textvariable=self.calibration_peaks_entry_var)
		calibration_peaks_entry.grid(row=0,column=1,sticky="w",padx=5)

		#polynoial degree info
		polynomial_degree_label = ttk.Label(peaks_setup_frame,text = "fit polynomial degree: ")
		polynomial_degree_label.grid(row=1,column=0,sticky="w")

		self.polynomial_degree_entry_var = tk.StringVar(value="1")
		polynomial_degree_entry = ttk.Entry(peaks_setup_frame,width=4,textvariable=self.polynomial_degree_entry_var)
		polynomial_degree_entry.grid(row=1,column=1,sticky="w",padx=5)

		button_frame = ttk.Frame(self)
		button_frame.grid(row=1,column=0,pady = 10,sticky="news")

		calibrate_button = ttk.Button(button_frame, text="cal",command = lambda: self.calibrate(self.calibration_peaks_entry_var.get(),self.polynomial_degree_entry_var.get()))
		calibrate_button.grid(row=0,column=0,sticky="news")

		undo_calibrate_button = ttk.Button(button_frame, text="undo cal",command = self.undo_calibrate)
		undo_calibrate_button.grid(row=0,column=1,sticky="news")

	def calibrate(self,calibration_peak_number,polynomial_degree):

		try:
			calibration_peak_number,polynomial_degree = int(calibration_peak_number),int(polynomial_degree)
			if polynomial_degree >= calibration_peak_number:
				messagebox.showinfo("", "Polynomial degree < # of peaks.")
				return

		except:
			messagebox.showinfo("", "Invalid entries.")
			return

		if self.controller.calibration_window is not None:
			self.controller.calibration_window.destroy()

		calibration_window = tk.Toplevel(self.controller)
		self.controller.calibration_window = calibration_window
		calibration_window.title("Calibration")
		try:
			calibration_window.iconbitmap("steve.ico")
		except:
			pass

		info_frame = ttk.Frame(calibration_window)
		info_frame.grid(row=0,column=0,pady = 10,sticky="news")

		info_label = ttk.Label(info_frame,text = "  select a radio button and double click a peak on the graph")
		info_label.grid(row=0,column=0)

		#set up buttons based on number of peaks
		peaks_frame = ttk.Frame(calibration_window)
		peaks_frame.grid(row=1,column=0,sticky="news")

		self.peaks_radiobutton_var.set(0)
		if len(self.data_peaks_entry_list) != calibration_peak_number:
				self.calibration_peaks_entry_list.clear()
				self.data_peaks_entry_list.clear()

		calibration_peaks_label = ttk.Label(peaks_frame,text = "cal peaks x")
		calibration_peaks_label.grid(row=0,column=1,sticky="w")

		temp_data_peaks_label = ttk.Label(peaks_frame,text = "data peaks x")
		temp_data_peaks_label.grid(row=0,column=2,sticky="w")


		for i in range(calibration_peak_number):
			if i>10:
				break

			if len(self.data_peaks_entry_list) != calibration_peak_number:

				temp_calibration_peaks_entry_var = tk.StringVar()
				self.calibration_peaks_entry_list.append(temp_calibration_peaks_entry_var)

				temp_data_peaks_entry_var = tk.StringVar()
				self.data_peaks_entry_list.append(temp_data_peaks_entry_var)

			
			temp_radio = ttk.Radiobutton(peaks_frame,text=f"peak : {i}",variable=self.peaks_radiobutton_var,value=i)
			temp_radio.grid(row=i+1,column=0,padx=5)

			temp_calibration_peaks_entry = ttk.Entry(peaks_frame,width=10,textvariable=self.calibration_peaks_entry_list[i])
			temp_calibration_peaks_entry.grid(row=i+1,column=1,sticky="w",padx=5)

			temp_data_peaks_entry = ttk.Entry(peaks_frame,width=10,textvariable=self.data_peaks_entry_list[i])
			temp_data_peaks_entry.grid(row=i+1,column=2,sticky="w",padx=5)

		#raman shift check
		raman_shift_frame = ttk.Frame(calibration_window)
		raman_shift_frame.grid(row=2,column=0,pady = 5,sticky="news")

		raman_shift_checkbutton = ttk.Checkbutton(raman_shift_frame, text = "raman shift (nm \u2192 cm\u207B\u00B9)", 
									variable = self.raman_shift_var, onvalue = 1, offvalue = 0)
		raman_shift_checkbutton.grid(row=0,column=0,sticky="w",padx=5)

		laser_wavelength_label = ttk.Label(raman_shift_frame,text = "          laser wavelength (nm): ")
		laser_wavelength_label.grid(row=1,column=0,sticky="w")

		laser_wavelength_entry = ttk.Entry(raman_shift_frame,width=5,textvariable=self.laser_wavelength_var)
		laser_wavelength_entry.grid(row=1,column=1,sticky="w",padx=5)

		#calibration buttons
		button_frame = ttk.Frame(calibration_window)
		button_frame.grid(row=3,column=0,pady = 10,sticky="news")

		calibrate_button = ttk.Button(button_frame, text="calibrate",command = lambda: self.set_calibration(calibration_peak_number,polynomial_degree))
		calibrate_button.grid(row=0,column=0,padx=10,sticky="news")

		clear_entries_button = ttk.Button(button_frame, text="clear",command = self.clear_entries)
		clear_entries_button.grid(row=0,column=1,sticky="news")

		load_peaks_button = ttk.Button(button_frame, text="load peaks",command = self.load_peaks)
		load_peaks_button.grid(row=0,column=2,sticky="news")

	def clear_entries(self):
		for i in range(len(self.data_peaks_entry_list)):
			self.data_peaks_entry_list[i].set("")
			self.calibration_peaks_entry_list[i].set("")

	def set_calibration(self,calibration_peak_number,polynomial_degree):
		data_x = np.zeros(calibration_peak_number)
		calibration_x = np.zeros(calibration_peak_number)
		try:
			for i in range(calibration_peak_number):
				data_x[i] = float(self.data_peaks_entry_list[i].get())
				calibration_x[i] = float(self.calibration_peaks_entry_list[i].get())

		except:
			messagebox.showinfo("", "Invalid entries.")
			return



		calibration_fit = np.polyfit(data_x, calibration_x, polynomial_degree) #returns list of polynomial coefficients from highest degree to lowest 

		if self.controller.x is None:
			x_fit = np.linspace(0, len(self.controller.y), num=50)
			x_temp = np.arange(0,len(self.controller.y))
			self.controller.x = self.polynomial_function(x_temp,calibration_fit)
		else:
			x_fit = np.linspace(min(self.controller.x), max(self.controller.x), num=50)
			self.controller.x = self.polynomial_function(self.controller.x,calibration_fit)

		calibration_figure = plt.figure()
		calibration_figure_ax = calibration_figure.add_subplot(1,1,1)
		calibration_figure_ax.plot(data_x,calibration_x,".")
		calibration_figure_ax.plot(x_fit,self.polynomial_function(x_fit,calibration_fit))
		plt.show()
		plt.close()

		if self.raman_shift_var.get() == 1:
			self.controller.x = ( (10**7) / float(self.laser_wavelength_var.get()) ) - ((10**7) / self.controller.x )
			#ax1.set_xlabel("Raman shift (cm$^{-1}$)",fontsize=15)
		else:
			pass
			#ax1.set_xlabel("Wavelength (nm)",fontsize=15)

		self.controller.canvas_graph_update()

	def polynomial_function(self,x,params):
		params = np.flip(params)
		y = np.zeros(len(x))
		for i in range(len(params)):
			y += params[i]*(x**i)
		return y


	def load_peaks(self):
		x_temp = []
		filename = filedialog.askopenfilename()

		try:
			file = open(filename,'r')
			for i in file:
				x_temp_i = i
				x_temp.append(float(x_temp_i))

			file.close()

			for i in range(len(self.calibration_peaks_entry_list)):
				self.calibration_peaks_entry_list[i].set(str(x_temp[i]))

		except:
			messagebox.showwarning("Peak error!", "Could not read file.")
			return

		self.controller.calibration_window.lift()


	def undo_calibrate(self):
		self.controller.x = None
		self.controller.canvas_graph_update()

class Temperature(ttk.LabelFrame):
	def __init__(self,parent,controller,label_frame_text=""):
		super().__init__(parent,text=label_frame_text)
		
		self.controller = controller
		#threading event start set true for no thread running (Event.wait() waits while Event is set to false)
		self.temperature_thread_event = threading.Event()
		self.temperature_thread_event.set()

		#temp labels
		labels_frame = ttk.Frame(self)
		labels_frame.grid(row=0,column=0,sticky="news")

		current_temperature_label_static = ttk.Label(labels_frame,text="current temperature (\u00B0C): ")
		current_temperature_label_static.grid(row=0,column=0, columnspan=1, sticky = 'w')
		self.current_temperature_label = ttk.Label(labels_frame,text="",foreground="black")
		self.current_temperature_label.grid(row=0,column=1, columnspan=2, sticky = 'w')

		power_label_static = ttk.Label(labels_frame,text="power (%): ")
		power_label_static.grid(row=1,column=0, columnspan=1, sticky = 'w')
		self.power_label = ttk.Label(labels_frame,text="",foreground="black")
		self.power_label.grid(row=1,column=1, columnspan=2, sticky = 'w')

		#temperature settings
		entry_frame = ttk.Frame(self)
		entry_frame.grid(row=1,column=0,sticky="news")

		temperature_label = ttk.Label(entry_frame,text = "Set point (\u00B0C): ")
		temperature_label.grid(row=0,column=0,sticky="w")

		self.temperature_entry_var = tk.StringVar(value="-13")
		temperature_entry = ttk.Entry(entry_frame,width=5,textvariable=self.temperature_entry_var)
		temperature_entry.grid(row=0,column=1,sticky="w")

		button_frame = ttk.Frame(self)
		button_frame.grid(row=2,column=0,pady = 10,sticky="news")

		self.cooler_button = ttk.Button(button_frame, text="turn cooler on",command = self.cooler)
		self.cooler_button.grid(row=0,column=0)
	@threaded
	def cooler(self):
		#print("state ",self.temperature_thread_event.is_set())
		if self.controller.camera == None:
			messagebox.showinfo("", "No camera connected.")
			print("camera not connected")
			return
		elif self.controller.camera.get_camera_property()["IsCoolerCam"] != True:
			print("not cooler cam")
			messagebox.showinfo("", "Selected camera does not have a cooler.")
			return

		if self.temperature_thread_event.is_set() == True:
			print("turn on cooler")
			self.temperature_thread_event.clear()
			print("test",self.temperature_thread_event.is_set())
			try:
				target_temperature = int(self.temperature_entry_var.get())
				print("target temp",target_temperature)
				self.controller.camera.set_control_value(zwoasi.ASI_TARGET_TEMP,target_temperature)
			except:
				self.temperature_thread_event.set()
				messagebox.showwarning("Temperature error!", f"Count not set temperature to {self.temperature_entry_var.get()}.")

			self.cooler_button.configure(text="turn cooler off")

			self.controller.camera.set_control_value(zwoasi.ASI_COOLER_ON, 1)
			self.controller.camera.set_control_value(zwoasi.ASI_FAN_ON,1)

		else:
			self.temperature_thread_event.set()

			self.cooler_button.configure(text="turn cooler on")
			
			self.controller.camera.set_control_value(zwoasi.ASI_COOLER_ON, 0)
			self.controller.camera.set_control_value(zwoasi.ASI_FAN_ON,0)

			self.current_temperature_label.configure(text="")
			self.power_label.configure(text="")

		while self.temperature_thread_event.is_set() == False:
			try:
				current_temperature = self.controller.camera.get_control_value(zwoasi.ASI_TEMPERATURE)
				current_temperature = current_temperature[0]/10 #zwo asi ccd store temp as int *10 to keep one decimal 
				power = self.controller.camera.get_control_value(zwoasi.ASI_COOLER_POWER_PERC)
				power = power[0]
			except:
				print("camera busy")
				#continue

			self.current_temperature_label.configure(text=f"{current_temperature}")
			self.power_label.configure(text=f"{power}")

			if current_temperature > 0:
				self.current_temperature_label.configure(foreground="red")
			else:
				self.current_temperature_label.configure(foreground="blue")
			time.sleep(1)

		print("done temp loop")

class ROISet(ttk.LabelFrame):
	def __init__(self,parent,controller,label_frame_text=""):
		super().__init__(parent,text=label_frame_text)

		self.controller = controller

		roi_label_frame = ttk.Frame(self)
		roi_label_frame.grid(row=0,column=0,sticky="news")

		center_label_static = ttk.Label(roi_label_frame,text="center: ")
		center_label_static.grid(row=0,column=0, sticky = 'w')
		self.center_label = ttk.Label(roi_label_frame,text="5",foreground="black")
		self.center_label.grid(row=0,column=1, sticky = 'w')

		height_label_static = ttk.Label(roi_label_frame,text="height: ")
		height_label_static.grid(row=0,column=2, sticky = 'w')
		self.height_label = ttk.Label(roi_label_frame,text="5000",foreground="black")
		self.height_label.grid(row=0,column=3, sticky = 'w')

		#entry frame
		entry_frame = ttk.Frame(self)
		entry_frame.grid(row=1,column=0,sticky="news")

		#center position of roi
		roi_center_label = ttk.Label(entry_frame,text = "center : ")
		roi_center_label.grid(row=0,column=0,sticky="w")

		self.roi_center_var = tk.StringVar(value="1")
		roi_center_entry = ttk.Entry(entry_frame,width=10,textvariable=self.roi_center_var)
		roi_center_entry.grid(row=0,column=1,sticky="w")

		#height of roi
		roi_height_label = ttk.Label(entry_frame,text = "height : ")
		roi_height_label.grid(row=0,column=2,sticky="w")

		self.roi_height_var = tk.StringVar(value="1")
		roi_height_entry = ttk.Entry(entry_frame,width=10,textvariable=self.roi_height_var)
		roi_height_entry.grid(row=0,column=3,sticky="w")

		#set roi button
		button_frame = ttk.Frame(self)
		button_frame.grid(row=2,column=0,pady = 10,sticky="news")

		roi_set_button = ttk.Button(button_frame, text="set",command = self.roi_set)
		roi_set_button.grid(row=0,column=0)

		#log ccd image
		log_ccd_frame = ttk.Frame(self)
		log_ccd_frame.grid(row=3,column=0,pady = 5,sticky="news")

		self.log_ccd_var = tk.IntVar(value=0)
		log_ccd_checkbutton = ttk.Checkbutton(log_ccd_frame, text = "log view ccd", 
									variable = self.log_ccd_var, onvalue = 1, offvalue = 0, command = self.controller.canvas_graph_update)
		log_ccd_checkbutton.grid(row=0,column=0,sticky="w")

	def roi_set(self):

		roi_center = float(self.roi_center_var.get())
		roi_height = int(self.roi_height_var.get())

		self.controller.canvas_rectangle_coords[0] = int( roi_center - (roi_height/2) )
		self.controller.canvas_rectangle_coords[1] = int( roi_center + (roi_height/2) )
		print("roi_button =",self.controller.canvas_rectangle_coords[0],self.controller.canvas_rectangle_coords[1] )

		self.center_label.configure(text=str(roi_center))
		self.height_label.configure(text=str(roi_height))

		self.controller.canvas_graph_update()

class ThreadTest(ttk.Frame):
	def __init__(self,parent_window,main_window,thread_text):
		super().__init__(parent_window)
		#self.thread_text = thread_text
		self.main_window = main_window

		ttk.Label(self, text=f"Thread test: ").pack(side="left")
		ttk.Button(self, text="print",command = lambda: self.threaded_print(thread_text) ).pack(side="right")
		ttk.Button(self, text="stop",command = self.stop_thread ).pack(side="right")

	@threaded #thread decorated function
	def threaded_print(self,thread_text):
		if self.main_window.thread_bool:
			print(thread_text)
			time.sleep(0.5)
			self.threaded_print(thread_text)

	def stop_thread(self):
		if self.main_window.thread_bool == False:
			self.main_window.thread_bool = True
		else:
			self.main_window.thread_bool = False
		 