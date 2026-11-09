// Fiji Script Editor, language Groovy. Targets TrackMate 8.x.
#@ File(label="Folder containing frame_000.png, ...", style="directory") framesDir
#@ File(label="Output folder", style="directory") outputDir

import ij.ImagePlus
import ij.ImageStack
import ij.IJ
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.Spot
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.detection.ThresholdDetectorFactory
import fiji.plugin.trackmate.features.FeatureFilter
import fiji.plugin.trackmate.io.TmXmlWriter
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.kalman.KalmanTrackerFactory
import fiji.plugin.trackmate.tracking.kdtree.NearestNeighborTrackerFactory

if (!outputDir.isDirectory() && !outputDir.mkdirs()) {
    throw new IllegalArgumentException("Unable to create output folder: " + outputDir)
}
def paths = framesDir.listFiles().findAll { it.name ==~ /frame_[0-9]+[.]png/ }.sort { it.name }
if (paths.isEmpty()) throw new IllegalArgumentException("No sample frames found.")
def first = IJ.openImage(paths.first().absolutePath)
def stack = new ImageStack(first.getWidth(), first.getHeight())
paths.each { file ->
    def image = IJ.openImage(file.absolutePath)
    stack.addSlice(file.name, image.getProcessor().convertToByte(false))
}
def imp = new ImagePlus(framesDir.name, stack)
imp.setDimensions(1, 1, stack.getSize())
imp.setOpenAsHyperStack(true)
imp.calibration.frameInterval = 1d / 15d
imp.calibration.setUnit("pixel")
imp.calibration.setTimeUnit("s")

def methods = [
    nearest: new NearestNeighborTrackerFactory(),
    lap: new SimpleSparseLAPTrackerFactory(),
    kalman: new KalmanTrackerFactory()
]

methods.each { name, factory ->
    def model = new Model()
    model.setPhysicalUnits("pixel", "s")
    def settings = new Settings(imp)
    settings.detectorFactory = new ThresholdDetectorFactory()
    settings.detectorSettings = settings.detectorFactory.getDefaultSettings()
    settings.detectorSettings.put("INTENSITY_THRESHOLD", 110d)
    settings.detectorSettings.put("SIMPLIFY_CONTOURS", false)
    settings.addSpotFilter(new FeatureFilter("QUALITY", 35d, true))
    settings.addSpotFilter(new FeatureFilter("QUALITY", 240d, false))
    settings.trackerFactory = factory
    settings.trackerSettings = factory.getDefaultSettings()
    settings.trackerSettings.put("LINKING_MAX_DISTANCE", 24d)
    if (name == "lap") {
        settings.trackerSettings.put("ALLOW_GAP_CLOSING", true)
        settings.trackerSettings.put("GAP_CLOSING_MAX_DISTANCE", 36d)
        settings.trackerSettings.put("MAX_FRAME_GAP", 6)
    }
    if (name == "kalman") {
        settings.trackerSettings.put("KALMAN_SEARCH_RADIUS", 24d)
        settings.trackerSettings.put("MAX_FRAME_GAP", 6)
    }
    def process = new TrackMate(model, settings)
    if (!process.checkInput() || !process.process()) {
        throw new IllegalStateException(name + ": " + process.getErrorMessage())
    }

    def prefix = framesDir.name + "_" + name
    def writer = new TmXmlWriter(new File(outputDir, prefix + ".xml"))
    writer.appendModel(model)
    writer.appendSettings(settings)
    writer.writeToFile()
    def tm = model.getTrackModel()
    new File(outputDir, prefix + ".csv").withWriter("UTF-8") { csv ->
        csv.println("frame,track_id,x,y")
        model.getSpots().iterable(true).each { spot ->
            def trackId = tm.trackIDOf(spot)
            // Treat an unlinked visible spot as a singleton for evaluation.
            def id = trackId == null ? -(spot.ID() + 1) : trackId
            csv.println([spot.getFeature(Spot.FRAME).intValue(), id,
                         spot.getFeature(Spot.POSITION_X), spot.getFeature(Spot.POSITION_Y)].join(","))
        }
    }
    println("Wrote " + prefix + ".xml and .csv")
}
