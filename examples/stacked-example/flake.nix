{
  description = "Stacked example - demonstrates config layering";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      devShells.${system}.default = pkgs.mkShell {
        name = "stacked-example";
        buildInputs = with pkgs; [
          bash
          coreutils
        ];
        shellHook = ''
          echo "=== Stacked Environment ==="
          echo "This shell inherits from base + opencode + local config"
          echo "Try: nix-devbox run ../base ../opencode . --dry-run"
        '';
      };
    };
}
