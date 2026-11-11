# deploy

Running the server automatically.

- `install-service.sh` — installs and starts a systemd user service
  (`timetracker.service`) that runs `tt-server` from this checkout's virtual
  environment at login and restarts it on failure.

```
uv sync                       # make sure .venv exists
deploy/install-service.sh
```

Useful commands afterwards:

```
systemctl --user status timetracker
systemctl --user restart timetracker     # after pulling new code
journalctl --user -u timetracker -f      # logs
systemctl --user disable --now timetracker
```
