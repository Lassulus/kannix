{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.kannix;
  kannixPkg = pkgs.callPackage ./package.nix { };

  configFile = pkgs.writeText "kannix.json" (
    builtins.toJSON {
      columns = cfg.columns;
      hooks = {
        on_create = cfg.hooks.onCreate;
        on_move = cfg.hooks.onMove;
        on_delete = cfg.hooks.onDelete;
      };
      server = {
        host = cfg.host;
        port = cfg.port;
      };
    }
  );
in
{
  options.services.kannix = {
    enable = lib.mkEnableOption "Kannix kanban board with terminal sessions";

    host = lib.mkOption {
      type = lib.types.str;
      default = "0.0.0.0";
      description = "Host to bind to.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8080;
      description = "Port to listen on.";
    };

    stateDir = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/kannix";
      description = "Directory for state file.";
    };

    columns = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "Backlog"
        "In Progress"
        "Review"
        "Done"
      ];
      description = "Kanban board column names.";
    };

    hooks = {
      onCreate = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Shell command to run when a ticket is created.";
      };

      onMove = lib.mkOption {
        type = lib.types.attrsOf lib.types.str;
        default = { };
        description = "Shell commands for column transitions. Keys are 'From->To'.";
      };

      onDelete = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Shell command to run when a ticket is deleted.";
      };
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "kannix";
      description = "User to run the service as.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "kannix";
      description = "Group to run the service as.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Whether to open the port in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isSystemUser = true;
      group = cfg.group;
      home = cfg.stateDir;
    };

    users.groups.${cfg.group} = { };

    systemd.services.kannix = {
      description = "Kannix - Kanban board with terminal sessions";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        StateDirectory = "kannix";
        WorkingDirectory = cfg.stateDir;
        ExecStart = "${kannixPkg}/bin/kannix ${configFile} ${cfg.stateDir}";
        Restart = "on-failure";
        RestartSec = 5;
      };
    };

    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}
