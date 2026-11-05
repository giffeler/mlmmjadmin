# Downstream maintenance

Repository: `giffeler/mlmmjadmin`. Development branch: `downstream/unix-sockets`.
Upstream repository: `iredmail/mlmmjadmin`. Initial upstream baseline: `9bbe04f45a2d44338dca9b48be5944f2ea300723`.

The upstream history and licensing remain intact. Keep `master` as an upstream reference and maintain application changes on the downstream branch. Do not modify bundled third-party libraries for this feature. Socket configuration does not require a database schema migration.

## Update procedure

1. Fetch both remotes and read upstream release notes, security notices, configuration changes, and database migrations. Record the exact current downstream commit and the candidate upstream commit.
2. Create a separate candidate branch/worktree from the current downstream branch. Merge the selected upstream release/commit there. Inspect changes to all connection factories and settings, including new direct database connections that might bypass the transport helper.
3. Run local regressions and the isolated MariaDB workflow on that exact candidate commit. For iRedAPD, require both SQLAlchemy compatibility jobs. Do not treat skipped live database tests as an integration pass.
4. Test the candidate in a disposable copy of the target deployment, using its relevant schemas, enabled plugins, service accounts and sandbox restrictions. Exercise the daemon/application and the maintenance commands actually used. Confirm SMTP policy behavior for iRedAPD and application operations for iRedAdmin/mlmmjadmin.
5. Review the candidate diff and upstream migrations before advancing the downstream branch. Record the tested commit and CI run URLs. Build deployment archives from that exact commit rather than an unversioned working directory.

Example branch preparation (replace `UPSTREAM_RELEASE` with a verified tag or commit):

```sh
git fetch upstream --tags
git fetch origin
git switch -c downstream/upgrade-candidate origin/downstream/unix-sockets
git merge --no-edit UPSTREAM_RELEASE
```

The `Unix socket transport` workflow supports manual dispatch on a candidate branch. Release only a candidate whose checks and staging acceptance have passed. The initial test work does not authorize or perform a production deployment.

## Deployment and rollback preparation

Before deployment, preserve the currently running application tree, configuration and ownership/modes, service definitions, and a verified database backup. Record service commands and the current MariaDB networking configuration. Use a versioned application directory and an explicit switch/restart procedure appropriate to the actual installation. Do not blindly run an upstream upgrade script: it installs upstream application code and may replace downstream changes.

Stage socket configuration across all clients while retaining the ability to return to the previous database transport. Disable TCP only after all required clients have passed acceptance. If returning to an unmodified upstream application that lacks socket support, restore its prior loopback MariaDB transport first; otherwise the old application cannot connect. Do not broaden the database bind address during rollback.

If an upstream update introduces schema changes, application-directory rollback alone may be insufficient. Follow that release's migration/restore procedure, using the captured backup and a tested restoration plan. No schema changes are introduced by the socket extension itself.

## Validation record

The GitHub Actions run attached to a commit is the evidence for that commit. Successful factory/transport tests do not certify a complete mail system. Production service-user access, OS confinement, complete application behavior and a target-specific rollback rehearsal remain required before production deployment.
