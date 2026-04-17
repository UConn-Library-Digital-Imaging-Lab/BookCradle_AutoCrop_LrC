local LrView = import 'LrView'
local LrPathUtils = import 'LrPathUtils'
local LrHttp = import 'LrHttp'

return {
    sectionsForTopOfDialog = function(f, propertyTable)
        local logoPath = LrPathUtils.child(_PLUGIN.path, "Library-stacked_blue.png")
        local repoUrl = "https://github.com/UConn-Library-Digital-Imaging-Lab/Digitization_AutoCrop_LrC"
	local rdmeUrl = "https://github.com/UConn-Library-Digital-Imaging-Lab/Digitization_AutoCrop_LrC?tab=readme-ov-file"
        
        return {
            {
                title = "Plugin Info",
                
                f:column {
                    spacing = 10,
                    
                    f:row {
		    
                        fill_horizontal = 1,
                        
			f:column {
			    f:spacer { height = 12 },
                            f:static_text {
                                title = "Book Cradle AutoCrop",
                                font = "<system/bold>",
                            }
			},
                        
                        -- Pushes the logo to the right edge
                        f:spacer { fill_horizontal = 1 }, 
                        
                        f:picture {
                            value = logoPath,
                            width = 150, -- Reduced from 201
                            height = 50, -- Reduced from 67
                        }
                    },
                    
                    f:row {
                        fill_horizontal = 1,
                        
                        f:static_text {
                            title = "This Lightroom Classic plugin automates the cropping of cultural heritage and archival materials captured using a V-shaped book cradle. It uses Python and OpenCV to read the JPEG preview image embedded in DNG files, detect material boundaries and features, and calculate crop coordinates and rotation angles. It is optimized to work with DNG files with Medium Sized JPEG Previews embedded.",
                            width_in_chars = 58,
                            height_in_lines = 4, 
                        }
                    },

                    f:row {
			spacing = 10,

                        f:push_button {
                            title = "Info for Users",
                            action = function()
                                LrHttp.openUrlInBrowser(rdmeUrl)
                            end
                        },

                        f:push_button {
                            title = "Source Code Repository",
                            action = function()
                                LrHttp.openUrlInBrowser(repoUrl)
                            end
                        }
                    },

                    
                    f:row {
                        fill_horizontal = 1,
                        margin_top = 10,
                        
                        f:static_text {
                            title = "Developed by Ian Paul for the Digital Imaging Lab at the Homer Babbidge Library, University of Connecticut.",
                            width_in_chars = 58,
                            height_in_lines = 1,
                        }
                    },

                    f:row {
                        fill_horizontal = 1,
                        
                        f:static_text {
                            title = "Acknowledgements",
                            font = "<system/bold>",
                        }
                    },

                    f:row {
                        fill_horizontal = 1,
                        
                        f:static_text {
                            title = "A special thanks to Michael J. Bennett for his support and insight throughout the development of this plugin.",
                            width_in_chars = 58,
                            height_in_lines = 1,
                        }
                    },

                    f:row {
                        f:static_text {
                            title = "David Heiko Kolf for dkjson.lua.",
                            width_in_chars = 58,
                            height_in_lines = 1,
                        }
                    },

                    f:row {    
                        f:static_text {
                            title = "Stephen Holdaway for the proof of concept that inspired this project and the original framework it followed.",
                            width_in_chars = 58,
                            height_in_lines = 1,
                        }
                    }
                }
            }
        }
    end
}