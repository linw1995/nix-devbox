{
  inputs = {
    utils.url = "github:numtide/flake-utils";
    dream2nix.url = "github:nix-community/dream2nix";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs = {
    self,
    dream2nix,
    nixpkgs,
    utils,
    ...
  }:
    utils.lib.eachDefaultSystem
    (
      system: let
        pkgs = import nixpkgs {
          inherit system;
        };
      in {
        packages = {
          default = dream2nix.lib.evalModules {
            packageSets.nixpkgs = pkgs;
            modules = [
              ./default.nix
              {
                paths.projectRoot = ./.;
                paths.projectRootFile = "flake.nix";
                paths.package = ./.;
              }
            ];
          };
        };
        devShells = {
          default = pkgs.mkShell {
            inputsFrom = [self.packages.${system}.default.devShell];

            packages = with pkgs; [
              python314
              prek
            ];
          };
        };
      }
    );
}
