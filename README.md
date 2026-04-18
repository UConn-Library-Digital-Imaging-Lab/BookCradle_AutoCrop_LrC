# BookCradle_AutoCrop.lrplugin

A Lightroom Classic plugin that automates the cropping of bound cultural heritage and archival materials captured using a V-shaped book cradle. It uses rawpy to extract the JPEG preview image embedded in DNG files, OpenCV to detect material boundaries and features, and sends crop coordinates and rotation angles to Lightroom to apply. It is optimized to work with DNG files with Medium Sized JPEG Previews embedded.

## Installation Instructions

To install the plugin:
1. Navigate to the **[Releases](https://github.com/UConn-Library-Digital-Imaging-Lab/BookCradle_AutoCrop_LrC/releases)** section of the repository.
2. Download the latest `BookCradle_Autocrop_vX.X_OS.zip` file for your operating system.
3. Extract the ZIP file.
4. Move the extracted `BookCradle_Autocrop.lrplugin` folder to a permanent, safe location on your computer.
5. Open Lightroom Classic, go to **File > Plug-in Manager**, click **Add**, and select the folder.

## How to Use
1. Select the images you want to crop in your Lightroom Library.
2. Go to **Library > Plug-in Extras > AutoCrop Selected Bound Material**.
3. Select your desired crop strategy:
    * **Inside Page Edge**: applies a uniform sized crop across all images. You can choose the **Inside Crop Size** you'd like applied, either the minimum crop size available, the maximum available, or an average of the two.
    * **Outside Book Edge**: you can enter a margin percentage into the dialogue box to increase or decrease the margin the crop leaves from the edge of the book. It is defaulted to 2%, which was found to be ideal when used in production within the UConn Library's Digital Imaging Lab. 
    * (Positive value = crop outside page edge, Negative = crop inside page edge).
4. Click **OK**. The plugin will run in the background. When complete, a dialogue box will appear to tell you the crop was successful. Once you click **OK**, the crop boxes and rotation angles for every selected image will be applied at once.
5. You can easily undo the batch crop and rerun it if needed.

## The Nudge Crop Tool

This is a custom tool that can apply simple, uniform crop resizes across a batch of images.

1. Select the images you want to apply a uniform resize to.
2. Go to **Library > Plug-in Extras > Nudge Batch Crop**
3. Enter a percentage into the edge you want to change across the entire selection. Multiple can be entered at once with different values.
    * This tool reads the rotation applied to an image in Lightroom, so it "knows" which edge of the image is the foredge, spine, top and bottom.
4. Click **OK**. The batch crop can be reversed with **Undo** if needed.

## Developer Notes

The computer vision backend (`bookcradle_detect.py`) is written in Python using `rawpy`, `numpy`, and `opencv-python`. The current version of `BookCradle_AutoCrop.lua` is written to work with a compiled executable of `bookcradle_detect.py`. It is included in the release, but can also be created locally using `Pyinstaller`.

### Running Natively (Without the Executable)

If you wish to bypass the compiled executable and run the Python script directly, you will need to modify `BookCradle.lua` and ensure all dependencies are installed on your machine.

**1. Set Up the Python Environment**

Ensure you have Python installed, then use `pip` to install the required dependencies.

```bash
pip install opencv-python numpy rawpy
```
**2. Modify the Lua Script**

Open `BookCradle_Autocrop.lua` and locate the **"Path to the bundled python executable and results"** section.

Find these lines:
```bash
   	-- Paths to bundled python executables, if/then for OS, and results.
      local detectExe
      local cmd
      local resultsPath = LrPathUtils.child(tempFolder, "results.ndjson")

      if WIN_ENV then
         detectExe = LrPathUtils.child(_PLUGIN.path, "bin/bookcradle_detect.exe")
         cmd = string.format('""%s" --dng-list "%s" --margin %s --out "%s""',
                             detectExe, listPath, tostring(margin), resultsPath)
      else
         detectExe = LrPathUtils.child(_PLUGIN.path, "bin/bookcradle_detect")
         cmd = string.format('"%s" --dng-list "%s" --margin %s --out "%s"',
                             detectExe, listPath, tostring(margin), resultsPath)
```
Change references to the executable to reference the script itself. Add OS dependent python interpreter. It should look like:

```bash
      -- Paths to python interpreter, python script, and results.
      local pythonInterpreter
      local scriptPath = LrPathUtils.child(_PLUGIN.path, "bin/bookcradle_detect.py")
      local cmd
      local resultsPath = LrPathUtils.child(tempFolder, "results.ndjson")

      if WIN_ENV then
         -- Windows developers may need to change this to "py" or a full path if python is not in their environment variables.
         pythonInterpreter = "python" 
         cmd = string.format('""%s" "%s" --dng-list "%s" --margin %s --out "%s""',
                             pythonInterpreter, scriptPath, listPath, tostring(margin), resultsPath)

      else
         pythonInterpreter = "python3"
         cmd = string.format('"%s" "%s" --dng-list "%s" --margin %s --out "%s"',
                             pythonInterpreter, scriptPath, listPath, tostring(margin), resultsPath)
      end
```

## Credits
* Developed by Ian Paul for the Digital Imaging Lab at the Homer Babbidge Library, University of Connecticut.

* A special thanks to [Michael J. Bennett](https://tundragraphics.com/) for his support and insight throughout the development of this plugin. His wealth of knowledge, experience, and enthusiasm for advancing the field of cultural heritage imaging helped make this project possible.

* [David Heiko Kolf](https://dkolf.de/) for [dkjson.lua](https://dkolf.de/dkjson-lua/)

* [Stephen Holdaway](https://stecman.co.nz/) for his [proof of concept](https://gist.github.com/stecman/91cb5d28d330550a1dc56fa29215cb85) that inspired this project and the original framework I followed when first exploring this.
