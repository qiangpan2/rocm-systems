# TheRock wheels ship librocprofiler-sdk.so and libamd_comgr.so without
# CMake package files. The public SDK headers are not in the wheel either.
# When the sibling rocprofiler-sdk source tree is present, import those
# libraries and generate the two headers the public API includes.

function(_rocprof_compute_rocm_roots out_var)
    set(_roots ${CMAKE_PREFIX_PATH})
    if(DEFINED ENV{ROCM_PATH} AND NOT "$ENV{ROCM_PATH}" STREQUAL "")
        list(APPEND _roots "$ENV{ROCM_PATH}")
    endif()
    find_package(Python3 COMPONENTS Interpreter QUIET)
    if(Python3_EXECUTABLE)
        execute_process(
            COMMAND "${Python3_EXECUTABLE}" -c
                    "import sysconfig; print(sysconfig.get_path('purelib'), end='')"
            OUTPUT_VARIABLE _purelib
            RESULT_VARIABLE _purelib_rc
            OUTPUT_STRIP_TRAILING_WHITESPACE
        )
        if(_purelib_rc EQUAL 0 AND NOT _purelib STREQUAL "")
            list(APPEND _roots "${_purelib}/_rocm_sdk_core")
        endif()
    endif()
    list(REMOVE_DUPLICATES _roots)
    set(${out_var} "${_roots}" PARENT_SCOPE)
endfunction()

function(_rocprof_compute_find_shared out_var roots)
    set(_found "")
    foreach(_root IN LISTS roots)
        foreach(_name IN LISTS ARGN)
            foreach(_dir IN ITEMS lib lib64)
                if(EXISTS "${_root}/${_dir}/${_name}")
                    set(_found "${_root}/${_dir}/${_name}")
                    break()
                endif()
            endforeach()
            if(NOT _found STREQUAL "")
                break()
            endif()
        endforeach()
        if(NOT _found STREQUAL "")
            break()
        endif()
    endforeach()
    set(${out_var} "${_found}" PARENT_SCOPE)
endfunction()

function(_rocprof_compute_import_therock_sdk)
    if(TARGET rocprofiler-sdk::rocprofiler-sdk AND TARGET amd_comgr)
        return()
    endif()

    _rocprof_compute_rocm_roots(_roots)
    # This file lives in src/lib/cmake. The SDK tree is a sibling project.
    set(_sdk_root
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/../../../../rocprofiler-sdk"
    )
    set(_sdk_include "${_sdk_root}/source/include")
    if(NOT EXISTS "${_sdk_include}/rocprofiler-sdk/rocprofiler.h")
        message(FATAL_ERROR
            "rocprofiler-sdk CMake package was not found, and "
            "${_sdk_include}/rocprofiler-sdk/rocprofiler.h does not exist"
        )
    endif()

    _rocprof_compute_find_shared(
        _sdk_lib
        "${_roots}"
        librocprofiler-sdk.so
        librocprofiler-sdk.so.1
    )
    _rocprof_compute_find_shared(
        _comgr_lib
        "${_roots}"
        libamd_comgr.so
        libamd_comgr.so.3
    )
    if(_sdk_lib STREQUAL "" OR _comgr_lib STREQUAL "")
        message(FATAL_ERROR
            "rocprofiler-sdk CMake package was not found, and the shared "
            "libraries were not found under: ${_roots}"
        )
    endif()

    set(_rocm_include "")
    foreach(_root IN LISTS _roots)
        if(EXISTS "${_root}/include/hsa/amd_hsa_elf.h")
            set(_rocm_include "${_root}/include")
            break()
        endif()
    endforeach()
    if(_rocm_include STREQUAL "")
        message(FATAL_ERROR
            "Found ${_sdk_lib} but no ROCm include directory with hsa/amd_hsa_elf.h"
        )
    endif()

    file(READ "${_sdk_root}/VERSION" FULL_VERSION_STRING LIMIT_COUNT 1)
    string(STRIP "${FULL_VERSION_STRING}" FULL_VERSION_STRING)
    string(REGEX REPLACE "([0-9]+)\\.([0-9]+)\\.([0-9]+).*" "\\1;\\2;\\3"
                         _ver "${FULL_VERSION_STRING}")
    list(GET _ver 0 PROJECT_VERSION_MAJOR)
    list(GET _ver 1 PROJECT_VERSION_MINOR)
    list(GET _ver 2 PROJECT_VERSION_PATCH)
    set(ROCPROFILER_SDK_GIT_DESCRIBE "therock-import")
    set(ROCPROFILER_SDK_GIT_REVISION "therock-import")
    set(HSA_RUNTIME_VERSION_MAJOR 1)
    set(HSA_RUNTIME_VERSION_MINOR 21)
    set(_gen_root "${CMAKE_BINARY_DIR}/generated")
    foreach(_hdr IN ITEMS
        rocprofiler-sdk/version.h.in
        rocprofiler-sdk/ext_version.h.in
        rocprofiler-sdk-roctx/version.h.in
        rocprofiler-sdk-rocpd/version.h.in
        rocprofiler-sdk-rocattach/version.h.in
    )
        string(REGEX REPLACE "\\.in$" "" _out "${_hdr}")
        get_filename_component(_dir "${_out}" DIRECTORY)
        file(MAKE_DIRECTORY "${_gen_root}/${_dir}")
        configure_file(
            "${_sdk_include}/${_hdr}"
            "${_gen_root}/${_out}"
            @ONLY
        )
    endforeach()

    if(NOT TARGET rocprofiler-sdk::rocprofiler-sdk)
        add_library(rocprofiler-sdk::rocprofiler-sdk SHARED IMPORTED)
        set_target_properties(rocprofiler-sdk::rocprofiler-sdk PROPERTIES
            IMPORTED_LOCATION "${_sdk_lib}"
            INTERFACE_INCLUDE_DIRECTORIES "${_gen_root};${_sdk_include};${_rocm_include}"
            INTERFACE_COMPILE_DEFINITIONS "__HIP_PLATFORM_AMD__"
        )
    endif()
    if(NOT TARGET amd_comgr)
        add_library(amd_comgr SHARED IMPORTED)
        set_target_properties(amd_comgr PROPERTIES
            IMPORTED_LOCATION "${_comgr_lib}"
            INTERFACE_INCLUDE_DIRECTORIES "${_rocm_include}"
        )
    endif()
    message(STATUS "Imported TheRock rocprofiler-sdk: ${_sdk_lib}")
    message(STATUS "Imported TheRock amd_comgr: ${_comgr_lib}")
endfunction()
