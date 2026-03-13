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
    {
      nixosModules.default = ./module.nix;
    }
    //
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
            websockets
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
        packages.default = pkgs.callPackage ./package.nix { };

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
            (pkgs.writeShellScriptBin "kannix-ctl" ''
              exec ${pythonEnv}/bin/python -m kannix.ctl "$@"
            '')
            (pkgs.writeShellScriptBin "kannix-dev" ''
              set -e
              export PYTHONPATH="$PWD/src:''${PYTHONPATH:-}"
              export KANNIX_CONFIG="''${KANNIX_CONFIG:-dev-config.json}"
              export KANNIX_STATE_DIR="''${KANNIX_STATE_DIR:-/tmp/kannix-dev}"
              mkdir -p "$KANNIX_STATE_DIR"

              # Seed admin user if needed
              ${pythonEnv}/bin/python -c "
              from pathlib import Path
              from kannix.auth import AuthManager
              from kannix.state import StateManager
              import os
              sd = os.environ['KANNIX_STATE_DIR']
              sm = StateManager(Path(sd) / 'state.json')
              auth = AuthManager(sm)
              try:
                  user = auth.create_user('admin', 'admin', is_admin=True)
                  print(f'Created admin user, token: {user.token}')
              except ValueError:
                  print('Admin user already exists')
              "

              echo "Starting dev server with auto-reload..."
              echo "  Config: $KANNIX_CONFIG"
              echo "  State:  $KANNIX_STATE_DIR"
              echo ""
              exec ${pythonEnv}/bin/python -m uvicorn \
                kannix.main:create_dev_app \
                --factory \
                --reload \
                --reload-dir src \
                --host 127.0.0.1 \
                --port 9876
            '')
          ];

          shellHook = ''
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
          '';
        };
      }
    );
}
