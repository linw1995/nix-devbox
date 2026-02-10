{
  inputs = {
    utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    llm-agents.url = "github:numtide/llm-agents.nix";
  };

  outputs = {
    nixpkgs,
    utils,
    llm-agents,
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
            packages = with llm-agents.packages.${system}; [opencode];
          };
        };
      }
    );
}
