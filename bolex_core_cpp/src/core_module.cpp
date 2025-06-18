// src/core_module.cpp (Return Unscaled Raw, Provide WB Gains)

#include "ndarray_converter.h" // OpenCV helper

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>

// Pylon Includes
#include <pylon/PylonIncludes.h>
#include <pylon/TlFactory.h>
#include <pylon/DeviceInfo.h>
#include <pylon/TransportLayer.h>
#include <pylon/InstantCamera.h>
#include <pylon/GrabResultPtr.h>
#include <pylon/ParameterIncludes.h>

#ifdef PYLON_WIN_BUILD
#    include <pylon/PylonGUI.h>
#endif

// OpenCV Includes
#include <opencv2/core/core.hpp>
#include <opencv2/imgproc/imgproc.hpp>

// Standard Includes
#include <stdexcept>
#include <iostream>
#include <memory>
#include <string>
#include <cmath>
#include <algorithm>
#include <utility> // For std::pair

namespace py = pybind11;
using namespace GenApi;

// --- Global/Static Pylon Objects ---
static Pylon::CInstantCamera* camera = nullptr;
static bool pylonInitialized = false;
static const double TARGET_FPS = 24.0; // Or your desired target

// --- Helper Functions ---
int get_ocv_bayer_code_for_rgb(const std::string& pylon_format) {
    // Use the code that matches the actual Pylon Bayer format for PREVIEW
    if (pylon_format == "BayerGB12" || pylon_format == "BayerGB8") return cv::COLOR_BayerGB2RGB; // Sensor is GBRG
    if (pylon_format == "BayerRG12" || pylon_format == "BayerRG8") return cv::COLOR_BayerRG2RGB;
    if (pylon_format == "BayerGR12" || pylon_format == "BayerGR8") return cv::COLOR_BayerGR2RGB;
    if (pylon_format == "BayerBG12" || pylon_format == "BayerBG8") return cv::COLOR_BayerBG2RGB;
    std::cerr << "Warning: get_ocv_bayer_code_for_rgb() received unknown Pylon format: " << pylon_format << std::endl;
    return -1;
}

// --- Functions Exposed to Python ---

// Initialize camera - unchanged from previous working versions
bool initialize_camera() {
    std::cout << "[C++] initialize_camera called." << std::endl;
    if (camera != nullptr && camera->IsOpen()) { std::cerr << "[C++] Warning: Camera already initialized." << std::endl; return true; }
    try {
        if (!pylonInitialized) { std::cout << "[C++] Initializing Pylon runtime..." << std::endl; Pylon::PylonInitialize(); pylonInitialized = true; std::cout << "[C++] Pylon runtime initialized." << std::endl; }
        else { std::cout << "[C++] Pylon runtime already initialized." << std::endl; }
        std::cout << "[C++] Creating camera object..." << std::endl; Pylon::CTlFactory& tlFactory = Pylon::CTlFactory::GetInstance(); Pylon::DeviceInfoList_t devices;
        if (tlFactory.EnumerateDevices(devices) == 0) { throw std::runtime_error("[C++] No camera devices found."); }
        camera = new Pylon::CInstantCamera(tlFactory.CreateDevice(devices[0])); std::cout << "[C++] Camera object created." << std::endl; std::cout << "[C++] Using device " << camera->GetDeviceInfo().GetModelName() << std::endl;
        std::cout << "[C++] Opening camera..." << std::endl; camera->Open(); std::cout << "[C++] Camera opened." << std::endl;
        std::cout << "[C++] Getting node map..." << std::endl; GenApi::INodeMap& nodemap = camera->GetNodeMap(); std::cout << "[C++] Node map obtained." << std::endl;
        std::cout << "[C++] Applying final configuration..." << std::endl;
        // --- Camera Settings ---
        try { Pylon::CEnumParameter(nodemap, "PixelFormat").FromString("BayerGB12"); std::cout << " -> PixelFormat=BayerGB12 OK" << std::endl; } catch(const std::exception& e) { std::cerr << "Warn: PixelFormat: " << e.what() << std::endl; } // Use GBRG
        try { Pylon::CBooleanParameter(nodemap, "ProcessedRawEnable").SetValue(false); std::cout << " -> ProcessedRawEnable=false OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: ProcessedRawEnable: " << e.what() << std::endl; }
        try { Pylon::CEnumParameter(nodemap, "GainAuto").FromString("Off"); std::cout << " -> GainAuto=Off OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: GainAuto: " << e.what() << std::endl; }
        try { const int gain_raw_value = 300; Pylon::CIntegerParameter(nodemap, "GainRaw").SetValue(gain_raw_value); std::cout << " -> GainRaw=" << Pylon::CIntegerParameter(nodemap, "GainRaw").GetValue() << " OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: GainRaw: " << e.what() << std::endl; }
        try { Pylon::CIntegerParameter(nodemap, "GevSCPSPacketSize").SetValue(9000); std::cout << " -> Packet Size OK" << std::endl; } catch(const std::exception& e) { std::cerr << "Warn: GevSCPSPacketSize: " << e.what() << std::endl; }
        try { const int target_width = 2048; Pylon::CIntegerParameter(nodemap, "Width").SetValue(target_width); std::cout << " -> Width=" << Pylon::CIntegerParameter(nodemap, "Width").GetValue() << " OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: Width: " << e.what() << std::endl; }
        try { const int target_height = 1108; Pylon::CIntegerParameter(nodemap, "Height").SetValue(target_height); std::cout << " -> Height=" << Pylon::CIntegerParameter(nodemap, "Height").GetValue() << " OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: Height: " << e.what() << std::endl; }
        try { Pylon::CBooleanParameter(nodemap, "CenterX").SetValue(true); std::cout << " -> CenterX OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: CenterX: " << e.what() << std::endl; }
        try { Pylon::CBooleanParameter(nodemap, "CenterY").SetValue(true); std::cout << " -> CenterY OK" << std::endl;} catch(const std::exception& e) { std::cerr << "Warn: CenterY: " << e.what() << std::endl; }
        try { std::cout << "[C++] Setting BlackLevelRaw..." << std::endl; try { Pylon::CEnumParameter(nodemap, "BlackLevelSelector").FromString("All"); } catch(...) {} Pylon::CIntegerParameter(nodemap, "BlackLevelRaw").SetValue(32); std::cout << " -> BlackLevelRaw=" << Pylon::CIntegerParameter(nodemap, "BlackLevelRaw").GetValue() << " OK" << std::endl; } catch (const GenICam::GenericException &e) { std::cerr << "Warn: BlackLevelRaw: " << e.GetDescription() << std::endl;}
        try { std::cout << "[C++] Setting AutoFunctionProfile..." << std::endl; Pylon::CEnumParameter(nodemap, "AutoFunctionProfile").FromString("GainMinimum"); std::cout << " -> AutoFunctionProfile set to: " << Pylon::CEnumParameter(nodemap, "AutoFunctionProfile").ToString() << std::endl; } catch (const GenICam::GenericException &e) { std::cerr << "Warn: AutoFunctionProfile: " << e.GetDescription() << std::endl;}
        try { std::cout << "[C++] Setting ExposureMode to Timed..." << std::endl; Pylon::CEnumParameter(nodemap, "ExposureMode").FromString("Timed"); std::cout << " -> ExposureMode set to: " << Pylon::CEnumParameter(nodemap, "ExposureMode").ToString() << std::endl;} catch (const GenICam::GenericException &e) { std::cerr << "ERROR: Could not set ExposureMode: " << e.GetDescription() << std::endl; throw; }
        try { Pylon::CEnumParameter(nodemap, "ExposureAuto").FromString("Off"); std::cout << " -> ExposureAuto Off OK" << std::endl;} catch (const GenICam::GenericException &e) { std::cerr << "Warn: ExposureAuto: " << e.GetDescription() << std::endl;}
        try { int exposure_us_value = static_cast<int>(std::round(1000000.0 / (2.0 * TARGET_FPS))); std::cout << "[C++] Setting ExposureTimeRaw to " << exposure_us_value << " us..." << std::endl; Pylon::CIntegerParameter(nodemap, "ExposureTimeRaw").SetValue(exposure_us_value); std::cout << " -> ExposureTimeRaw=" << Pylon::CIntegerParameter(nodemap, "ExposureTimeRaw").GetValue() << " OK" << std::endl; } catch (const GenICam::GenericException &e) { std::cerr << "Warn: ExposureTimeRaw failed: " << e.GetDescription() << std::endl; }
        try { Pylon::CBooleanParameter(nodemap, "AcquisitionFrameRateEnable").SetValue(true); std::cout << " -> FrameRateEnable OK" << std::endl;} catch (const GenICam::GenericException &e) { std::cerr << "Warn: FrameRateEnable: " << e.GetDescription() << std::endl;}
        try { Pylon::CFloatParameter(nodemap, "AcquisitionFrameRateAbs").SetValue(TARGET_FPS); std::cout << " -> FrameRateAbs OK" << std::endl;} catch (const GenICam::GenericException &e) { std::cerr << "Warn: FrameRateAbs: " << e.GetDescription() << std::endl;}
        // --- End Settings ---
        std::cout << "[C++] Starting grabbing..." << std::endl; camera->StartGrabbing(Pylon::EGrabStrategy::GrabStrategy_LatestImageOnly); std::cout << "[C++] Camera initialized and grabbing started successfully." << std::endl; return true;
    } catch (const GenICam::GenericException &e) { std::cerr << "[C++] GenICam Ex: " << e.GetDescription() << std::endl; if (camera != nullptr) { if (camera->IsOpen()) camera->Close(); delete camera; camera = nullptr; } return false;
    } catch (const std::exception &e) { std::cerr << "[C++] Std Ex: " << e.what() << std::endl; if (camera != nullptr) { if (camera->IsOpen()) camera->Close(); delete camera; camera = nullptr; } return false;
    } catch (...) { std::cerr << "[C++] Unknown ex." << std::endl; if (camera != nullptr) { if (camera->IsOpen()) camera->Close(); delete camera; camera = nullptr; } return false; }
}


// Grab and process frame, returning preview and UNSCALED raw
std::pair<cv::Mat, cv::Mat> grab_preview_and_raw() {
    if (camera == nullptr || !camera->IsGrabbing()) { return std::make_pair(cv::Mat(), cv::Mat()); }

    Pylon::CGrabResultPtr grabResult;
    cv::Mat preview_frame; // Resized RGB frame for preview
    cv::Mat raw_frame;     // Full resolution 16-bit raw Bayer frame (unscaled)

    try {
        camera->RetrieveResult(5000, grabResult, Pylon::TimeoutHandling_ThrowException);

        if (grabResult->GrabSucceeded()) {
            int width = grabResult->GetWidth(); int height = grabResult->GetHeight(); const void* pImageBuffer = grabResult->GetBuffer();
            std::string pylonFormat = Pylon::CEnumParameter(camera->GetNodeMap(), "PixelFormat").ToString().c_str();
            int cvBayerCode = get_ocv_bayer_code_for_rgb(pylonFormat); // Use code matching Pylon format
            if (cvBayerCode == -1) { std::cerr << "Err: Unsupported Bayer fmt for color preview: " << pylonFormat << std::endl; return std::make_pair(cv::Mat(), cv::Mat()); }

            // --- Prepare RAW frame (Unscaled, MSB aligned) ---
            // Assuming 12-bit or similar packed into 16-bit container
             if (pylonFormat.find("Bayer") != std::string::npos && (pylonFormat.find("12") != std::string::npos || pylonFormat.find("10") != std::string::npos || pylonFormat.find("16") != std::string::npos)) {
                 // Create a Mat header pointing to the Pylon buffer (no copy yet)
                 cv::Mat raw_bayer_mat_16u = cv::Mat(height, width, CV_16UC1, const_cast<void*>(pImageBuffer)); // Use const_cast if buffer is const

                 // *** Clone the raw data directly (NO SCALING) ***
                 raw_frame = raw_bayer_mat_16u.clone();

                 // --- Prepare PREVIEW frame (Scale for 8-bit display) ---
                 cv::Mat raw_bayer_8bit;
                 // Scale MSB-aligned data down for 8-bit visibility (e.g., 12-bit needs /16)
                 double scale_factor_8bit = 1.0;
                 if (pylonFormat.find("12") != std::string::npos) scale_factor_8bit = 1.0 / 16.0; // 2^(16-12) = 16
                 else if (pylonFormat.find("10") != std::string::npos) scale_factor_8bit = 1.0 / 64.0; // 2^(16-10) = 64
                 // Add other bit depths if needed

                 raw_bayer_mat_16u.convertTo(raw_bayer_8bit, CV_8U, scale_factor_8bit);
                 // Debayer 8-bit data using the correct code for the sensor
                 cv::Mat rgb_8bit;
                 cv::cvtColor(raw_bayer_8bit, rgb_8bit, cvBayerCode);
                 // Resize to 720p
                 cv::Size target_size(1024, 600);
                 cv::resize(rgb_8bit, preview_frame, target_size, 0, 0, cv::INTER_NEAREST);

            } else if (pylonFormat.find("8") != std::string::npos) {
                 // Handle 8-bit Bayer case (less common for raw)
                 cv::Mat raw_bayer_8bit_direct = cv::Mat(height, width, CV_8UC1, const_cast<void*>(pImageBuffer));
                 raw_frame = raw_bayer_8bit_direct.clone(); // Save the 8-bit raw directly

                 // Prepare preview frame
                 cv::Mat rgb_8bit;
                 cv::cvtColor(raw_bayer_8bit_direct, rgb_8bit, cvBayerCode);
                 cv::resize(rgb_8bit, preview_frame, cv::Size(1024, 600), 0, 0, cv::INTER_NEAREST);

            } else { std::cerr << "Err: Unhandled pixel format type for raw saving: " << pylonFormat << std::endl; return std::make_pair(cv::Mat(), cv::Mat()); }

        } else { std::cerr << "Err: Grab Failed: " << grabResult->GetErrorCode() << " " << grabResult->GetErrorDescription() << std::endl; return std::make_pair(cv::Mat(), cv::Mat()); }
    // Exception handling
    } catch (const GenICam::GenericException &e) { std::cerr << "Grab GenICam Ex: " << e.GetDescription() << std::endl; return std::make_pair(cv::Mat(), cv::Mat());
    } catch (const std::exception &e) { std::cerr << "Grab Std Ex: " << e.what() << std::endl; return std::make_pair(cv::Mat(), cv::Mat());
    } catch (...) { std::cerr << "Grab Unknown ex." << std::endl; return std::make_pair(cv::Mat(), cv::Mat()); }

    // Return the pair of frames
    return std::make_pair(preview_frame, raw_frame);
}


// Shutdown camera - unchanged
bool shutdown_camera() { std::cout << "[C++] Shutting down camera..." << std::endl; if (camera != nullptr) { try { if (camera->IsGrabbing()) { camera->StopGrabbing(); } if (camera->IsOpen()) { camera->Close(); } } catch (...) { /* Ignore shutdown errors */ } delete camera; camera = nullptr; std::cout << "[C++] Camera object deleted." << std::endl; } else { std::cout << "[C++] Camera pointer null." << std::endl; } std::cout << "[C++] shutdown_camera finished." << std::endl; return true; }

// Gain/Exposure functions - unchanged
int set_gain(int delta) { if (!camera || !camera->IsOpen()) return -1; try { GenApi::INodeMap& n = camera->GetNodeMap(); Pylon::CIntegerParameter p(n,"GainRaw"); int64_t c=p.GetValue(),mn=p.GetMin(),mx=p.GetMax(),v=std::max(mn,std::min(mx,c+static_cast<int64_t>(delta))); p.SetValue(v); std::cout<<"-> Gain="<<v<<std::endl; return (int)v;} catch(...){return -1;} }
int get_gain() { if (!camera || !camera->IsOpen()) return -1; try { return (int)Pylon::CIntegerParameter(camera->GetNodeMap(),"GainRaw").GetValue();} catch(...) {return -1;} }
int get_exposure() { if (!camera || !camera->IsOpen()) return -1; try { return (int)Pylon::CIntegerParameter(camera->GetNodeMap(),"ExposureTimeRaw").GetValue();} catch(...) {return -1;} }

// *** White Balance Function: Trigger AND Return Gains ***
std::pair<double, double> trigger_wb_and_get_gains() {
    if (!camera || !camera->IsOpen()) { std::cerr << "[C++] Error: Camera not open in trigger_wb_and_get_gains" << std::endl; return {-1.0, -1.0}; }
    try {
        GenApi::INodeMap& n = camera->GetNodeMap();
        // Trigger the Auto WB "Once"
        Pylon::CEnumParameter balAuto(n, "BalanceWhiteAuto");
        balAuto.FromString("Off"); // Ensure it's off first
        balAuto.FromString("Once");
        std::cout << "[C++] BalanceWhiteAuto set to Once triggered." << std::endl;

        // Add a small delay to allow camera to calculate WB
        // Adjust this value if needed, might depend on camera model/firmware
        Pylon::WaitObject::Sleep(200); // Wait 200 ms

        // Read the resulting BalanceRatioAbs values (Multipliers relative to Green=1.0)
        double red_gain = 1.0; double blue_gain = 1.0;
        try {
            Pylon::CEnumParameter balRatioSel(n, "BalanceRatioSelector"); // Get selector node
            Pylon::CFloatParameter balRatioAbs(n, "BalanceRatioAbs");     // Get value node

            balRatioSel.FromString("Red"); // Select Red channel
            red_gain = balRatioAbs.GetValue();
            std::cout << "[C++] Read Red Gain: " << red_gain << std::endl;

            balRatioSel.FromString("Blue"); // Select Blue channel
            blue_gain = balRatioAbs.GetValue();
            std::cout << "[C++] Read Blue Gain: " << blue_gain << std::endl;
        } catch (const GenICam::GenericException &e) {
             std::cerr << "[C++] Warn: Could not read one or both BalanceRatioAbs values: " << e.GetDescription() << ". Using defaults." << std::endl;
             // Return default neutral gains if reading fails
             return {1.0, 1.0};
        }

        // Basic validation
        if (red_gain <= 0 || blue_gain <= 0 || !std::isfinite(red_gain) || !std::isfinite(blue_gain) ) {
             std::cerr << "[C++] Error: Invalid gains read after WB (<= 0 or non-finite). R=" << red_gain << ", B=" << blue_gain << ". Returning defaults." << std::endl;
             return {1.0, 1.0}; // Return neutral gains on error
        }

        std::cout << "[C++] WB triggered. Returning gains R=" << red_gain << ", B=" << blue_gain << std::endl;
        return {red_gain, blue_gain};

    } catch (const GenICam::GenericException &e) { std::cerr << "[C++] Error during WB trigger/read: " << e.GetDescription() << std::endl; return {-1.0, -1.0};
    } catch (const std::exception &e) { std::cerr << "[C++] Std Error during WB trigger/read: " << e.what() << std::endl; return {-1.0, -1.0};
    } catch (...) { std::cerr << "[C++] Unknown Error during WB trigger/read." << std::endl; return {-1.0, -1.0}; }
}


// --- Module Definition ---
PYBIND11_MODULE(core_module, m) {
    NDArrayConverter::init_numpy(); // Important for OpenCV Mat <-> NumPy conversion
    m.doc() = "Core C++ module for Bolex camera control and preview";
    // Camera Functions
    m.def("initialize_camera", &initialize_camera, "Initializes the Pylon runtime and the first camera found.");
    m.def("grab_preview_and_raw", &grab_preview_and_raw, "Grabs one frame, returns tuple (720p_RGB_preview, full_res_raw16_MSB_unscaled)"); // Updated doc
    m.def("shutdown_camera", &shutdown_camera, "Stops grabbing, closes camera, and terminates Pylon runtime.");
    // Parameter Control
    m.def("set_gain", &set_gain, "Increases/decreases GainRaw by delta.", py::arg("delta"));
    m.def("get_gain", &get_gain, "Gets the current GainRaw value.");
    m.def("get_exposure", &get_exposure, "Gets the current ExposureTimeRaw value in microseconds.");
    // White Balance
    m.def("trigger_wb_and_get_gains", &trigger_wb_and_get_gains, "Triggers WB Once and returns tuple (red_gain, blue_gain). Returns (1,1) or (-1,-1) on error.");
}
