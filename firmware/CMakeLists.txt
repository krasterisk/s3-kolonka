cmake_minimum_required(VERSION 3.16)

# Feeds esp_app_desc_t.version (shown in boot logs / OTA metadata).
# Keep in sync with main/app/app_version.h and firmware/BUILDNUM.
file(READ "${CMAKE_CURRENT_LIST_DIR}/VERSION" _kolonka_ver)
string(STRIP "${_kolonka_ver}" PROJECT_VER)

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(s3-kolonka)
