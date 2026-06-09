# DiGS-Z
DiGS-Z is a Python GUI application for data acquisition using a diffraction grating spectrometer with ZWO ASI cameras.

---

## Installation & Launch

- Clone or download this repository to your machine.
- Install the required open-source Python dependencies for example using pip:

```bash
pip install numpy matplotlib opencv-python pillow zwoasi
```
### Windows

- Download and install the [ZWO camera driver](https://www.zwoastro.com/software/), found under **Desktop Apps - Windows**. Follow along through the .exe installer

- Download the [ASICamera2.dll](https://www.zwoastro.com/software/), found under **Others - For Developers - ASI Camera SDK**. Navigate through this .zip folder to find the ASICamera2.dll correct for your device (ie. Windows x64).

- Place the ASICamera2.dll in a folder called lib in the DiGS-Z main directory, the directory with the main.py, classes.py, and img folder.

### Linux
- Install the python library [Tkinter](https://docs.python.org/3/library/tkinter.html) if not already installed.

- Download the [libASICamera2.so](https://www.zwoastro.com/software/), found under **Others - For Developers - ASI Camera SDK**. Navigate through this .zip folder to find the libASICamera2.so correct for your device (ie. Linux x64).

- Place the libASICamera2.so in a folder called lib in the DiGS-Z main directory, the directory with the main.py, classes.py, and img folder.

- Follow the README.txt in the ASI Camera SDK on adding the asi.rules to your system.

#
- Plug your ZWO ASI Camera into a USB port, USB 3.0 is reccommended for faster scanning times.

- Launch the application:

```bash
python3 main.py
```

---

## License

This project is licensed under the **GNU General Public License v3.0 (GPLv3)**. 

### ZWO SDK Linking Exception
To accommodate proprietary hardware drivers, this software includes an explicit linking exception under Section 7 of the GPLv3:

> As a special exception to the GNU General Public License version 3.0, the copyright holders of this software grant permission to link this program with the proprietary ZWO ASI Camera SDK (including but not limited to zwoasicamera2.dll, libasicamera2.so, and libasicamera2.dylib) and distribute the resulting combination. All other requirements of the GNU GPLv3 regarding your own source code and any modifications remain fully in effect.

For full license details, please see the appended terms in the root `LICENSE` file.

---

## Credits & Acknowledgements

This project was made possible by the following incredible open-source libraries:
* **[python-zwoasi](https://github.com/python-zwoasi/python-zwoasi)** by Steve Marple — For the Python wrapper logic interfacing with the ZWO SDK.
* **[OpenCV](https://opencv.org)** & **[Pillow](https://python-pillow.github.io)** — For image manipulation.
* **[Matplotlib](https://matplotlib.org)** — For handling graphing.
* **[NumPy](https://numpy.org)**  — For data manipulation.
