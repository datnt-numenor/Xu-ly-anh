// Fiji (GUI mode), language Groovy, TrackMate 7.x/8.x.
// Walks through the real TrackMate wizard on one frame folder with the group's
// settings and saves a PNG screenshot of every step, the Tracks table and the
// track overlay on the image. Needs a display (on Linux: xvfb-run).
#@ File(label="Folder containing frame_000.png, ...", style="directory") framesDir
#@ File(label="Screenshot folder", style="directory") outputDir
#@ String(label="Detector", choices={"threshold", "log"}, value="threshold") detectorChoice
#@ String(label="Tracker", choices={"kalman", "lap", "nearest"}, value="kalman") trackerChoice
#@ Integer(label="Frame shown in the overlay shot", value=26) overlayFrame

import ij.IJ
import ij.ImagePlus
import ij.ImageStack
import java.awt.Rectangle
import java.awt.Robot
import java.awt.Window
import javax.imageio.ImageIO
import javax.swing.AbstractButton
import javax.swing.JFrame
import javax.swing.JTabbedPane
import javax.swing.SwingUtilities
import fiji.plugin.trackmate.Model
import fiji.plugin.trackmate.SelectionModel
import fiji.plugin.trackmate.Settings
import fiji.plugin.trackmate.TrackMate
import fiji.plugin.trackmate.detection.LogDetectorFactory
import fiji.plugin.trackmate.detection.ThresholdDetectorFactory
import fiji.plugin.trackmate.features.FeatureFilter
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings
import fiji.plugin.trackmate.gui.displaysettings.DisplaySettings.TrackDisplayMode
import fiji.plugin.trackmate.gui.wizard.TrackMateWizardSequence
import fiji.plugin.trackmate.gui.wizard.WizardController
import fiji.plugin.trackmate.tracking.jaqaman.SimpleSparseLAPTrackerFactory
import fiji.plugin.trackmate.tracking.kalman.KalmanTrackerFactory
import fiji.plugin.trackmate.tracking.kdtree.NearestNeighborTrackerFactory
import fiji.plugin.trackmate.visualization.hyperstack.HyperStackDisplayer
import fiji.plugin.trackmate.visualization.table.TrackTableView

robot = new Robot()
shots = outputDir

def onEdt(Closure c) { SwingUtilities.invokeAndWait(c as Runnable) }

def capture(Window window, String name) {
    Thread.sleep(1200)
    onEdt { window.toFront(); window.repaint() }
    Thread.sleep(600)
    def image = robot.createScreenCapture(new Rectangle(window.getLocationOnScreen(), window.getSize()))
    ImageIO.write(image, "png", new File(shots, name + ".png"))
    println("Saved " + name)
}

def findTabs(java.awt.Container root) {
    for (component in root.getComponents()) {
        if (component instanceof JTabbedPane) return component
        if (component instanceof java.awt.Container) {
            def found = findTabs(component)
            if (found != null) return found
        }
    }
    return null
}

def findButton(java.awt.Container root, String text) {
    for (component in root.getComponents()) {
        if (component instanceof AbstractButton && component.getText()?.trim() == text) return component
        if (component instanceof java.awt.Container) {
            def found = findButton(component, text)
            if (found != null) return found
        }
    }
    return null
}

// 1. Open the PNG sequence as a calibrated hyperstack and enlarge it.
def paths = framesDir.listFiles().findAll { it.name ==~ /frame_[0-9]+[.]png/ }.sort { it.name }
def first = IJ.openImage(paths.first().absolutePath)
def stack = new ImageStack(first.getWidth(), first.getHeight())
paths.each { stack.addSlice(it.name, IJ.openImage(it.absolutePath).getProcessor().convertToByte(false)) }
def imp = new ImagePlus(framesDir.name, stack)
imp.setDimensions(1, 1, stack.getSize())
imp.setOpenAsHyperStack(true)
imp.calibration.frameInterval = 1d / 15d
imp.calibration.setUnit("pixel")
imp.calibration.setTimeUnit("s")
imp.show()
Thread.sleep(1500)
IJ.run(imp, "In [+]", "")
IJ.run(imp, "In [+]", "")
onEdt { imp.getWindow().setLocation(0, 0) }
capture(imp.getWindow(), "01_hyperstack")

// 2. Pre-fill the settings with the group's parameters; the wizard shows them.
def factories = [kalman: new KalmanTrackerFactory(), lap: new SimpleSparseLAPTrackerFactory(),
                 nearest: new NearestNeighborTrackerFactory()]
def settings = new Settings(imp)
settings.addAllAnalyzers()
if (detectorChoice == "log") {
    // Same values as TrackMate_Nhom9.groovy.
    settings.detectorFactory = new LogDetectorFactory()
    settings.detectorSettings = settings.detectorFactory.getDefaultSettings()
    settings.detectorSettings.put("RADIUS", 7d)
    settings.detectorSettings.put("THRESHOLD", 5d)
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
settings.trackerFactory = factories[trackerChoice]
settings.trackerSettings = settings.trackerFactory.getDefaultSettings()
settings.trackerSettings.put("LINKING_MAX_DISTANCE", 24d)
if (trackerChoice == "lap") {
    settings.trackerSettings.put("ALLOW_GAP_CLOSING", true)
    settings.trackerSettings.put("GAP_CLOSING_MAX_DISTANCE", 36d)
    settings.trackerSettings.put("MAX_FRAME_GAP", 6)
}
if (trackerChoice == "kalman") {
    settings.trackerSettings.put("KALMAN_SEARCH_RADIUS", 24d)
    settings.trackerSettings.put("MAX_FRAME_GAP", 6)
}

def model = new Model()
model.setPhysicalUnits("pixel", "s")
def trackmate = new TrackMate(model, settings)
def selection = new SelectionModel(model)
def display = DisplaySettings.defaultStyle().copy()
display.setTrackDisplayMode(TrackDisplayMode.LOCAL_BACKWARD)
display.setFadeTrackRange(30)
display.setLineThickness(3d)
def displayer = new HyperStackDisplayer(model, selection, imp, display)
displayer.render()

// 3. Walk through the wizard and capture every step.
def sequence = new TrackMateWizardSequence(trackmate, selection, display)
def controller = new WizardController(sequence)
JFrame frame = null
onEdt {
    frame = new JFrame("TrackMate on " + imp.getShortTitle())
    frame.getContentPane().add(controller.getWizardPanel())
    frame.setSize(380, 720)
    frame.setLocation(imp.getWindow().getWidth() + 10, 0)
    controller.init()
    frame.setVisible(true)
}
def step = 2
def seen = [] as Set
while (true) {
    def key = sequence.current().getPanelDescriptorIdentifier()
    if (key in seen) break
    seen << key
    if (key == "ConfigureDetector") {
        // Click "Preview" to show the detected spots on the current frame.
        onEdt { imp.setT(22) }
        def preview = findButton(frame.getContentPane(), "Preview")
        if (preview != null) {
            onEdt { preview.doClick() }
            Thread.sleep(2500)
            capture(imp.getWindow(), String.format("%02d_Preview_image", step++))
        }
    }
    if (key == "ExecuteDetection" || key == "ExecuteTracking") Thread.sleep(4000)
    capture(frame, String.format("%02d_%s", step++, key))
    if (key == "ConfigureViews") {
        // The display panel: open the Tracks table from its "Tracks" button.
        def tracks = new TrackTableView(model, selection, display, imp.getShortTitle())
        onEdt {
            tracks.render()
            tracks.setLocation(0, imp.getWindow().getHeight() + 10)
            tracks.setSize(1100, 240)
            findTabs(tracks.getContentPane())?.setSelectedIndex(2)  // Spots, Edges, Tracks
        }
        capture(tracks, String.format("%02d_TracksTable", step++))
        onEdt { imp.setT(overlayFrame + 1); displayer.refresh() }
        capture(imp.getWindow(), String.format("%02d_Overlay", step++))
        break
    }
    if (!sequence.hasNext()) break
    onEdt { controller.next() }
    Thread.sleep(1500)
}
println("Done")
System.exit(0)
