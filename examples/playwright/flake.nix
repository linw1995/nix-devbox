{
  inputs = {
    utils.url = "github:numtide/flake-utils";
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

    playwright.url = "github:pietdevries94/playwright-web-flake";
  };

  outputs = {
    nixpkgs,
    utils,
    playwright,
    ...
  }:
    utils.lib.eachDefaultSystem
    (
      system: let
        playuwright-overlay = final: prev: {
          inherit (playwright.packages.${system}) playwright-test playwright-driver;
        };
        pkgs = import nixpkgs {
          inherit system;
          overlays = [
            playuwright-overlay
          ];
          config.allowUnfree = true;
        };
      in {
        devShells = {
          default = pkgs.mkShell {
            packages = with pkgs; [
              nodejs

              playwright-driver.browsers
            ];

            # the playwright version in package.json need to be the same as the one in playwright-driver
            shellHook =
              if pkgs.stdenv.isLinux
              then ''
                export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
                export PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
              ''
              else "";
          };
        };
      }
    );
}
