cmake_minimum_required(VERSION 3.19)

if(NOT DEFINED VERSION)
    execute_process(COMMAND git describe --tags --abbrev=0
        WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
        OUTPUT_VARIABLE VERSION
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if("${VERSION}" STREQUAL "")
        set(VERSION "1.0.0")
    endif()
endif()

if(NOT DEFINED GIT_REVISION)
    execute_process(COMMAND git rev-parse --short HEAD
        WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
        OUTPUT_VARIABLE GIT_REVISION
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )
    if("${GIT_REVISION}" STREQUAL "")
        set(GIT_REVISION "dev")
    endif()
endif()

string(REGEX REPLACE "^v" "" VERSION "${VERSION}")
string(REGEX MATCH "^[0-9]+(\\.[0-9]+){0,3}" _PROJECT_NUM_VERSION "${VERSION}")
if("${_PROJECT_NUM_VERSION}" STREQUAL "")
    set(_PROJECT_NUM_VERSION "1.0.0")
endif()

project(ano-shell VERSION ${_PROJECT_NUM_VERSION} LANGUAGES CXX)

include(GNUInstallDirs)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")

set(DISTRIBUTOR "Ano Shell" CACHE STRING "Distributor")
set(ENABLE_MODULES "extras;plugin;shell;shapes" CACHE STRING "Modules to build/install")
set(INSTALL_LIBDIR "${CMAKE_INSTALL_LIBDIR}/ano-shell" CACHE STRING "Library install dir")
set(INSTALL_QMLDIR "${CMAKE_INSTALL_LIBDIR}/qt6/qml" CACHE STRING "QML install dir")
set(INSTALL_QSCONFDIR "${CMAKE_INSTALL_SYSCONFDIR}/xdg/quickshell/ano-shell" CACHE STRING "Quickshell config install dir")

add_compile_options(
    -Wall -Wextra -Wpedantic -Wshadow -Wconversion
    -Wold-style-cast -Wnull-dereference -Wdouble-promotion
    -Wformat=2 -Wfloat-equal -Woverloaded-virtual
    -Wsign-conversion -Wredundant-decls -Wswitch
    -Wunreachable-code
)

if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    add_compile_options(-Wunused-lambda-capture)
endif()

if("extras" IN_LIST ENABLE_MODULES)
    add_subdirectory(extras)
endif()

if("plugin" IN_LIST ENABLE_MODULES)
    add_subdirectory(plugin)
endif()

if("shell" IN_LIST ENABLE_MODULES)
    # Compile Liquid Glass fragment shaders (.frag -> .frag.qsb) when qsb is available
    find_program(QT6_QSB NAMES qsb PATHS /usr/lib/qt6/bin /usr/bin)
    file(GLOB SHADER_FRAGS "${CMAKE_SOURCE_DIR}/shell/assets/shaders/*.frag")
    set(SHADER_QSBS "")
    if(QT6_QSB AND SHADER_FRAGS)
        foreach(frag IN LISTS SHADER_FRAGS)
            get_filename_component(fname "${frag}" NAME)
            set(qsb_out "${CMAKE_BINARY_DIR}/shaders/${fname}.qsb")
            add_custom_command(
                OUTPUT "${qsb_out}"
                COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_BINARY_DIR}/shaders"
                COMMAND "${QT6_QSB}" --qt6 -o "${qsb_out}" "${frag}"
                DEPENDS "${frag}"
                COMMENT "Compiling Qt6 shader ${fname}"
            )
            list(APPEND SHADER_QSBS "${qsb_out}")
        endforeach()
        add_custom_target(anoshell-shaders ALL DEPENDS ${SHADER_QSBS})
    endif()

    foreach(dir assets components modules services utils)
        install(DIRECTORY "shell/${dir}" DESTINATION "${INSTALL_QSCONFDIR}"
            PATTERN "__pycache__" EXCLUDE
            PATTERN "*.pyc" EXCLUDE
        )
    endforeach()

    if(SHADER_QSBS)
        install(FILES ${SHADER_QSBS} DESTINATION "${INSTALL_QSCONFDIR}/assets/shaders")
    endif()

    if(EXISTS "${CMAKE_SOURCE_DIR}/shell/assets/wrap_term_launch.sh")
        install(PROGRAMS "shell/assets/wrap_term_launch.sh" DESTINATION "${INSTALL_QSCONFDIR}/assets")
    endif()

    file(READ "${CMAKE_SOURCE_DIR}/shell/shell.qml" SHELL_QML)
    string(REPLACE "settings.watchFiles: true" "settings.watchFiles: false" SHELL_QML "${SHELL_QML}")
    file(WRITE "${CMAKE_BINARY_DIR}/qml/shell.qml" "${SHELL_QML}")
    install(FILES "${CMAKE_BINARY_DIR}/qml/shell.qml" DESTINATION "${INSTALL_QSCONFDIR}")

    install(FILES LICENSE NOTICE DESTINATION "${INSTALL_QSCONFDIR}")
endif()

if("shapes" IN_LIST ENABLE_MODULES)
    message(STATUS "Fetching AnoShell.Shapes (m3shapes) module")
    include(FetchContent)
    set(M3SHAPES_REV bdc327b29f95394a732baf3c9b19658ba23755b6)
    set(M3SHAPES_SRC "${CMAKE_BINARY_DIR}/_deps/m3shapes-${M3SHAPES_REV}")
    set(M3SHAPES_PATCHER "${CMAKE_SOURCE_DIR}/cmake/patch_m3shapes.py")
    FetchContent_Declare(
        m3shapes_external
        GIT_REPOSITORY https://github.com/soramanew/m3shapes.git
        GIT_TAG        ${M3SHAPES_REV}
        SOURCE_DIR     "${M3SHAPES_SRC}"
        PATCH_COMMAND  python3 "${M3SHAPES_PATCHER}" "${M3SHAPES_SRC}/CMakeLists.txt"
    )
    if(EXISTS "${M3SHAPES_SRC}/CMakeLists.txt")
        execute_process(
            COMMAND python3 "${M3SHAPES_PATCHER}" "${M3SHAPES_SRC}/CMakeLists.txt"
            RESULT_VARIABLE _m3shapes_patch_rc
        )
        if(NOT _m3shapes_patch_rc EQUAL 0)
            message(FATAL_ERROR "Échec du patch AnoShell.Shapes sur ${M3SHAPES_SRC}/CMakeLists.txt")
        endif()
    endif()
    FetchContent_MakeAvailable(m3shapes_external)

    if(TARGET m3shapesplugin)
        set_target_properties(m3shapesplugin PROPERTIES INSTALL_RPATH "$ORIGIN")
    endif()
endif()
