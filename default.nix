{
  config,
  lib,
  dream2nix,
  ...
}: let
  python = config.deps.python;
in {
  imports = [
    dream2nix.modules.dream2nix.python-pdm
  ];

  mkDerivation = {
    src = lib.cleanSourceWith {
      src = lib.cleanSource ./.;
      filter = name: type:
        !(builtins.any (x: x) [
          (lib.hasSuffix ".nix" name)
          (lib.hasPrefix "." (builtins.baseNameOf name))
          (lib.hasSuffix "flake.lock" name)
        ]);
    };
  };

  pdm.lockfile = ./pdm.lock;
  pdm.pyproject = ./pyproject.toml;
  pdm.editables = lib.mkForce {};

  buildPythonPackage = {
    pythonImportsCheck = [
      "nix_devbox"
    ];
  };

  overrides.pyyaml = {
    buildPythonPackage.build-system = with python.pkgs; [
      cython
    ];
  };
}
