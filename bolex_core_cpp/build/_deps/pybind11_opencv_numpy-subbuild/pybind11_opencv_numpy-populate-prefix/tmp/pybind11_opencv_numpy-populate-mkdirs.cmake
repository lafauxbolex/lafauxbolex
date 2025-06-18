# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-src"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-build"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/tmp"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/src/pybind11_opencv_numpy-populate-stamp"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/src"
  "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/src/pybind11_opencv_numpy-populate-stamp"
)

set(configSubDirs )
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/src/pybind11_opencv_numpy-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "/home/ooze3d/Downloads/bolex_core_cpp/build/_deps/pybind11_opencv_numpy-subbuild/pybind11_opencv_numpy-populate-prefix/src/pybind11_opencv_numpy-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
