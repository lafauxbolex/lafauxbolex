# FauxBolex_Beta_0.93.py (Pillow Fonts, 1.85:1 recording, Lossless JPEG compressed RAW DNG, White/Red Box)
import sys, os, cv2, time, numpy as np, queue, threading, traceback
import pidng
from pidng.core import RAW2DNG, DNGTags, Tag
from pidng.defs import CFAPattern, CalibrationIlluminant, DNGVersion, Orientation, PhotometricInterpretation
from datetime import datetime
import pygame 
from PIL import Image, ImageDraw, ImageFont

# --- Path and Module Imports ---
current_dir = os.path.dirname(os.path.abspath(__file__))
cpp_build_dir = os.path.join(current_dir, 'bolex_core_cpp', 'build')
if not os.path.isdir(cpp_build_dir): exit(f"ERROR: Build directory not found: {cpp_build_dir}")
print(f"Adding to sys.path: {cpp_build_dir}")
sys.path.insert(0, cpp_build_dir)
try: import core_module; print("Successfully imported core_module!")
except Exception as e: exit(f"ERROR importing core_module: {e}\n{traceback.format_exc()}")

# --- Recorder Class (From your "Color Science Fixed Version") ---
class Recorder:
    _STOP_SENTINEL = None
    def __init__(self, storage_path: str, cfa_pattern: tuple = (1, 2, 0, 1), wb_gains: list = [1.0, 1.0, 1.0], max_buffer_frames: int = 3000):
            self.storage_path=storage_path; self.file_format="dng"; self.max_buffer_frames=max_buffer_frames; self.cfa_pattern_tuple=cfa_pattern
            self.actual_camera_wb_gains = list(wb_gains) 
            self.wb_gains = list(wb_gains) 
            if not (isinstance(cfa_pattern, tuple) and len(cfa_pattern) == 4): raise ValueError("cfa_pattern must be a tuple of length 4")
            cfa_map = { (1,2,0,1): CFAPattern.GBRG, (1,0,2,1): CFAPattern.GRBG, (0,1,1,2): CFAPattern.RGGB, (2,1,1,0): CFAPattern.BGGR }
            self.cfa_pattern_enum = cfa_map.get(cfa_pattern, CFAPattern.GBRG)
            print(f"Recorder initialized for pidng. Max frames: {self.max_buffer_frames}. CFA: {self.cfa_pattern_enum}. Init Cam WB Gains: {self.actual_camera_wb_gains}")
            try:
                if not os.path.exists(self.storage_path): os.makedirs(self.storage_path); print(f"Created storage dir: {self.storage_path}")
            except OSError as e: print(f"FATAL: No storage dir '{self.storage_path}': {e}"); raise
            self._is_recording=False; self.current_recording_folder=None; self.frame_save_count=0; self.total_frames_added_this_segment=0; self._frame_queue=queue.Queue(); self._save_thread=None
            self.tags = None; self.converter = RAW2DNG(); self.converter_options_set = False

    def update_wb_gains(self, new_gains: list):
        if len(new_gains) == 3 and all(isinstance(g, (float, int)) and g > 1e-9 for g in new_gains):
            self.actual_camera_wb_gains = list(new_gains) 
            self.wb_gains = list(new_gains)
            print(f"Recorder actual camera WB gains updated: R={self.actual_camera_wb_gains[0]:.3f} G={self.actual_camera_wb_gains[1]:.3f} B={self.actual_camera_wb_gains[2]:.3f}")
            if self.tags and self.converter_options_set: 
                try: # As per your working DNG script (forced neutral AsShotNeutral)
                    asn_denominator = 10000 
                    as_shot_neutral_rationals = [[1 * asn_denominator, asn_denominator]] * 3
                    self.tags.set(Tag.AsShotNeutral, as_shot_neutral_rationals)
                    print(f" -> DNG AsShotNeutral forced to neutral (runtime): {as_shot_neutral_rationals}")
                    self.converter.options(self.tags, path="", compress=True)
                    print(" -> Converter DNG options updated with new WB and compression.")
                except Exception as e: print(f"Error updating DNG AsShotNeutral to neutral (runtime): {e}")
        else: print(f"Error: Invalid WB gains format received: {new_gains}")

    def start_recording(self): # Identical
        if self._is_recording: return False
        now=datetime.now(); folder_name=now.strftime("%Y%m%d_%H%M%S"); self.current_recording_folder=os.path.join(self.storage_path, folder_name)
        try: 
            os.makedirs(self.current_recording_folder);
            while not self._frame_queue.empty():
                 try: self._frame_queue.get_nowait()
                 except queue.Empty: break
            self.frame_save_count=0; self.total_frames_added_this_segment=0; self._is_recording=True; self.converter_options_set = False; self.tags = None
            self._save_thread=threading.Thread(target=self._save_worker, name="SaveWorker", daemon=True); self._save_thread.start()
            print(f"Recording started. Saving to: {self.current_recording_folder}"); return True
        except OSError as e: print(f"Error creating recording folder: {e}"); self.current_recording_folder=None; self._is_recording=False; self._save_thread=None; return False

    def stop_recording(self): # Identical
        if not self._is_recording: return
        self._is_recording=False; print(f"Stopping recording. Frames added: {self.total_frames_added_this_segment}. Waiting saver..."); self._frame_queue.put(self._STOP_SENTINEL)
        if self._save_thread is not None and self._save_thread.is_alive():
             join_timeout=30.0; self._save_thread.join(timeout=join_timeout)
             if self._save_thread.is_alive(): print(f"Warn: Saver thread timeout.")
             else: print("Saver thread finished.")
        self.current_recording_folder=None; self._save_thread=None

    def add_frame(self, raw_frame: np.ndarray): # Identical
        if not self._is_recording or raw_frame is None or raw_frame.size == 0: return
        if self.total_frames_added_this_segment>=self.max_buffer_frames:
             if self._is_recording: print(f"Max frames ({self.max_buffer_frames}) reached."); self.stop_recording()
             return
        try: self._frame_queue.put(raw_frame); self.total_frames_added_this_segment += 1
        except Exception as e: print(f"Error queueing frame: {e}")

    def _save_worker(self): # From your "Color Science Fixed Version" script
        print(f"Saver thread started (pidng Mode - Camera Applies WB).")
        frames_processed=0; save_errors=0; worker_active=True
        first_frame_shape = None; debug_first_frame = True; denominator = 1000000
        bolex_stdA_matrix_floats = [1.4296849, -0.7867698, 0.2219452, -0.2511404, 0.9766861, 0.2091821, -0.0839671, 0.1939601, 0.6574579]
        bolex_d65_matrix_floats = [1.4868945, -0.6438222, -0.0699355, -0.261274, 1.0494869, 0.1399011, -0.1775877, 0.313115, 0.4792254]
        bolex_stdA_matrix_rational = [[int(round(f * denominator)), denominator] for f in bolex_stdA_matrix_floats]
        bolex_d65_matrix_rational = [[int(round(f * denominator)), denominator] for f in bolex_d65_matrix_floats]
        try: illuminant_stdA = CalibrationIlluminant.Standard_Light_A; illuminant_d65 = CalibrationIlluminant.D65
        except AttributeError: print("Warning: Using integer fallback for CI values."); illuminant_stdA = 21; illuminant_d65 = 1
        baseline_exposure_float = 1.0; baseline_exposure_srational = [[int(round(baseline_exposure_float * 100)), 100]]
        black_level = 30; white_level = 65520; bits_per_sample = 12
        make = 'LA FAUX BOLEX'; model = 'F16'; cfa_pattern_enum_val = self.cfa_pattern_enum; bayer_green_split = 240
        self.tags = DNGTags()
        self.tags.set(Tag.Make, make); self.tags.set(Tag.Model, model); self.tags.set(Tag.Software, 'DIY CCD CINE CAM v2.1 CamWB')
        self.tags.set(Tag.Orientation, Orientation.Horizontal); self.tags.set(Tag.PhotometricInterpretation, PhotometricInterpretation.Color_Filter_Array)
        self.tags.set(Tag.SamplesPerPixel, 1); self.tags.set(Tag.BitsPerSample, bits_per_sample)
        self.tags.set(Tag.CFARepeatPatternDim, [2, 2]); self.tags.set(Tag.CFAPattern, cfa_pattern_enum_val); self.tags.set(Tag.CFAPlaneColor, [0, 1, 2])
        self.tags.set(Tag.BlackLevel, black_level); self.tags.set(Tag.WhiteLevel, white_level)
        self.tags.set(Tag.ColorMatrix1, bolex_stdA_matrix_rational); self.tags.set(Tag.ColorMatrix2, bolex_d65_matrix_rational)
        self.tags.set(Tag.CalibrationIlluminant1, illuminant_stdA); self.tags.set(Tag.CalibrationIlluminant2, illuminant_d65)
        self.tags.set(Tag.BaselineExposure, baseline_exposure_srational); self.tags.set(Tag.BayerGreenSplit, bayer_green_split)
        initial_exposure_us = -1; 
        try: initial_exposure_us = core_module.get_exposure(); 
        except Exception: pass
        if initial_exposure_us > 0: exposure_s = initial_exposure_us / 1_000_000.0; exp_num = int(round(exposure_s * 1000000)); exp_den = 1000000; self.tags.set(Tag.ExposureTime, [[exp_num, exp_den]])
        self.tags.set(Tag.DNGVersion, DNGVersion.V1_4); self.tags.set(Tag.DNGBackwardVersion, DNGVersion.V1_2)
        self.tags.set(Tag.UniqueCameraModel, make)
        self.converter = RAW2DNG(); self.converter_options_set = False
        while worker_active:
            try:
                frame_data = self._frame_queue.get()
                if frame_data is self._STOP_SENTINEL: worker_active=False; self._frame_queue.task_done(); print(f"Saver stop signal..."); break
                if not self.converter_options_set:
                    if frame_data is not None and frame_data.size > 0:
                        first_frame_shape = frame_data.shape; print(f" -> Detected frame shape: {first_frame_shape}")
                        height, width = first_frame_shape
                        self.tags.set(Tag.ImageWidth, int(width)); self.tags.set(Tag.ImageLength, int(height))
                        self.tags.set(Tag.DefaultCropOrigin, (0, 0)); self.tags.set(Tag.DefaultCropSize, (int(height), int(width)))
                        try: # AsShotNeutral forced to neutral
                            asn_denominator = 10000; as_shot_neutral_rationals = [[1*asn_denominator, asn_denominator]]*3
                            self.tags.set(Tag.AsShotNeutral, as_shot_neutral_rationals)
                            print(f" -> DNG AsShotNeutral forced to neutral (initial set): {as_shot_neutral_rationals}")
                        except Exception as wb_e: print(f"Warn: Error setting forced neutral AsShotNeutral: {wb_e}"); self.tags.set(Tag.AsShotNeutral, [[10000,10000]]*3)
                        self.converter.options(self.tags, path="", compress=True); self.converter_options_set = True
                        print(f"Saver starting frame {self.frame_save_count}...")
                    else: self._frame_queue.task_done(); continue
                if not self.converter_options_set: self._frame_queue.task_done(); continue
                if self.current_recording_folder and frame_data is not None and frame_data.size > 0 and first_frame_shape is not None:
                    if debug_first_frame:
                        debug_first_frame = False
                    filename=f"frame_{self.frame_save_count:06d}"; filepath_no_ext = os.path.join(self.current_recording_folder, filename)
                    try:
                        if frame_data.dtype != np.uint16: frame_data = frame_data.astype(np.uint16)
                        if frame_data.shape != first_frame_shape: raise ValueError("Frame shape mismatch!")
                        self.converter.convert(frame_data, filename=filepath_no_ext)
                        self.frame_save_count += 1; frames_processed += 1
                    except Exception as e: print(f"ERROR saving DNG {filepath_no_ext}.dng: {e}\n{traceback.format_exc()}"); save_errors += 1
                else: print("Saver skip item.")
                self._frame_queue.task_done()
            except queue.Empty: time.sleep(0.005)
            except Exception as e: print(f"FATAL error in saver thread: {e}\n{traceback.format_exc()}"); save_errors += 1; worker_active = False
        print(f"Saver thread exiting. Processed: {frames_processed}, Errors: {save_errors}")

    def is_recording(self) -> bool: return self._is_recording
    def get_queue_size(self) -> int: return self._frame_queue.qsize()
# ---------------------------------------

# --- Initialize Camera, Recorder (Identical to your baseline) ---
print("Initializing camera via C++ module...")
if not core_module.initialize_camera(): exit("Failed to initialize camera.")
print("Camera initialization successful (C++).")
try:
    assumed_cfa_tuple = (1, 2, 0, 1); print(f"Using CFA Pattern Tuple for DNG: {assumed_cfa_tuple}")
    recorder = Recorder( storage_path="/home/ooze3d/digitalbolex/storage/", cfa_pattern=assumed_cfa_tuple, wb_gains=[1.0, 1.0, 1.0] )
except Exception as e: exit(f"FATAL: Could not initialize Recorder: {e}")

# --- Pillow Font UI Setup ---
ui_font_main = None; ui_font_status = None
try:
    script_dir = os.path.dirname(os.path.abspath(__file__)) 
    font_file_name = "RobotoCondensed-Regular.ttf" 
    font_path_roboto_condensed = os.path.join(script_dir, "fonts", font_file_name) 
    font_size_main_info = 22; font_size_status_info = 18
    if os.path.exists(font_path_roboto_condensed):
        ui_font_main = ImageFont.truetype(font_path_roboto_condensed, font_size_main_info)
        ui_font_status = ImageFont.truetype(font_path_roboto_condensed, font_size_status_info)
        print(f"Custom font '{font_path_roboto_condensed}' loaded successfully.")
    else: print(f"Error: Font file not found at '{font_path_roboto_condensed}'. OpenCV fonts will be used.")
except IOError as e: print(f"Error loading font '{font_path_roboto_condensed}': {e}. OpenCV fonts will be used.")

TEXT_COLOR_PIL_MAIN = (200, 200, 200); TEXT_COLOR_PIL_STATUS = (200, 200, 200); RECORD_DOT_COLOR_PIL = (0, 0, 200)
TEXT_COLOR_CV_MAIN = (200, 200, 200); TEXT_COLOR_CV_STATUS = (200, 200, 200); RECORD_DOT_COLOR_CV = (200, 0, 0)
CLIPPING_COLOR_CV_BGR = (155, 0, 0) 

# --- Define UI Element Constants (Including Frame Guide) ---
PREVIEW_CONTENT_WIDTH = 1024
PREVIEW_CONTENT_HEIGHT = 600

# Frame Guide Colors (Pillow RGB)
FRAME_GUIDE_BORDER_THICKNESS = 8 
FRAME_GUIDE_COLOR_STANDBY_PIL = (200, 200, 200) # White
FRAME_GUIDE_COLOR_RECORDING_PIL = (0, 0, 200)   # Red

# Frame Guide Colors (OpenCV BGR - for fallback)
FRAME_GUIDE_COLOR_STANDBY_CV_BGR = (FRAME_GUIDE_COLOR_STANDBY_PIL[2], FRAME_GUIDE_COLOR_STANDBY_PIL[1], FRAME_GUIDE_COLOR_STANDBY_PIL[0])
FRAME_GUIDE_COLOR_RECORDING_CV_BGR = (FRAME_GUIDE_COLOR_RECORDING_PIL[2], FRAME_GUIDE_COLOR_RECORDING_PIL[1], FRAME_GUIDE_COLOR_RECORDING_PIL[0])

LETTERBOX_DARKEN_FACTOR = 0.5 # 0.0 (black) to 1.0 (no change)

# --- Calculate 2.39:1 Frame Guide Dimensions (ONCE) ---
FRAME_GUIDE_ASPECT_RATIO = 2.39
# PREVIEW_CONTENT_WIDTH and PREVIEW_CONTENT_HEIGHT should be defined before this point
FG_HEIGHT = int(round(PREVIEW_CONTENT_WIDTH / FRAME_GUIDE_ASPECT_RATIO))
# Ensure even number for simple centering, though //2 handles odd/even for top_y
if FG_HEIGHT % 2 != 0:
    FG_HEIGHT -= 1 

FG_TOP_Y = (PREVIEW_CONTENT_HEIGHT - FG_HEIGHT) // 2
FG_BOTTOM_Y = FG_TOP_Y + FG_HEIGHT
FG_LEFT_X = 0 # Or a small margin like FRAME_GUIDE_BORDER_THICKNESS // 2
FG_RIGHT_X = PREVIEW_CONTENT_WIDTH # Or PREVIEW_CONTENT_WIDTH - (FRAME_GUIDE_BORDER_THICKNESS // 2)
# For precise border placement with Pillow's width parameter, using 0 and PREVIEW_CONTENT_WIDTH is fine.

print(f"Frame Guide Calculated: X={FG_LEFT_X}-{FG_RIGHT_X}, Y={FG_TOP_Y}-{FG_BOTTOM_Y}, Height={FG_HEIGHT}")

# --- Config, Window, Gamepad Init (Identical to your baseline) ---
WINDOW_NAME = "Faux Bolex Camera UI"; DISPLAY_WIDTH = 1024; DISPLAY_HEIGHT = 600;
CLIPPING_THRESHOLD = 245; TARGET_FPS_FOR_ANGLE = 24.0; show_clipping = False
cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
try: cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
except cv2.error as e: print(f"Warn: Fullscreen property failed: {e}")
pygame.init(); pygame.joystick.init(); gamepad = None
joystick_count = pygame.joystick.get_count()
if joystick_count > 0: gamepad = pygame.joystick.Joystick(0); gamepad.init(); print(f"Gamepad '{gamepad.get_name()}' init.")
else: print("No gamepad detected.")
print("Starting preview loop...")
is_running = True; is_recording = False
last_fps_time = time.monotonic(); frame_count = 0; display_fps = 0.0
current_gain = -1; current_exposure = -1; shutter_angle_str = "ANGLE: N/A"

# --- Main Loop ---
while is_running:
    try:
        loop_start_time = time.monotonic()
        preview_frame_rgb_from_cpp, raw_frame = core_module.grab_preview_and_raw() # This IS RGB
        
        frame_to_display = None # This will be the final frame for cv2.imshow

        if preview_frame_rgb_from_cpp is not None and preview_frame_rgb_from_cpp.size > 0:
            # --- Calculate dynamic text values ---
            if is_recording and raw_frame is not None and raw_frame.size > 0: recorder.add_frame(raw_frame)
            frame_count += 1; now = time.monotonic(); elapsed_fps = now - last_fps_time
            if elapsed_fps >= 1.0: display_fps = frame_count / elapsed_fps; frame_count = 0; last_fps_time = now
            current_gain = core_module.get_gain(); current_exposure = core_module.get_exposure()
            if current_exposure > 0: angle = (current_exposure / 1_000_000.0) * TARGET_FPS_FOR_ANGLE * 360.0; shutter_angle_str = f"ANGLE: {angle:.0f}"
            else: shutter_angle_str = "ANGLE: N/A"
            
            # --- Frame preparation for drawing overlays ---
            # Start with the RGB frame from C++. Make a copy for modifications.
            overlay_target_rgb = preview_frame_rgb_from_cpp.copy()

            # Apply OpenCV-based clipping overlay IF active, directly on the RGB NumPy array
            if show_clipping:
                clipped_mask = np.any(overlay_target_rgb > CLIPPING_THRESHOLD, axis=2)
                clipping_color_rgb_overlay = (CLIPPING_COLOR_CV_BGR[2], CLIPPING_COLOR_CV_BGR[1], CLIPPING_COLOR_CV_BGR[0]) # Convert BGR to RGB
                overlay_target_rgb[clipped_mask] = clipping_color_rgb_overlay

            if LETTERBOX_DARKEN_FACTOR < 1.0: 
                if FG_TOP_Y > 0:
                    overlay_target_rgb[0:FG_TOP_Y, :] = \
                        (overlay_target_rgb[0:FG_TOP_Y, :] * LETTERBOX_DARKEN_FACTOR).astype(np.uint8)
                if FG_BOTTOM_Y < PREVIEW_CONTENT_HEIGHT:
                    overlay_target_rgb[FG_BOTTOM_Y:PREVIEW_CONTENT_HEIGHT, :] = \
                        (overlay_target_rgb[FG_BOTTOM_Y:PREVIEW_CONTENT_HEIGHT, :] * LETTERBOX_DARKEN_FACTOR).astype(np.uint8)

            if ui_font_main and ui_font_status: # ---- USE PILLOW IF FONTS LOADED ----
                pil_image = Image.fromarray(overlay_target_rgb) # Pass RGB to Pillow
                draw = ImageDraw.Draw(pil_image)

                # --- Draw 2.39:1 Frame Guide Border (uses pre-calculated FG_ constants) ---
                current_frame_guide_color_pil = FRAME_GUIDE_COLOR_RECORDING_PIL if is_recording else FRAME_GUIDE_COLOR_STANDBY_PIL

                draw.rectangle((FG_LEFT_X, FG_TOP_Y, FG_RIGHT_X -1 , FG_BOTTOM_Y -1), outline=current_frame_guide_color_pil, width=FRAME_GUIDE_BORDER_THICKNESS)
                
                text_y_start = 15; text_x_margin = 15
                try: # Robust way to get line height
                    text_bbox_test = draw.textbbox((0,0), "Tg", font=ui_font_main)
                    line_height = text_bbox_test[3] - text_bbox_test[1] + 8 
                except AttributeError: # Fallback for older Pillow
                    line_height = font_size_main_info + 5

                fps_text = f'FPS: {display_fps:.1f}'
                draw.text((text_x_margin, text_y_start), fps_text, font=ui_font_main, fill=TEXT_COLOR_PIL_MAIN)
                
                gain_text_str = f"GAIN: {current_gain}" if current_gain != -1 else "GAIN: N/A"
                try: gain_bbox = draw.textbbox((0,0), gain_text_str, font=ui_font_main); draw.text((DISPLAY_WIDTH-(gain_bbox[2]-gain_bbox[0])-text_x_margin, text_y_start), gain_text_str,font=ui_font_main,fill=TEXT_COLOR_PIL_MAIN)
                except AttributeError: draw.text((DISPLAY_WIDTH - 200 - text_x_margin, text_y_start), gain_text_str, font=ui_font_main, fill=TEXT_COLOR_PIL_MAIN)

                angle_y_pos = text_y_start + line_height
                try: angle_bbox = draw.textbbox((0,0), shutter_angle_str, font=ui_font_main); draw.text((DISPLAY_WIDTH-(angle_bbox[2]-angle_bbox[0])-text_x_margin, angle_y_pos), shutter_angle_str,font=ui_font_main,fill=TEXT_COLOR_PIL_MAIN)
                except AttributeError: draw.text((DISPLAY_WIDTH - 200 - text_x_margin, angle_y_pos), shutter_angle_str, font=ui_font_main, fill=TEXT_COLOR_PIL_MAIN)
                
                try: 
                    status_font_bbox_test = draw.textbbox((0,0), "Q", font=ui_font_status) # For height
                    status_font_height = status_font_bbox_test[3] - status_font_bbox_test[1]
                except AttributeError: 
                    status_font_height = font_size_status_info # Fallback height
                
                status_y_pos = PREVIEW_CONTENT_HEIGHT - status_font_height - 10 # Common Y for bottom line
                
                clip_status_text_str = f"CLIP: {'ON' if show_clipping else 'OFF'}"
                try:
                    clip_bbox = draw.textbbox((0,0), clip_status_text_str, font=ui_font_status)
                    clip_text_width = clip_bbox[2] - clip_bbox[0]
                    draw.text((PREVIEW_CONTENT_WIDTH - clip_text_width - text_x_margin, status_y_pos), clip_status_text_str, font=ui_font_status, fill=TEXT_COLOR_PIL_STATUS)
                except AttributeError: # Fallback for older Pillow if textbbox not available
                    # Estimate width or use a fixed offset if textbbox fails
                    draw.text((PREVIEW_CONTENT_WIDTH - 100 - text_x_margin, status_y_pos), clip_status_text_str, font=ui_font_status, fill=TEXT_COLOR_PIL_STATUS)
                
                if is_recording: # Only show queue size if recording
                    queue_text_str = f"Q: {recorder.get_queue_size()}"
                    draw.text((text_x_margin, status_y_pos), queue_text_str, font=ui_font_status, fill=TEXT_COLOR_PIL_STATUS)
                    #dot_radius = 8 
                    #draw.ellipse((DISPLAY_WIDTH-dot_radius*2-text_x_margin, status_y_start+status_font_height//2-dot_radius, DISPLAY_WIDTH-text_x_margin, status_y_start+status_font_height//2+dot_radius), fill=RECORD_DOT_COLOR_PIL)
                else:
                    current_frame_guide_color_pil = FRAME_GUIDE_COLOR_STANDBY_PIL   # White
                # Pillow image is RGB. If imshow on your system displays RGB correctly, pass it directly.
                frame_to_display = np.array(pil_image) # This is RGB

            else: # ---- FALLBACK TO OPENCV HERSHEY FONTS ----
                # overlay_target_rgb is RGB. If imshow displays RGB correctly, pass it.
                # cv2.putText expects BGR and BGR colors. So convert for drawing, then convert back IF NEEDED for imshow.
                # However, your baseline script passed an RGB frame to cv2.putText and cv2.imshow and colors were fine.
                # This means cv2.putText was likely drawing with swapped colors on the RGB frame,
                # or cv2.imshow on your system was re-interpreting.

                # Let's try to replicate your baseline's direct drawing on what we assume is RGB.
                # The FONT_COLOR_RGB in your baseline was (0, 255, 255) - which is Cyan in RGB, Yellow in BGR.
                # If preview was perfect, then C++ was RGB, and cv2.putText was drawing "BGR-ordered colors" onto an RGB frame,
                # and cv2.imshow displayed that RGB frame correctly.

                frame_to_display = overlay_target_rgb # This is RGB
                font_cv = cv2.FONT_HERSHEY_SIMPLEX; font_scale_cv = 0.8; font_thickness_cv = 2; # From your baseline
                # Using your original FONT_COLOR_RGB which was (0,255,255)
                # This is Cyan in RGB. If it looked Yellow, then frame was BGR or imshow swapped.
                # Assuming your C++ preview frame IS RGB.
                # TEXT_COLOR_CV_MAIN, _STATUS, _DOT_CV are defined as BGR. Let's use RGB equivalents if drawing on RGB frame.
                cv_main_color_rgb = (TEXT_COLOR_CV_MAIN[2], TEXT_COLOR_CV_MAIN[1], TEXT_COLOR_CV_MAIN[0])
                cv_status_color_rgb = (TEXT_COLOR_CV_STATUS[2], TEXT_COLOR_CV_STATUS[1], TEXT_COLOR_CV_STATUS[0])
                cv_dot_color_rgb = (RECORD_DOT_COLOR_CV[2], RECORD_DOT_COLOR_CV[1], RECORD_DOT_COLOR_CV[0])

                cv2.putText(frame_to_display, f'FPS: {display_fps:.1f}', (15, 30), font_cv, font_scale_cv, cv_main_color_rgb, font_thickness_cv, cv2.LINE_AA)
                gain_text_cv = f"GAIN(CV2): {current_gain}" if current_gain != -1 else "GAIN: N/A"; text_size_gain_cv, _ = cv2.getTextSize(gain_text_cv, font_cv, font_scale_cv, font_thickness_cv); cv2.putText(frame_to_display, gain_text_cv, (DISPLAY_WIDTH - text_size_gain_cv[0] - 15, 30), font_cv, font_scale_cv, cv_main_color_rgb, font_thickness_cv, cv2.LINE_AA)
                angle_y_pos_cv = 30 + text_size_gain_cv[1] + 15; text_size_angle_cv, _ = cv2.getTextSize(shutter_angle_str, font_cv, font_scale_cv, font_thickness_cv); cv2.putText(frame_to_display, shutter_angle_str, (DISPLAY_WIDTH - text_size_angle_cv[0] - 15, angle_y_pos_cv), font_cv, font_scale_cv, cv_main_color_rgb, font_thickness_cv, cv2.LINE_AA)
                clip_status_text_cv = f"CLIP: {'ON' if show_clipping else 'OFF'}"; clip_y_pos_cv = DISPLAY_HEIGHT - 20
                if is_recording:
                    cv2.circle(frame_to_display, (DISPLAY_WIDTH - 12 - 15, DISPLAY_HEIGHT - 12 - 15), 12, cv_dot_color_rgb, -1)
                    queue_text_cv = f"Q: {recorder.get_queue_size()}"; cv2.putText(frame_to_display, queue_text_cv, (15, DISPLAY_HEIGHT - 20), font_cv, font_scale_cv * 0.9, cv_status_color_rgb, font_thickness_cv, cv2.LINE_AA); clip_y_pos_cv -= 25
                cv2.putText(frame_to_display, clip_status_text_cv, (15, clip_y_pos_cv), font_cv, font_scale_cv*0.9, cv_status_color_rgb, font_thickness_cv, cv2.LINE_AA)
        else: 
            frame_to_display = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8) # Black BGR
            no_signal_text_cv = "NO SIGNAL"
            if ui_font_main: # Try Pillow for "NO SIGNAL" on RGB
                pil_black = Image.new("RGB", (DISPLAY_WIDTH, DISPLAY_HEIGHT), (0,0,0))
                draw_black = ImageDraw.Draw(pil_black)
                try:
                    bbox = draw_black.textbbox((0,0), no_signal_text_cv, font=ui_font_main); draw_black.text(((DISPLAY_WIDTH-(bbox[2]-bbox[0]))//2, (DISPLAY_HEIGHT-(bbox[3]-bbox[1]))//2), no_signal_text_cv, font=ui_font_main, fill=(255,0,0))
                except AttributeError: draw_black.text((DISPLAY_WIDTH//2-70, DISPLAY_HEIGHT//2-10), no_signal_text_cv, font=ui_font_main, fill=(255,0,0))
                frame_to_display = np.array(pil_black) # RGB for imshow
            else: # OpenCV fallback needs BGR for putText, then convert to RGB for imshow if needed
                  # Or draw with RGB colors if imshow takes RGB and putText handles it.
                  # For simplicity, let's assume imshow takes RGB, and putText will draw on RGB.
                  # TEXT_COLOR_CV_MAIN is BGR. (0,0,255) is BGR Red.
                  cv2.putText(frame_to_display, no_signal_text_cv, (DISPLAY_WIDTH//2-100, DISPLAY_HEIGHT//2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255,0,0), 2, cv2.LINE_AA) # Draw Blue text on RGB frame
            time.sleep(0.05)
        
        if frame_to_display is not None:
            # Based on your finding, imshow on your system needs RGB for correct colors.
            # The frame_to_display should be RGB at this point from both Pillow and OpenCV fallback paths.
            cv2.imshow(WINDOW_NAME, frame_to_display) 
        
        # Gamepad & Keyboard Event Handling (Identical)
        BUTTON_RECORD_TOGGLE = 11 ; BUTTON_CLIPPING_TOGGLE = 7; BUTTON_GAIN_UP = 8; BUTTON_GAIN_DOWN = 9; BUTTON_WHITE_BALANCE = 10 
        if gamepad:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: is_running = False
                if event.type == pygame.JOYBUTTONDOWN:
                    if event.button == BUTTON_RECORD_TOGGLE: is_recording = not is_recording; print(f"Gamepad: R/S. State: {is_recording}"); (recorder.start_recording() if is_recording else recorder.stop_recording())
                    elif event.button == BUTTON_CLIPPING_TOGGLE: show_clipping = not show_clipping; print(f"Gamepad: Clip. State: {'ON' if show_clipping else 'OFF'}")
                    elif event.button == BUTTON_GAIN_UP: print("Gamepad: Gain Up"); core_module.set_gain(10)
                    elif event.button == BUTTON_GAIN_DOWN: print("Gamepad: Gain Down"); core_module.set_gain(-10)
                    elif event.button == BUTTON_WHITE_BALANCE: print("Gamepad: WB"); wb_result=core_module.trigger_wb_and_get_gains(); r_gain,b_gain=wb_result if wb_result and wb_result[0]>0 else (None,None); recorder.update_wb_gains([r_gain,1.0,b_gain]) if r_gain else print(" -> Warn: No valid WB")
        key = cv2.waitKey(1) & 0xFF
        if key == 27: is_running = False; print("ESC exit")
        elif key == ord('r'): is_recording = not is_recording; print(f"Key: R/S. State: {is_recording}"); (recorder.start_recording() if is_recording else recorder.stop_recording())
        elif key == ord('+'): print("Key: Gain Up"); core_module.set_gain(10)
        elif key == ord('-'): print("Key: Gain Down"); core_module.set_gain(-10)
        elif key == ord('w'): print("Key: WB"); wb_result=core_module.trigger_wb_and_get_gains(); r_gain,b_gain=wb_result if wb_result and wb_result[0]>0 else (None,None); recorder.update_wb_gains([r_gain,1.0,b_gain]) if r_gain else print(" -> Warn: No valid WB")
        elif key == ord('c'): show_clipping = not show_clipping; print(f"Key: Clip. State: {'ON' if show_clipping else 'OFF'}")
    except Exception as loop_exception: print(f"ERROR loop: {loop_exception}\n{traceback.format_exc()}"); is_running = False

# --- Shutdown & Cleanup (Identical) ---
if gamepad: pygame.joystick.quit(); pygame.quit(); print("Gamepad uninit.") 
print("Exiting main loop..."); recorder.stop_recording() if 'recorder' in locals() and recorder.is_recording() else None
try: print("Shutting down camera..."); core_module.shutdown_camera(); print("Camera shutdown.")
except Exception as shutdown_exc: print(f"Error C++ shutdown: {shutdown_exc}")
cv2.destroyAllWindows(); print("Script finished.")
try: sys.path.remove(cpp_build_dir)
except ValueError: pass
