cmake_minimum_required(VERSION 3.16)
project(scibrain_geant4 LANGUAGES CXX)

find_package(Geant4 REQUIRED gdml)
include(${Geant4_USE_FILE})

add_executable(scibrain-geant4 main.cc)
target_compile_features(scibrain-geant4 PRIVATE cxx_std_17)
target_link_libraries(scibrain-geant4 PRIVATE ${Geant4_LIBRARIES})

install(TARGETS scibrain-geant4 RUNTIME DESTINATION bin)
