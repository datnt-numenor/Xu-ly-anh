// Fiji Script Editor, language Groovy. Targets TrackMate 8.x.
#@ File(label="Folder containing frame_000.png, ...", style="directory") framesDir
#@ File(label="Output folder", style="directory") outputDir
#@ String(label="Detector", choices={"threshold", "log", "both"}, value="threshold") detectorChoice

import ij.ImagePlus
import ij.ImageStack
import ij.IJ
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.Spot
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.detection.LogDetectorFactory
import fiji.plugin.trackmate.detection.ThresholdDetectorFactory
import fiji.plugin.trackmate.features.FeatureFilter
import fiji.plugin.trackmate.io.TmXmlWriter
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.kalman.KalmanTrackerFactory
import fiji.plugin.trackmate.tracking.kdtree.NearestNeighborTrackerFactory

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

// Threshold detector: quality = spot area, kept in [35, 240] px like the Python code.
// LoG detector: Laplacian of Gaussian for blobs of radius 7 px. It smooths the
// image before looking for maxima, which makes it robust to noise.
// On the test videos true spots score >= 7 and noise maxima <= 2.5.
def LOG_QUALITY = 5d
def detectors = detectorChoice == "both" ? ["threshold", "log"] : [detectorChoice]

[detectors, methods.keySet()].combinations().each { detector, name ->
    def factory = methods[name]
    def model = new Model()
    model.setPhysicalUnits("pixel", "s")
    def settings = new Settings(imp)
    if (detector == "log") {
        settings.detectorFactory = new LogDetectorFactory()
        settings.detectorSettings = settings.detectorFactory.getDefaultSettings()
        settings.detectorSettings.put("RADIUS", 7d)
        settings.detectorSettings.put("THRESHOLD", LOG_QUALITY)
        settings.detectorSettings.put("DO_SUBPIXEL_LOCALIZATION", true)
        settings.detectorSettings.put("DO_MEDIAN_FILTERING", false)
    } else {
        settings.detectorFactory = new ThresholdDetectorFactory()
        settings.detectorSettings = settings.detectorFactory.getDefaultSettings()
        settings.detectorSettings.put("INTENSITY_THRESHOLD", 110d)
        settings.detectorSettings.put("SIMPLIFY_CONTOURS", false)
        settings.addSpotFilter(new FeatureFilter("QUALITY", 35d, true))
        settings.addSpotFilter(new FeatureFilter("QUALITY", 240d, false))
    }
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

    // Drop the spots rejected by the filters before saving, so the XML holds
    // only the tracked spots (on noisy video it would otherwise be ~80 MB).
    def kept = model.getSpots().iterable(true).toSet()
    def rejected = model.getSpots().iterable(false).findAll { !kept.contains(it) }
    model.beginUpdate()
    try { rejected.each { model.removeSpot(it) } } finally { model.endUpdate() }

    def prefix = framesDir.name + (detector == "log" ? "_log_" : "_") + name
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
