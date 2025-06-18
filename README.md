# Faux Bolex - A DIY Digital Cinema Camera Project (Beta 0.93)

## The Dream: A Cinema Camera "With a Box of Scraps"

Welcome to the Faux Bolex project! This endeavor was born from a lifelong passion for filmmaking, a fascination with the technical aspects of cinema cameras, and a natural-born maker's spirit. Born in 1980, owning a proper cinema camera was an impossible dream. While digital cinema has made this more accessible (thanks, George Lucas, Jim Jannard, and others), the challenge of building one from scratch was an irresistible siren call.

This project is an homage to the spirit of innovation and a nod to the legendary Digital Bolex D16. Why the D16? Its beautiful marriage of old and new, the unique look from its 1" CCD global shutter sensor, and Joseph Rubinstein's original vision for an accessible cinema tool resonated deeply. Its untimely demise also served as a motivation to keep its spirit alive, in a way.

Our goal: To create a digital RAW 2K cinema camera, as Obadiah Stane might say, "with a box of scraps!" (or at least, readily available components).

## The Journey: From Monolith to Maker Masterpiece

This project has been nearly a year in the making, filled with research, headaches, trial-and-error, and moments of "eureka!"

**Phase 1: The "Ugly Monolithic" Beginnings (The Spark - approx. Beta 0.1 - 0.3)**

*   **Concept & Core Components:**
    *   Inspired by the Digital Bolex D16 for its sensor and overall ethos.
    *   Technical concept influenced by projects like CinemaPI (though no code/structure was reused).
    *   **Hardware Selected:**
        *   Raspberry Pi (initially older models, now a Pi 5 8Gb + SSD hat).
        *   M.2 1Tb SSD for high-speed RAW recording.
        *   The heart: A Basler Aviator avA2300-25gc GigE industrial camera module, featuring the **exact same Kodak KAI-04050 1" CCD global shutter sensor** as the Digital Bolex D16. Critically, its interface could pull off ~24fps at 2K.
        *   USB Gamepad board for physical button controls.
        *   12V/5A 7800mAh battery pack.
        *   3D printed resin body and accessories.
        *   A growing collection of C-mount and adaptable lenses.

*   **The First Code (The Monolith):**
    *   The initial software was a single, sprawling Python script – a testament to a burst of creative energy and a lot of caffeine
    *   It was a patchwork of:
        *   Code snippets to interface with the Basler camera via the Pylon SDK (pieced together from documentation and examples).
        *   Random blocks extracted from OpenCV repositories for image manipulation and display.
        *   A Python gaming library for basic button input.
    *   AI assistance was more rudimentary back then (this was many AI-generations ago), so progress was a hard-fought battle of sifting through documentation and endless debugging.

*   **Early Milestones & Struggles:**
    *   **Success:** Achieved (silent) uncompressed 2K TIFF file output to an intermediary buffer, then saved to SSD on stop.
    *   **Success:** Implemented a 720p 24fps debayered preview feed.
    *   **Success:** Basic automatic White Balance and Gain control (though rudimentary).
    *   **Struggle:** File sizes were enormous (uncompressed TIFFs).
    *   **Struggle:** Code was difficult to maintain and expand.
    *   **Struggle:** Performance was always a concern, pushing the limits of the hardware.
    *   **Wall:** Truly replicating the D16's CinemaDNG RAW output felt like a distant dream.

**Phase 2: The Great Refactoring & The DNG Breakthrough (The Structure - approx. Beta 0.4 - 0.7)**

*   **The Shift to OOP and C++:**
    *   Realizing the monolithic Python script was hitting its limits, a major refactor began.
    *   The core camera operations (Pylon SDK interface, image grabbing, critical processing) were moved to a C++ module. This was a steep learning curve, involving diving deep into the Pylon SDK.
    *   `PyBind11` became the bridge, allowing Python to call these performant C++ functions. This hybrid approach was a game-changer.
    *   Python was retained for the main application logic, UI (OpenCV `imshow`), DNG generation orchestration, and overall control.

*   **Conquering CinemaDNG:**
    *   This was the "holy grail" for the project. The goal was to output industry-standard DNG files, just like the original D16.
    *   **Milestone:** Reverse-engineering original Bolex D16 DNG files to understand their metadata structure and tags. This was painstaking work.
    *   **Tooling:** The `PiDNG` library (or a similar DNG library/custom implementation) was adopted/developed to construct DNG files.
    *   **Initial Success:** We went from debayered TIFFs to compliant, usable RAW DNGs. This was mind-blowing. The camera could now output files that professional software like DaVinci Resolve could understand as RAW.
    *   **Struggle:** Color science was tricky. Initial DNGs looked washed out or had color casts. The original Bolex color matrices were elusive or hard to apply correctly at first.
    *   **Struggle:** Metadata was complex. Getting all the DNG tags right (`BlackLevel`, `WhiteLevel`, `ColorMatrix1/2`, `CalibrationIlluminant1/2`, `AsShotNeutral`, `CFAPattern`) was an iterative process of trial, error, and `exiftool` analysis.
    *   **Struggle (Still):** DNG file sizes were still an issue (initially uncompressed within the DNG).

**Phase 3: Refinement, UI, and Real-World Usability (The Polish - approx. Beta 0.7 - 0.93 - Where We Are Now)**

*   **Color Science Deep Dive (The "It Works Like a Real Camera" Moment):**
    *   This was a period of intense focus. We wrestled with:
        *   `BlackLevel` and `WhiteLevel` settings (understanding sensor black vs. DNG tag black, MSB-aligned data, etc.). The "eyeballed" `30/30980` with unscaled data became a key pragmatic solution for a good default look in Resolve when `BaselineExposure` was ignored.
        *   Correctly sourcing and applying the original Bolex D16 `ColorMatrix1` (StdA) and `ColorMatrix2` (D65) and pairing them with the right `CalibrationIlluminant` tags.
        *   Ensuring `AsShotNeutral` was correctly calculated from camera WB gains and formatted as rationals for the DNG.
        *   Confirming the `CFAPattern` (GBRG `1,2,0,1`) for our direct sensor output.
        *   Adding `BayerGreenSplit` for better demosaicing.
    *   **Milestone:** DNGs started looking *good* in DaVinci Resolve, especially after a manual WB, with recoverable highlights and shadows. The "Faux Bolex" was producing images with a quality and flexibility comparable to commercial cinema cameras.

*   **User Interface (UI) Overhaul:**
    *   **The Goal:** Move away from "beta test" looking overlays to something professional.
    *   **Custom Fonts:** Integrated Pillow for rendering "Roboto Condensed" fonts, replacing aliased OpenCV Hershey fonts. This dramatically improved the look.
    *   **Performance vs. Quality:** Iterated on preview frame handling (channel order, conversions) to maintain FPS while using Pillow. Settled on an RGB pipeline for preview display on the specific RPi setup.
    *   **Framing Guides:** Implemented a 2.39:1 aspect ratio frame guide with a border that changes color (white for standby, red for record), replacing the simple red dot.
    *   **Letterbox Darkening:** Added optional darkening of areas outside the 2.39:1 frame for better compositional focus.
    *   **Fullscreen Preview:** Achieved reliable fullscreen operation for the 1024x600 display.

*   **Hardware Controls & Usability:**
    *   **Gamepad Integration:** Successfully mapped physical buttons on a USB gamepad to functions like Start/Stop Record, Gain Up/Down, WB Trigger, Clipping Toggle using `pygame`.
    *   **Desktop Launcher:** Created a `.desktop` file for easy application launching.

*   **Performance and Efficiency:**
    *   **Lossless JPEG Compression:** After confirming `PiDNG` supports it via `compress=True`, implemented this, reducing DNG file sizes by ~33% without any loss of quality. This was a huge win for practicality.
    *   **Optimized Preview Resolution:** Changed C++ preview output to 1280x720 (or 1024x576 for better 1:1 on display) to improve Python-side UI rendering performance and preview sharpness, while DNGs capture the full 2048x1152 16:9 sensor data.

*   **Current Status (Beta 0.93):**
    *   Records 2K (2048x1152, 16:9) DNGs with lossless JPEG compression.
    *   DNGs have robust metadata (correctly applied Bolex color matrices, illuminants, black/white levels chosen for a good look, neutral AsShotNeutral, etc.) that yield good, gradable images in DaVinci Resolve.
    *   Features a professional-looking fullscreen UI with custom fonts, 2.39:1 framing guides (with record status indication), and optional letterboxing.
    *   Full gamepad control for key camera operations.
    *   Stable preview and recording FPS.

## The Road Ahead (Beyond Beta 0.93)

While Beta 0.93 is incredibly capable, the journey of a maker is never truly over! Potential future explorations include:

*   **Lens Mount Modification:** Actively working on a DIY M4/3 mount to vastly expand lens options (primes, zooms, speed boosters!). This is the current major engineering challenge.
*   **Advanced UI Elements:** Further refining the UI, perhaps adding histograms, audio meters (if audio is implemented).
*   **Audio Recording:** Exploring options for synchronized audio capture.
*   **Custom Tone Curve / Look Profiles:** Developing a custom `ToneCurve` DNG tag or DCP profile for a more refined "Faux Bolex Native Look" out of the box.
*   **Further Optimizations:** Always looking for ways to squeeze more performance or efficiency.
*   **Sharing with the Community:** This GitHub repo, YouTube videos, and social media.

This project is a labor of love, and it's a thrill to see it come so far. Thank you for joining me on this journey!

---
# 2025 - La Faux Bolex
# Released under the MIT License. See LICENSE for details.
