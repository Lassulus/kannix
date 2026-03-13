{
  lib,
  python3Packages,
  tmux,
  makeWrapper,
  vendorDir ? null,
}:

python3Packages.buildPythonApplication {
  pname = "kannix";
  version = "0.1.0";
  pyproject = true;

  src = lib.cleanSource ./.;

  build-system = [ python3Packages.setuptools ];

  dependencies = with python3Packages; [
    fastapi
    uvicorn
    pydantic
    jinja2
    bcrypt
    python-multipart
    websockets
  ];

  nativeBuildInputs = [ makeWrapper ];

  postFixup = ''
    wrapProgram $out/bin/kannix \
      --prefix PATH : ${lib.makeBinPath [ tmux ]}
    ${lib.optionalString (vendorDir != null) ''
      local siteDir=$(echo $out/lib/python3*/site-packages)
      mkdir -p $siteDir/kannix/static/vendor
      cp ${vendorDir}/* $siteDir/kannix/static/vendor/
    ''}
  '';

  # Tests require network/pty
  doCheck = false;

  meta = {
    description = "Kanban board with terminal sessions";
    mainProgram = "kannix";
    license = lib.licenses.mit;
  };
}
