{
  description = "Kannix - Kanban board with terminal sessions";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    diff2html-css = {
      url = "https://cdn.jsdelivr.net/npm/diff2html@3.4.56/bundles/css/diff2html.min.css";
      flake = false;
    };
    diff2html-js = {
      url = "https://cdn.jsdelivr.net/npm/diff2html@3.4.56/bundles/js/diff2html-ui.min.js";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      diff2html-css,
      diff2html-js,
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

        vendorDir = pkgs.runCommand "kannix-vendor" { } ''
          mkdir -p $out
          cp ${diff2html-css} $out/diff2html.min.css
          cp ${diff2html-js} $out/diff2html-ui.min.js
        '';

        mkCheck =
          name: script:
          pkgs.runCommand "kannix-check-${name}" { nativeBuildInputs = [ pythonEnv pkgs.ruff ]; } ''
            cp -r ${src}/* .
            chmod -R u+w .
            mkdir -p src/kannix/static/vendor
            cp ${vendorDir}/* src/kannix/static/vendor/
            export PYTHONPATH="$PWD/src:$PYTHONPATH"
            export HOME=$(mktemp -d)
            ${script}
            touch $out
          '';
      in
      {
        packages.default = pkgs.callPackage ./package.nix { inherit vendorDir; };

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
            # Vendor diff2html for dev
            mkdir -p src/kannix/static/vendor
            ln -sf ${vendorDir}/diff2html.min.css src/kannix/static/vendor/diff2html.min.css
            ln -sf ${vendorDir}/diff2html-ui.min.js src/kannix/static/vendor/diff2html-ui.min.js
          '';
        
        };
      }
    );
}
