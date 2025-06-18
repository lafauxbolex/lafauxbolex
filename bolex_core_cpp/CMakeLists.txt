# CMakeLists.txt (Complete - Manual Pylon Finding - Correct Case)
cmake_minimum_required(VERSION 3.12)
project(BolexCore LANGUAGES CXX)

# Find Python
find_package(Python COMPONENTS Interpreter Development REQUIRED)

# Fetch Dependencies using CMake FetchContent
include(FetchContent)

# --- Fetch pybind11 ---
FetchContent_Declare(
  pybind11
  GIT_REPOSITORY https://github.com/pybind/pybind11.git
  GIT_TAG        v2.11 # Use a consistent tag
  GIT_SHALLOW    TRUE
)

# --- Fetch edmBernard/pybind11_opencv_numpy ---
FetchContent_Declare(
  pybind11_opencv_numpy # Logical name for CMake
  GIT_REPOSITORY https://github.com/edmBernard/pybind11_opencv_numpy.git
  GIT_TAG        master # Or a specific release tag if available
  GIT_SHALLOW    TRUE
)

# Make ONLY pybind11 available (which runs its CMake logic)
FetchContent_MakeAvailable(pybind11)

# Manually get properties of the downloaded helper library (pybind11_opencv_numpy)
FetchContent_GetProperties(pybind11_opencv_numpy)
if(NOT pybind11_opencv_numpy_POPULATED)
    FetchContent_Populate(pybind11_opencv_numpy)
endif()
# -------------------------------------------------------------------

# Find OpenCV
find_package(OpenCV REQUIRED COMPONENTS core imgproc)

# --- Find Pylon (More Manual Approach - Correct Case) ---
set(PYLON_ROOT "/opt/pylon" CACHE PATH "Root directory of the Pylon SDK installation")
message(STATUS "Using PYLON_ROOT: ${PYLON_ROOT}")

# Find Pylon Include Directory
find_path(Pylon_INCLUDE_DIRS NAMES pylon/PylonIncludes.h
          HINTS ${PYLON_ROOT}/include
          NO_DEFAULT_PATH)

# Find Pylon Libraries (using CORRECT lowercase base names)
# Prioritize the versioned names based on ls output (e.g., libpylonbase-6.2.0.so)
find_library(Pylon_BASE_LIB NAMES pylonbase-6.2.0 pylonbase # Lowercase names
             HINTS ${PYLON_ROOT}/lib
             NO_DEFAULT_PATH)
find_library(Pylon_UTILITY_LIB NAMES pylonutility-6.2.0 pylonutility # Lowercase names
             HINTS ${PYLON_ROOT}/lib
             NO_DEFAULT_PATH)
# GenApi was found correctly before, keep using its name
find_library(Pylon_GENAPI_LIB NAMES GenApi_gcc_v3_1_Basler_pylon
             HINTS ${PYLON_ROOT}/lib
             NO_DEFAULT_PATH)

# Combine found libraries into a list
set(Pylon_LIBRARIES ${Pylon_BASE_LIB} ${Pylon_UTILITY_LIB} ${Pylon_GENAPI_LIB})

# Check if everything was found
if(NOT Pylon_INCLUDE_DIRS OR NOT Pylon_BASE_LIB OR NOT Pylon_UTILITY_LIB OR NOT Pylon_GENAPI_LIB)
    message(FATAL_ERROR "Could not find Pylon includes or required libraries using find_library. "
                        "Check PYLON_ROOT, SDK installation, and library NAMES (case-sensitive!) in CMakeLists.txt. "
                        "Found Includes: '${Pylon_INCLUDE_DIRS}', Base: '${Pylon_BASE_LIB}', Util: '${Pylon_UTILITY_LIB}', GenApi: '${Pylon_GENAPI_LIB}'")
else()
    message(STATUS "Found Pylon includes: ${Pylon_INCLUDE_DIRS}")
    message(STATUS "Found Pylon libraries using find_library: ${Pylon_LIBRARIES}")
endif()
# --------------------------------------------------------

# --- Define our Python extension module ---
pybind11_add_module(core_module
    src/core_module.cpp
    ${pybind11_opencv_numpy_SOURCE_DIR}/ndarray_converter.cpp
)

# --- Link Libraries ---
target_link_libraries(core_module PRIVATE
    ${OpenCV_LIBS}
    ${Pylon_LIBRARIES}
)
# ---------------------

# --- Set Include Directories ---
target_include_directories(core_module PRIVATE
    ${pybind11_SOURCE_DIR}/include
    ${pybind11_opencv_numpy_SOURCE_DIR}
    ${Pylon_INCLUDE_DIRS}
)
# ----------------------------

# Optional: Install step
# install(TARGETS core_module LIBRARY DESTINATION .)
