
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

__author__ = "Collin Tower"
__license__ = 'GNU GPL V3.0'
__version__ = "1.0.0"

#gui imports
import tkinter as tk
from tkinter import ttk 
from tkinter import filedialog
from tkinter import messagebox

# import custom classes
import classes

#data manipulation
import numpy as np

#image manipulation
import cv2

#ZWO ASI python binding
import zwoasi

#threading
import threading
import time

#find operating system
import platform
os_name = platform.system()
print(f"OS: {os_name}")

if os_name == "Windows":
	zwoasi.init(r"lib/ASICamera2.dll")
elif os_name == "Linux":
	zwoasi.init(r"lib/libASICamera2.so.1.40")

num_cameras = zwoasi.get_num_cameras()
print("camera number: ",num_cameras)


def main(): #function to start program, called at end of the file
	raman_program = Application()
	raman_program.mainloop()

class Application(tk.Tk):

	def __init__(self):
		super().__init__()
		################
		# Window setup #
		################
		self.title("DiGS-Z")
		logo = tk.PhotoImage(file="img/logo.png")
		self.wm_iconphoto(True, logo)
		try:
			self.iconbitmap("steve.ico")
		except:
			#img = tk.PhotoImage(file='steve.png')
			#self.iconphoto(True,img)
			pass
		#window sizing
		screen_width = self.winfo_screenwidth()
		screen_height = self.winfo_screenheight()
		screen_scale = (3/4,3/4) #w,h
		mainwindow_width = int(screen_width*screen_scale[0])
		mainwindow_height = int(screen_height*screen_scale[1])
		self.geometry(f"{mainwindow_width}x{mainwindow_height}+0+0") #width x height + x + y

		self.rowconfigure(0, weight=1)
		self.columnconfigure(1, weight=3)

		#function ran on close window (stop all threads)
		self.protocol("WM_DELETE_WINDOW", self.on_close_window)
		
	######################
	# "global" variables #
	######################
		self.camera = None
		self.ccd_bitmap = cv2.imread("img/Default.png", cv2.IMREAD_UNCHANGED) 
		self.ccd_bitmap_background = None
		self.x, self.y = None, None
		self.canvas_rectangle_coords = [None,None]

		self.calibration_window = None
	################
	#Gui File Menu #
	################

		menubar = tk.Menu(self)

		#file menu
		filemenu = tk.Menu(menubar, tearoff=0)

		filemenu.add_command(label="load image (raw/png)", command=lambda: classes.Bitmap(controller=self).open_bitmap("ccd_bitmap") )
		filemenu.add_command(label="save image (raw/png)", command=lambda: classes.Bitmap(controller=self).save_bitmap(self.ccd_bitmap,camera=self.camera) )
		filemenu.add_separator()
		filemenu.add_command(label="load background image (raw/png)", command=lambda: classes.Bitmap(controller=self).open_bitmap("ccd_bitmap_background") )
		filemenu.add_command(label="save background image (raw/png)", command=lambda: classes.Bitmap(controller=self).save_bitmap(self.ccd_bitmap_background,camera=self.camera) )
		filemenu.add_separator()
		filemenu.add_command(label="load calibration", command= self.load_calibration)
		filemenu.add_command(label="save calibration", command= self.save_calibration)
		filemenu.add_separator()
		filemenu.add_command(label="save spectra", command=self.save_spectra )

		menubar.add_cascade(label="file", menu=filemenu)

		#about menu
		about_menu = tk.Menu(menubar, tearoff=0)
		about_menu.add_command(label="About", command=self.show_about)
		menubar.add_cascade(label="About", menu=about_menu)

		self.config(menu=menubar)

	##################
	# Controls Frame #
	##################
		#make a scrollable frame to contain controls incase screen size is not large enough
		scroll_frame_container = classes.ScrollableFrame(self)
		scroll_frame_container.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)	

		#######################
		# select camera frame #
		#######################
		camera_frame = classes.CameraSelect(scroll_frame_container.scrollable_frame,self,text="Camera Select")
		camera_frame.configure(padding=5)
		camera_frame.pack(fill="x")

		####################
		# take image frame #
		####################
		self.image_take_frame = classes.ImageTake(scroll_frame_container.scrollable_frame,self,label_frame_text="Take Image")
		self.image_take_frame.configure(padding=5)
		self.image_take_frame.pack(fill="x")

		#####################
		# Calibration frame #
		#####################
		self.calibration_frame = classes.Calibration(scroll_frame_container.scrollable_frame,self,label_frame_text="Calibration")
		self.calibration_frame.configure(padding=5)
		self.calibration_frame.pack(fill="x")

		#####################
		# Calibration frame #
		#####################
		self.temperature_frame = classes.Temperature(scroll_frame_container.scrollable_frame,self,label_frame_text="Temperature")
		self.temperature_frame.configure(padding=5)
		self.temperature_frame.pack(fill="x")

		#################
		# set ROI frame #
		#################
		self.roi_set_frame = classes.ROISet(scroll_frame_container.scrollable_frame,self,label_frame_text="ROI Settings")
		self.roi_set_frame.configure(padding=5)
		self.roi_set_frame.pack(fill="x")

	###################
	# ROI/Graph frame #
	###################
		tabs_frame = ttk.Frame(self)
		tabs_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

		self.tab_control = ttk.Notebook(tabs_frame)

		tab1 = ttk.Frame(self.tab_control)
		tab2 = ttk.Frame(self.tab_control)
		tab3 = ttk.Frame(self.tab_control)

		self.tab_control.add(tab1, text ='ROI + Spectra')
		self.tab_control.add(tab2, text ='Spectra')
		self.tab_control.add(tab3, text ='ROI')

		self.tab_control.pack(expand = True, fill ="both")

		self.tab_control.bind("<<NotebookTabChanged>>", lambda e: self.canvas_graph_update())
		#########
		# tab 1 #
		#########
		tab1.columnconfigure(0, weight=1)
		tab1.columnconfigure(1, weight=1)
		tab1.rowconfigure(0, weight=1)

		self.tab1_graph = classes.GraphCanvas(tab1,self)
		self.tab1_graph.configure(relief="groove",padding=10)
		self.tab1_graph.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)

		self.tab1_graph.rowconfigure(0, weight=1)
		self.tab1_graph.columnconfigure(0, weight=1)

		self.tab1_roi = classes.RoiCanvas(tab1,self,linked_graph = self.tab1_graph)
		self.tab1_roi.configure(relief="groove",padding=10)
		self.tab1_roi.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)


		self.tab1_roi.grid_propagate(False)
		self.tab1_roi.pack_propagate(False)
		self.tab1_graph.grid_propagate(False)

		#########
		# tab 2 #
		#########
		tab2.columnconfigure(0, weight=1)
		tab2.rowconfigure(0, weight=1)

		self.tab2_graph = classes.GraphCanvas(tab2,self)
		self.tab2_graph.configure(relief="groove",padding=10)
		self.tab2_graph.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

		self.tab2_graph.rowconfigure(0, weight=1)
		self.tab2_graph.columnconfigure(0, weight=1)
		#########
		# tab 3 #
		#########
		tab3.columnconfigure(0, weight=1)
		tab3.rowconfigure(0, weight=1)

		self.tab3_roi = classes.RoiCanvas(tab3,self)
		self.tab3_roi.configure(relief="groove",padding=10)
		self.tab3_roi.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
		#tab1_roi.pack(expand = True,fill="both", side="left")

		self.tab3_roi.rowconfigure(0, weight=1)
		self.tab3_roi.columnconfigure(0, weight=1)

	#####################################
	#canvas and graph updating function #
	#####################################
	def canvas_graph_update(self):

		current_tab_widget = self.tab_control.select() 
		current_tab_text = self.tab_control.tab(current_tab_widget, "text") # Get the text of the selected tab
		current_tab_index = self.tab_control.index(current_tab_widget)

		if current_tab_index == 0:
			self.tab1_roi.canvas_update(self.ccd_bitmap)
			self.tab1_roi.roi_rectangle_update(self.canvas_rectangle_coords,self.ccd_bitmap)
			self.tab1_graph.plot_bin(self,
                                            self.ccd_bitmap[self.canvas_rectangle_coords[0]:self.canvas_rectangle_coords[1]])

		if current_tab_index == 1:
			self.tab2_graph.plot_bin(self,
                                            self.ccd_bitmap[self.canvas_rectangle_coords[0]:self.canvas_rectangle_coords[1]])

		if current_tab_index == 2:
			self.tab3_roi.canvas_update(self.ccd_bitmap)
			self.tab3_roi.roi_rectangle_update(self.canvas_rectangle_coords,self.ccd_bitmap)

	def save_spectra(self):
		save_file_name = filedialog.asksaveasfilename(defaultextension=".csv")

		file = open(save_file_name, "w")

		if self.x is None:
		    x = np.arange(1,len(self.y)+1)
		else:
		    x = self.x
		y = self.y

		for i in range(len(y)):
		    file.write(str(x[i])+","+str(y[i])+","+"\n")

		file.close()

	def save_calibration(self):
		if self.x is None:
		    messagebox.showinfo("", "No calibration to save.")
		    return

		save_file_name = filedialog.asksaveasfilename(defaultextension=".csv")

		file = open(save_file_name, "w")

		for i in range(len(self.x)):
		    file.write(str(self.x[i])+"\n")

		file.close()

	def load_calibration(self):
		x_temp = []
		filename = filedialog.askopenfilename()

		try:
			file = open(filename,'r')
			for i in file:
				x_temp_i = i
				x_temp.append(float(x_temp_i))

			file.close()

			if (self.ccd_bitmap is not None) and (np.shape(self.ccd_bitmap)[1] != len(x_temp)):
				messagebox.showinfo("Calibration error", f"Calibration length = {len(x_temp)}, ccd width = {np.shape(self.ccd_bitmap)[1]}.")
				return


			self.x = np.array(x_temp)
			self.canvas_graph_update()
		except:
			messagebox.showwarning("Calibration error!", "Count not read file.")
			return

	def show_about(self):
	    title = "About DiGS-Z"
	    message = (
	        f"DiGS-Z : Diffraction Grating Spectrometer Software v{__version__}\n"
	        "Copyright (C) 2026 Collin Tower\n\n"
	        "This program is free software under the GNU GPLv3 "
	        "(with ZWO SDK linking exception).\n\n"
	        "This program comes with ABSOLUTELY NO WARRANTY."
	    )
	    messagebox.showinfo(title, message)


	def on_close_window(self): #function used for closing the ports when closing the window
		#stop any running scans
		self.image_take_frame.stop()

		#turn off cooler if on
		if self.temperature_frame.temperature_thread_event.is_set() == False:
			self.temperature_frame.cooler()

		self.check_threads_close() #waits for threads to finish before closing

	def check_threads_close(self): # returns true if threads that are not the main thread are running
		thread_list = []
		for thread in threading.enumerate():
			if thread != threading.main_thread():
				thread_list.append(thread)
		print(f"number of running threads={len(thread_list)}")
		if len(thread_list) == 0:
			try:
				self.camera.close() # if ccd is taking an image, stop it
			except:
				print("no camera to close")
			self.destroy()
		else:
			#return True
			self.after(100,self.check_threads_close)
		
if __name__ == "__main__":
	main()
