return {
  LrSdkVersion = 10.0,
  LrToolkitIdentifier = 'edu.uconn.lib.dil.autocrop_bookcradle',
  LrPluginName = 'Book Cradle AutoCrop',

  LrLibraryMenuItems = {
    {
      title = "AutoCrop Selected Bound Material",
      file  = "BookCradle_AutoCrop.lua",
      enabledWhen = "photosSelected"
    },
    {
      title = "Nudge Batch Crop",
      file = "NudgeCrop.lua",
      enabledWhen = "photosSelected"
    }
  },

  VERSION = { major=1, minor=0, revision=0, build=1, date="2026-04-16" },

  LrPluginInfoProvider = 'PluginManager.lua',
}