{
  inputs = {
    utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  };

  outputs = {
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
        devShells = {
          default = pkgs.mkShell {
            packages = with pkgs; [
              # shell
              bash

              # essential cli
              coreutils
              busybox

              # editor
              neovim

              # tools
              git

              # for terminfo
              ncurses
            ];
          };
        };
      }
    );
}
