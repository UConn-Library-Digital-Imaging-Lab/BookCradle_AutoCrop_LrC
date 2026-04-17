local LrDialogs         = import "LrDialogs"
local LrTasks           = import "LrTasks"
local LrApplication     = import "LrApplication"
local LrView            = import "LrView"
local LrBinding         = import "LrBinding"
local LrFunctionContext = import "LrFunctionContext"
local LrColor           = import "LrColor"

LrTasks.startAsyncTask(function()
  LrFunctionContext.callWithContext("NudgeCropDialog", function(context)
    local catalog = LrApplication.activeCatalog()
    local photos  = catalog:getTargetPhotos()
    
    if #photos == 0 then 
        LrDialogs.message("No photos selected.")
        return 
    end

    local props = LrBinding.makePropertyTable(context)
    
    -- Always start at 0px so we don't accidentally double-apply previous nudges
    props.topEdge = 0
    props.bottomEdge = 0
    props.foreEdge = 0
    props.spine = 0

    local f = LrView.osFactory()
    
    local function makeInputRow(title, propName)
        return f:row {
            spacing = 10,
            f:static_text { title = title, alignment = "right", width = 120 },
            f:edit_field { 
                value = LrView.bind(propName), 
                width_in_chars = 8 
            }
        }
    end

    local dialogContent = f:column {
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
        
        f:separator { fill_horizontal = 1 },

        f:static_text { title = "Positive (+) expands outward from center of page.\nNegative (-) shrinks inward toward center of page." },
        
        makeInputRow("Top Edge (%):", "topEdge"),
        makeInputRow("Bottom Edge (%):", "bottomEdge"),
        makeInputRow("Fore Edge (%):", "foreEdge"),
        makeInputRow("Spine (%):", "spine")
    }
    
    local ok = LrDialogs.presentModalDialog { 
        title = "Nudge Batch Crop", 
        contents = dialogContent 
    }
    
    if ok ~= "ok" then return end

    -- Fetch the raw pixel values entered by the user
   local fracTop = (tonumber(props.topEdge) or 0) / 100.0
    local fracBot = (tonumber(props.bottomEdge) or 0) / 100.0
    local fracFore = (tonumber(props.foreEdge) or 0) / 100.0
    local fracSpine = (tonumber(props.spine) or 0) / 100.0

    -- If all inputs are 0, exit instantly to save time
    if fracTop == 0 and fracBot == 0 and fracFore == 0 and fracSpine == 0 then return end

    local successCount = 0

    catalog:withWriteAccessDo("Nudge Crop Boundaries", function()
        for _, photo in ipairs(photos) do
            local settings = photo:getDevelopSettings()
            
            -- Get image dimensions to convert nudges into Lightroom percentages
            local dim = photo:getRawMetadata("dimensions")
            local rawW = dim and dim.width or 1
            local rawH = dim and dim.height or 1
            
            -- Lightroom Crop coordinates are relative to the native image orientation.
            -- Assuming standard landscape camera mounting
            local W = math.max(rawW, rawH)
            local H = math.min(rawW, rawH)
            
            -- Calculate percentage in pixels using the short edge
            local shortEdge = math.min(rawW, rawH)
            local pxTop = shortEdge * fracTop
            local pxBot = shortEdge * fracBot
            local pxFore = shortEdge * fracFore
            local pxSpine = shortEdge * fracSpine

            -- Convert pixels back into Lightroom's percentages
            local lrFracTop = pxTop / W
            local lrFracBot = pxBot / W
            local lrFracFore = pxFore / H
            local lrFracSpine = pxSpine / H
            
            local curL = settings.CropLeft or 0.0
            local curT = settings.CropTop or 0.0
            local curR = settings.CropRight or 1.0
            local curB = settings.CropBottom or 1.0
            local curA = settings.CropAngle or 0.0
            
            -- Orientation dictates which raw coordinate maps to the physical Top/Bottom of the book
            local orientation = settings.Orientation or "AB"

            -- Spine is always bottom
            -- Fore Edge is always top
            local newT = curT - lrFracFore  
            local newB = curB + lrFracSpine 

            local newL = curL
            local newR = curR

            -- Determine physical Top/Bottom edges of book based on 90 degree rotation
            -- 90 degree CCW rotated images are seen as Left-hand pages. Top of book must be Right edge to Lightroom.
	    -- 90 degree CW rotated images are seen as Right-hand pages. Top of book must be Left edge to Lightroom.
            if orientation == "DA" then 
                newR = curR + lrFracTop
                newL = curL - lrFracBot
            else 
                newL = curL - lrFracTop
                newR = curR + lrFracBot
            end

            -- Ensure new crop is within image boundaries
            newL = math.max(0.0, math.min(1.0, newL))
            newT = math.max(0.0, math.min(1.0, newT))
            newR = math.max(0.0, math.min(1.0, newR))
            newB = math.max(0.0, math.min(1.0, newB))

            -- Ensure the box didn't invert itself
            if newL < newR and newT < newB then
                photo:applyDevelopSettings({
                    CropLeft   = newL,
                    CropTop    = newT,
                    CropRight  = newR,
                    CropBottom = newB,
                    CropAngle  = curA
                })
                successCount = successCount + 1
            end
        end
    end)

    LrDialogs.message(string.format("Nudge complete.\nUpdated %d photos.", successCount))
  end)
end)