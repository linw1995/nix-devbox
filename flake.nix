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
        lib = pkgs.lib;
        git_dirty =
          if (self.sourceInfo ? rev)
          then "False"
          else "True";
        git_commit_sha =
          let
            rev = self.sourceInfo.rev or (
              if (self.sourceInfo ? dirtyRev)
              then self.sourceInfo.dirtyRev
              else "unknown"
            );
            cleanRev = lib.strings.removeSuffix "-dirty" rev;
          in
            lib.substring 0 7 cleanRev;
        gitInfo = {
          commit = git_commit_sha;
          isDirty = git_dirty;
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
              {
                mkDerivation.postPatch = ''
                  cd src/nix_devbox
                  echo "__commit_sha__ = \"${gitInfo.commit}\"" > _version.py
                  echo "__is_dirty__ = ${gitInfo.isDirty}" >> _version.py
                  cd ../..
                '';
              }
            ];
          };
        };
        devShells = {
          default = pkgs.mkShell {
            inputsFrom = [self.packages.${system}.default.devShell];

            packages = with pkgs; [
              prek
              python314
            ];
          };
        };
      }
    );
}
