#include "G4GDMLParser.hh"
#include "G4GeneralParticleSource.hh"
#include "G4OpticalPhysics.hh"
#include "G4PhysListFactory.hh"
#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"
#include "G4VModularPhysicsList.hh"
#include "G4VUserActionInitialization.hh"
#include "G4VUserDetectorConstruction.hh"
#include "G4VUserPrimaryGeneratorAction.hh"

#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>

class GdmlDetector final : public G4VUserDetectorConstruction {
 public:
  explicit GdmlDetector(std::string path) : path_(std::move(path)) {}
  G4VPhysicalVolume* Construct() override {
    parser_.Read(path_, false);
    return parser_.GetWorldVolume();
  }

 private:
  std::string path_;
  G4GDMLParser parser_;
};

class PrimaryGenerator final : public G4VUserPrimaryGeneratorAction {
 public:
  PrimaryGenerator() : gps_(std::make_unique<G4GeneralParticleSource>()) {}
  void GeneratePrimaries(G4Event* event) override { gps_->GeneratePrimaryVertex(event); }

 private:
  std::unique_ptr<G4GeneralParticleSource> gps_;
};

class Actions final : public G4VUserActionInitialization {
 public:
  void Build() const override { SetUserAction(new PrimaryGenerator()); }
};

static std::string env_or(const char* name, const char* fallback) {
  const char* value = std::getenv(name);
  return value && *value ? std::string(value) : std::string(fallback);
}

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "Usage: scibrain-geant4 run.mac\n";
    return 2;
  }

  const auto gdml = env_or("SCIBRAIN_GEANT4_GDML", "geometry.gdml");
  const auto physics_name = env_or("SCIBRAIN_GEANT4_PHYSICS_LIST", "FTFP_BERT_EMZ");
  const bool optical = env_or("SCIBRAIN_GEANT4_ENABLE_OPTICAL", "0") == "1";

  auto run_manager = G4RunManagerFactory::CreateRunManager();
  run_manager->SetUserInitialization(new GdmlDetector(gdml));

  G4PhysListFactory factory;
  auto* physics = factory.GetReferencePhysList(physics_name);
  if (!physics) {
    std::cerr << "Unsupported Geant4 reference physics list: " << physics_name << "\n";
    delete run_manager;
    return 3;
  }
  if (optical) {
    physics->RegisterPhysics(new G4OpticalPhysics());
  }
  run_manager->SetUserInitialization(physics);
  run_manager->SetUserInitialization(new Actions());
  run_manager->Initialize();

  const auto command = G4String("/control/execute ") + G4String(argv[1]);
  const auto status = G4UImanager::GetUIpointer()->ApplyCommand(command);
  if (status != 0) {
    std::cerr << "Geant4 macro execution failed with status " << status << "\n";
    delete run_manager;
    return 4;
  }
  delete run_manager;
  return 0;
}
