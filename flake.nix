{
  description = "Kannix - Kanban board with terminal sessions";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;

        pythonEnv = python.withPackages (
          ps: with ps; [
            fastapi
            uvicorn
            httpx
            pydantic
            jinja2
            bcrypt
            python-multipart
            pytest
            pytest-asyncio
            mypy
            ruff
          ]
        );

        src = self;

        mkCheck =
          name: script:
          pkgs.runCommand "kannix-check-${name}" { nativeBuildInputs = [ pythonEnv pkgs.ruff ]; } ''
            cp -r ${src}/* .
            chmod -R u+w .
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
            export HOME=$(mktemp -d)
            ${script}
            touch $out
          '';
      in
      {
        checks = {
          ruff-check = mkCheck "ruff-check" ''
            ruff check src/ tests/
          '';
          ruff-format = mkCheck "ruff-format" ''
            ruff format --check src/ tests/
          '';
          mypy = mkCheck "mypy" ''
            mypy --strict src/
          '';
          pytest = mkCheck "pytest" ''
            pytest -v tests/
          '';
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.ruff
            pkgs.tmux
          ];

          shellHook = ''
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
          '';
        };
      }
    );
}
