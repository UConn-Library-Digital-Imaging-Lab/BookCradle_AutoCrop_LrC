local LrDialogs         = import "LrDialogs"
local LrTasks           = import "LrTasks"
local LrApplication     = import "LrApplication"
local LrPathUtils       = import "LrPathUtils"
local LrFileUtils       = import "LrFileUtils"
local LrProgressScope   = import "LrProgressScope"
local LrView            = import "LrView"
local LrBinding         = import "LrBinding"
local LrFunctionContext = import "LrFunctionContext"
local LrColor           = import "LrColor"

local json = require "dkjson"

-- Launch a background "async" task so script doesn't freeze the main Lightroom app.
LrTasks.startAsyncTask(function()
  LrFunctionContext.callWithContext("BookCradleAutoCropDialog", function(context)
    -- Grab the currently open catalog, and all the photos currently selected by user.
    local catalog = LrApplication.activeCatalog()
    local photos  = catalog:getTargetPhotos()
    if #photos == 0 then LrDialogs.message("No photos selected."); return end

    -- Create and manage the property table tied to the Crop Boundary Strategy and Margin features.
    local props = LrBinding.makePropertyTable(context)
    props.cropMode = "inside"
    props.insideStrategy = "average"
    props.marginPercent = 2.0

    -- Build and show dialogue box
    local f = LrView.osFactory()
    
    local modePopup = f:popup_menu {
        value = LrView.bind("cropMode"),
        items = {
            { title = "Inside Page Edge (Uniform Crop Box)", value = "inside" },
            { title = "Outside Book Edge (With Margin)", value = "outside" }
        }
    }

    local strategyPopup = f:popup_menu {
        value = LrView.bind("insideStrategy"),
        items = {
            { title = "Minimum (Tight to Text)", value = "tight" },
            { title = "Average", value = "average" },
            { title = "Maximum (Edge to Edge)", value = "max" }
        },
        enabled = LrView.bind{ key = "cropMode", transform = function(v) return v == "inside" end }
    }

    local marginInput = f:edit_field {
        value = LrView.bind("marginPercent"),
        width_in_chars = 8,
        enabled = LrView.bind{ key = "cropMode", transform = function(v) return v == "outside" end }
    }
    
    local dialogContent = f:column{
      spacing = 15, bind_to_object = props,
      
      f:row {
          spacing = 4,
          f:static_text { title = "Pages Selected:" },
          f:static_text { 
              title = tostring(#photos),
              font = "<system/bold>",
              text_color = LrColor( 0, .055, .184 )
          }
      },
      
      f:row {
        spacing = f:control_spacing(),
        f:static_text{ title = "Crop Strategy:" },
        modePopup,
      },
      
      f:row {
        spacing = f:control_spacing(),
        f:static_text{ title = "Inside Crop Size:" },
        strategyPopup,
      },

      f:row {
        spacing = f:control_spacing(),
        f:static_text{ title = "Outer Margin (%):" },
        marginInput,
      }
    }
    
    -- Wait for user to click OK or Cancel. 
    -- 'Ok' initiates python script, saves settings, and generates progress bar.
    local ok = LrDialogs.presentModalDialog{ 
        title = "BookCradle AutoCrop Settings", 
        contents = dialogContent 
    }
    
    if ok ~= "ok" then return end

    local margin = (tonumber(props.marginPercent) or 0) / 100.0
    local mode = props.cropMode
    local strategy = props.insideStrategy

    local progressRun = LrProgressScope{ title = "Analyzing Batch Content…" }

    -- Find system Temp folder and find or create LR_BookCradleAutocrop folder inside.
    -- Create unique sub-folder to hold data for this run.
    local baseTemp = LrPathUtils.child(LrPathUtils.getStandardFilePath("temp"), "LR_BookCradleAutocrop")
    if not LrFileUtils.exists(baseTemp) then LrFileUtils.createAllDirectories(baseTemp) end
    local tempFolder = LrPathUtils.child(baseTemp, "run_" .. tostring(os.time()))
    LrFileUtils.createAllDirectories(tempFolder)

    -- Create text file and populate with actual path of each photo selected in Lightroom.
    -- Include an index to match the line number with each photo.
    local listPath = LrPathUtils.child(tempFolder, "dng_files.txt")
    local lf = io.open(listPath, "wb")
    local items = {}
    for i, photo in ipairs(photos) do
      local p = photo:getRawMetadata("path") 
      if p and #p > 0 then
        lf:write(p .. "\n")
        items[#items + 1] = { index = i, photo = photo } 
      end
    end
    lf:close()
    
    if #items > 0 then
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
        end

        -- Execute the command and wait for it to finish.
        local pythonExitCode = LrTasks.execute(cmd)
        local pythonFatalError = nil
        local resultsByIndex = {}

        -- Check if python succeeded. If it did, open the JSON results file, decode it, and check for fatal errors or save crop data.
        if pythonExitCode == 0 then
            local rf = io.open(resultsPath, "rb")
            if rf then
              for line in rf:lines() do
                local obj = json.decode(line)
                if obj and obj.fatal_error then
                    pythonFatalError = obj.fatal_error
                    break
                elseif obj and obj.index then
                    resultsByIndex[tonumber(obj.index)] = obj
                end
              end
              rf:close()
            end
        else
            progressRun:done()
            LrDialogs.message("Processing failed. Exit code: " .. tostring(pythonExitCode))
            return
        end

        -- If Python caught an exception and logged it, show it to user in a critical dialog box.
        if pythonFatalError then
            progressRun:done()
            LrDialogs.message("Error Log", pythonFatalError, "critical")
            return
        end

        -- Apply crops
        local successCount = 0
        local errorCount = 0

        -- Ask Lightroom for write access. Create single modification called "Apply Uniform BookCradle Cropping" that can be reversed with "undo".
        catalog:withWriteAccessDo("Apply Uniform BookCradle Cropping", function()
          -- Loop through selected photos, lookup crop and angle values for each photo.
          for i, it in ipairs(items) do
            local r = resultsByIndex[i]
            if r and not r.error then
              local L, R, T, B = tonumber(r.left), tonumber(r.right), tonumber(r.top), tonumber(r.bottom)
              local A = tonumber(r.angle) or 0.0
              
              -- Ensure coordinates are inside image bounds and properly formatted as relative percentages (0.0 to 1.0) expected by Lightroom.
              if L and R and T and B and L < R and T < B and L >= 0 and T >= 0 and R <= 1 and B <= 1 then
                it.photo:applyDevelopSettings({ 
                    CropLeft = L, 
                    CropRight = R, 
                    CropTop = T, 
                    CropBottom = B, 
                    CropAngle = A 
                })
                successCount = successCount + 1
              else
                errorCount = errorCount + 1
              end
            else
              errorCount = errorCount + 1
            end
          end
        end)

        if LrFileUtils.exists(tempFolder) then
          LrFileUtils.delete(tempFolder)
        end

        progressRun:done()
        
        -- Popup message showing how many images were cropped successfully vs skipped.
        local msg = string.format("Batch AutoCrop complete.\nSuccessfully cropped: %d", successCount)
        if errorCount > 0 then
          msg = msg .. string.format("\nSkipped due to errors: %d", errorCount)
        end
        
        LrDialogs.message(msg)
    else
        progressRun:done()
        LrDialogs.message("No valid file paths available.")
    end
  end)
end)
