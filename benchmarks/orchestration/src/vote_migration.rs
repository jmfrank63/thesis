use color_eyre::Report;
use eyre::WrapErr;
use std::time::Duration;
use tracing::instrument;
use tracing_futures::Instrument;
use tsunami::providers::aws;
use tsunami::providers::Launcher;

/// vote-migration; requires only one machine
#[instrument(name = "vote_migration")]
pub(crate) async fn main() -> Result<(), Report> {
    let mut aws = crate::launcher();
    // shouldn't take _that_ long
    aws.set_max_instance_duration(1);

    // try to ensure we do AWS cleanup
    let result: Result<(), Report> = try {
        tracing::info!("spinning up aws instances");
        aws.spawn(
            vec![(
                String::from("host"),
                aws::Setup::default()
                    .instance_type("r5n.4xlarge")
                    .ami(crate::AMI, "ubuntu")
                    .setup(crate::noria_setup("noria-applications", "vote-migration")),
            )],
            Some(Duration::from_secs(2 * 60)),
        )
        .await
        .wrap_err("failed to start instances")?;

        tracing::debug!("connecting");
        let vms = aws.connect_all().await?;
        let host = vms.get("host").unwrap();
        let ssh = host.ssh.as_ref().unwrap();
        tracing::debug!("connected");

        tracing::info!("running benchmark");
        tracing::trace!("launching remote process");
        let _ = crate::output_on_success(
            crate::noria_bin(ssh, "noria-applications", "vote-migration")
                .arg("--migrate=90")
                .arg("--runtime=180")
                .arg("--do-it-all")
                .arg("--articles=2000000")
                .stdout(std::process::Stdio::null()),
        )
        .await?;

        tracing::info!("benchmark completed successfully");

        // copy out all the log files
        let files = ssh
            .command("ls")
            .raw_arg("vote-*.log")
            .output()
            .await
            .wrap_err("ls vote-*.log")?;
        if files.status.success() {
            let mut sftp = ssh.sftp();
            let mut nfiles = 0;
            tracing::debug!("downloading log files");
            for file in std::io::BufRead::lines(&*files.stdout) {
                let file = file.expect("reading from Vec<u8> cannot fail");
                let file_span = tracing::trace_span!("file", file = &*file);
                async {
                    tracing::trace!("downloading");
                    let mut remote = sftp
                        .read_from(&file)
                        .in_current_span()
                        .await
                        .wrap_err("open remote file")?;
                    let mut local = tokio::fs::File::create(&file)
                        .in_current_span()
                        .await
                        .wrap_err("create local file")?;
                    tokio::io::copy(&mut remote, &mut local)
                        .in_current_span()
                        .await
                        .wrap_err("copy remote to local")?;

                    nfiles += 1;
                    Ok::<_, Report>(())
                }
                .instrument(file_span)
                .await?;
            }
            tracing::debug!(n = nfiles, "log files downloaded");
        }

        tracing::debug!("cleaning up");
        tracing::trace!("cleaning up ssh connections");
        for (name, host) in vms {
            let host_span = tracing::trace_span!("ssh_close", name = &*name);
            let ssh = host.ssh.expect("ssh connection to host disappeared");
            async {
                tracing::trace!("closing connection");
                if let Err(e) = ssh.close().await {
                    tracing::warn!("ssh connection failed: {}", e);
                }
            }
            .instrument(host_span)
            .await
        }
    };

    tracing::trace!("cleaning up instances");
    let cleanup = aws.terminate_all().await;
    tracing::debug!("done");
    let result = result?;
    let _ = cleanup.wrap_err("cleanup failed")?;
    Ok(result)
}
