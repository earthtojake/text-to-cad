{
  description = "Nix dev shell for the Emdash Electron workspace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        lib = pkgs.lib;
        packageJson = builtins.fromJSON (builtins.readFile ./package.json);
        pnpmPackageManager = packageJson.packageManager or "";
        pnpmVersionMatch = builtins.match "pnpm@([0-9]+\\.[0-9]+\\.[0-9]+)(\\+.*)?" pnpmPackageManager;
        requiredPnpmVersion =
          if pnpmVersionMatch != null then
            builtins.elemAt pnpmVersionMatch 0
          else
            throw "package.json must define packageManager as pnpm@<version> (optionally with +suffix)";
        # Nixpkgs can lag patch releases; require matching major/minor line (e.g. 10.28.x).
        requiredPnpmMajorMinor = builtins.elemAt (builtins.match "([0-9]+\\.[0-9]+)\\..*" requiredPnpmVersion) 0;
        requiredPnpmCompatVersion = "${requiredPnpmMajorMinor}.0";
        requiredPnpmMajor = builtins.elemAt (builtins.match "([0-9]+)\\..*" requiredPnpmVersion) 0;
        requiredPnpmAttr = "pnpm_" + requiredPnpmMajor;
        majorPnpm =
          if builtins.hasAttr requiredPnpmAttr pkgs then
            builtins.getAttr requiredPnpmAttr pkgs
          else
            null;
        nodejs = pkgs.nodejs_24;
        pnpmBase =
          if majorPnpm != null && lib.versionAtLeast majorPnpm.version requiredPnpmCompatVersion then
            majorPnpm
          else if pkgs ? pnpm && lib.versionAtLeast pkgs.pnpm.version requiredPnpmCompatVersion then
            pkgs.pnpm
          else
            throw "Nixpkgs pnpm is too old for this repo. Required >= ${requiredPnpmCompatVersion} (matching packageManager ${requiredPnpmVersion} major/minor), but found pnpm=${if pkgs ? pnpm then pkgs.pnpm.version else "missing"} ${requiredPnpmAttr}=${if builtins.hasAttr requiredPnpmAttr pkgs then (builtins.getAttr requiredPnpmAttr pkgs).version else "missing"}.";
        pnpm =
          if pnpmBase ? override then
            pnpmBase.override { inherit nodejs; }
          else
            pnpmBase;

        electronPackageSpec = packageJson.devDependencies.electron or (packageJson.dependencies.electron or "");
        electronVersionMatch = builtins.match "[\\^~]?([0-9]+\\.[0-9]+\\.[0-9]+).*" electronPackageSpec;
        # Electron version must match package.json. Update the fixed-output hash below
        # whenever the package.json Electron version changes.
        electronVersion =
          if electronVersionMatch != null then
            builtins.elemAt electronVersionMatch 0
          else
            throw "package.json must define electron as a semver version";

        # Pre-fetch Electron binary for Linux x64
        # electron-builder expects zips named: electron-v${version}-linux-x64.zip
        electronLinuxZip = pkgs.fetchurl {
          url = "https://github.com/electron/electron/releases/download/v${electronVersion}/electron-v${electronVersion}-linux-x64.zip";
          sha256 = "sha256-D3utkbADhMTStZ6++QRBW+lb8G7b/llfD8tX9R/RR+Q=";
        };

        # Create a directory with the electron zip for electronDist
        electronDistDir = pkgs.runCommand "electron-dist" {} ''
          mkdir -p $out
          cp ${electronLinuxZip} $out/electron-v${electronVersion}-linux-x64.zip
        '';

        sharedEnv =
          [
            nodejs
            pkgs.git
            pkgs.python3
            pkgs.pkg-config
            pkgs.openssl
            pkgs.libtool
            pkgs.autoconf
            pkgs.automake
            pkgs.coreutils
          ]
          ++ lib.optionals pkgs.stdenv.isDarwin [
            pkgs.libiconv
          ]
          ++ lib.optionals pkgs.stdenv.isLinux [
            pkgs.libsecret
            pkgs.sqlite
            pkgs.zlib
            pkgs.libutempter
            pkgs.patchelf
          ];
        cleanSrc = lib.cleanSource ./.;
        emdashPackage =
          if pkgs.stdenv.isLinux then
            pkgs.stdenv.mkDerivation rec {
              pname = "emdash";
              version = packageJson.version;
              src = cleanSrc;
              pnpmDeps =
                if pkgs ? fetchPnpmDeps then
                  pkgs.fetchPnpmDeps {
                    inherit pname version src;
                    inherit pnpm;
                    fetcherVersion = 1;
                    hash = "";
                  }
                else
                  pnpm.fetchDeps {
                    inherit pname version src;
                    fetcherVersion = 1;
                    hash = "";
                  };
              nativeBuildInputs =
                sharedEnv
                ++ [
                  pnpm
                  (pkgs.pnpmConfigHook or pnpm.configHook)
                  pkgs.dpkg
                  pkgs.rpm
                ];
              buildInputs = [
                pkgs.libsecret
                pkgs.sqlite
                pkgs.zlib
                pkgs.libutempter
              ];
              env = {
                HOME = "$TMPDIR/emdash-home";
                npm_config_build_from_source = "true";
                npm_config_manage_package_manager_versions = "false";
                # Skip Electron binary download during pnpm install
                ELECTRON_SKIP_BINARY_DOWNLOAD = "1";
              };

              buildPhase = ''
                runHook preBuild

                mkdir -p "$TMPDIR/emdash-home"
                pnpm config set manage-package-manager-versions false

                # Build the app (renderer + main)
                pnpm run build

                # Run electron-builder with electronDist override to avoid download
                # Use --dir to only produce unpacked output (no AppImage/deb which require network)
                pnpm exec electron-builder --linux --dir \
                  -c.electronDist=${electronDistDir} \
                  -c.electronVersion=${electronVersion}

                runHook postBuild
              '';

              installPhase = ''
                runHook preInstall

                # electron-builder outputs to "release" directory (configured in package.json build.directories.output)
                distDir="$PWD/release"
                unpackedDir="$distDir/linux-unpacked"

                if [ ! -d "$unpackedDir" ]; then
                  echo "Expected linux-unpacked output from electron-builder, got nothing at $unpackedDir" >&2
                  exit 1
                fi

                install -d $out/share/emdash
                cp -R "$unpackedDir" $out/share/emdash/

                if ls "$distDir"/*.AppImage >/dev/null 2>&1; then
                  for image in "$distDir"/*.AppImage; do
                    install -Dm755 "$image" "$out/share/emdash/$(basename "$image")"
                  done
                fi

                install -d $out/bin
                cat <<EOF > $out/bin/emdash
#!${pkgs.bash}/bin/bash
set -euo pipefail

APP_ROOT="$out/share/emdash/linux-unpacked"
exec "\$APP_ROOT/emdash" "\$@"
EOF
                chmod +x $out/bin/emdash

                runHook postInstall
              '';

              meta = {
                description = "Emdash – multi-agent orchestration desktop app";
                homepage = "https://github.com/amywork777/hardcore";
                license = lib.licenses.asl20;
                platforms = [ "x86_64-linux" ];
              };
            }
          else
            pkgs.writeShellScriptBin "emdash" ''
              echo "The packaged Emdash app is currently only available for Linux when using Nix." >&2
              exit 1
            '';
      in {
        devShells.default = pkgs.mkShell {
          packages = sharedEnv;

          shellHook = ''
            echo "Emdash dev shell ready"
            echo "Node: $(node --version)"
            echo "Run 'pnpm run d' for the full dev loop."
          '';
        };

        packages.emdash = emdashPackage;
        packages.default = emdashPackage;

        apps.default = {
          type = "app";
          program = "${emdashPackage}/bin/emdash";
        };
      });
}
