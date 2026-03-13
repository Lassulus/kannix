{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.kannix;
  kannixPkg = cfg.package;

  configFile = pkgs.writeText "kannix.json" (
    builtins.toJSON (
      {
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
      // lib.optionalAttrs (cfg.reposDir != null) {
        repos_dir = cfg.reposDir;
      }
      // lib.optionalAttrs (cfg.worktreeDir != null) {
        worktree_dir = cfg.worktreeDir;
      }
    )
  );
in
{
  options.services.kannix = {
    enable = lib.mkEnableOption "Kannix kanban board with terminal sessions";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The kannix package to use.";
    };

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

    reposDir = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Directory for bare git repo clones. Enables git integration when set with worktreeDir.";
    };

    worktreeDir = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Directory for git worktrees. Enables git integration when set with reposDir.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Whether to open the port in the firewall.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users.${cfg.user} = {
      isNormalUser = true;
      home = cfg.stateDir;
      createHome = true;
      group = cfg.group;
      shell = pkgs.bashInteractive;
    };

    users.groups.${cfg.group} = { };

    systemd.services.kannix = {
      description = "Kannix - Kanban board with terminal sessions";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      path = [
        pkgs.tmux
        pkgs.git
      ];

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
