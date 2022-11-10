use dirs;

use matrix_sdk::{
    config::SyncSettings,
    event_handler::Ctx,
    room::Joined,
    room::Room,
    ruma::events::room::{
        member::StrippedRoomMemberEvent,
        message::{
            MessageType, OriginalSyncRoomMessageEvent, RoomMessageEventContent,
            TextMessageEventContent,
        },
    },
    Client,
};
use tokio::{
    signal,
    time::{sleep, Duration},
};

use clap::arg;

use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

mod config;
use config::Config;

// Use Jemalloc only for musl-64 bits platforms
#[cfg(all(target_env = "musl", target_pointer_width = "64"))]
#[global_allocator]
static ALLOC: jemallocator::Jemalloc = jemallocator::Jemalloc;

/// This is the starting point of the app. `main` is called by rust binaries to
/// run the program in this case, we use tokio (a reactor) to allow us to use
/// an `async` function run.
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info".into()),
        ))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = Config::from_config_file("config.yaml");

    // Start our logic and in the same time listen for Ctrl+C
    tokio::select! {
        // our actual runner
        _ = login_and_sync(&config) => {},
        _ = signal::ctrl_c() => {println!("Shutdown received");},
    }

    Ok(())
}

// The core sync loop we have running.
async fn login_and_sync(config: &Config) -> anyhow::Result<()> {
    // First, we set up the client.

    // Figure out in which directory we are going to store our state
    let store_path = match &config.store_path {
        Some(path) => std::path::PathBuf::from(path),
        None => dirs::data_dir()
            .expect("no home directory found")
            .join("otcbot"),
    };
    println!("using {:?} for storage", store_path);
    std::fs::create_dir_all(&store_path).expect("Can't create store directory");

    let client = Client::builder()
        // We use the convenient client builder to set our custom homeserver URL on it.
        .homeserver_url(config.matrix.homeserver.clone())
        // Matrix-SDK has support for pluggable, configurable state and crypto-store
        // support we use the default sled-store (enabled by default on native
        // architectures), to configure a local cache and store for our crypto keys
        .sled_store(store_path, None)?
        .build()
        .await?;

    println!("client is {:?}", client);

    // Then let's log that client in
    client
        .login_username(
            config.matrix.username.as_str(),
            config.matrix.password.as_str(),
        )
        .initial_device_display_name("otcbot")
        .send()
        .await?;

    // It worked!
    println!("logged in as {}", config.matrix.username);

    sync_loop(client, &config).await
}

// once logged in, this is called where we configure the handlers
// and run the client
async fn sync_loop(client: Client, config: &Config) -> anyhow::Result<()> {
    // invite acceptance
    client.add_event_handler(on_stripped_state_member);
    // An initial sync to set up state and so our bot doesn't respond to old
    // messages. If the `StateStore` finds saved state in the location given the
    // initial sync will be skipped in favor of loading state from the store
    client.sync_once(SyncSettings::default()).await.unwrap();

    // our customisation:
    client.add_event_handler(on_room_message);
    client.add_event_handler_context(config.clone());

    // since we called `sync_once` before we entered our sync loop we must pass
    // that sync token to `sync`
    let settings = SyncSettings::default().token(client.sync_token().await.unwrap());

    // this keeps state from the server streaming in to the bot via the
    // EventHandler trait
    client.sync(settings).await?;

    Ok(())
}

// Whenever we see a new stripped room member event, we've asked our client to
// call this function. So what exactly are we doing then?
async fn on_stripped_state_member(
    room_member: StrippedRoomMemberEvent,
    client: Client,
    room: Room,
) {
    if room_member.state_key != client.user_id().unwrap() {
        // the invite we've seen isn't for us, but for someone else. ignore
        return;
    }

    // looks like the room is an invited room, let's attempt to join then
    if let Room::Invited(room) = room {
        // The event handlers are called before the next sync begins, but
        // methods that change the state of a room (joining, leaving a room)
        // wait for the sync to return the new room state so we need to spawn
        // a new task for them.
        tokio::spawn(async move {
            println!("Autojoining room {}", room.room_id());
            let mut delay = 2;

            while let Err(err) = room.accept_invitation().await {
                // retry autojoin due to synapse sending invites, before the
                // invited user can join for more information see
                // https://github.com/matrix-org/synapse/issues/4345
                eprintln!(
                    "Failed to join room {} ({err:?}), retrying in {delay}s",
                    room.room_id()
                );

                sleep(Duration::from_secs(delay)).await;
                delay *= 2;

                if delay > 3600 {
                    eprintln!("Can't join room {} ({err:?})", room.room_id());
                    break;
                }
            }
            println!("Successfully joined room {}", room.room_id());
        });
    }
}

fn otcbot_cmd() -> clap::Command {
    clap::Command::new("!otcbot")
        .about("An awesome OTC Bot")
        .subcommand_required(true)
        .subcommand(clap::Command::new("gm").about("Greet me"))
        .subcommand(clap::Command::new("party").about("Party time"))
        .subcommand(
            clap::Command::new("registry")
                .about("Manage Container Registry")
                .subcommand_required(true)
                .arg_required_else_help(true)
                .subcommand(
                    clap::Command::new("import")
                        .about("Import image into registry")
                        .arg(arg!(<IMAGE> "Image name"))
                        .arg(arg!(<TAG> "Image version")),
                ),
        )
}

// This fn is called whenever we see a new room message event. You notice that
// the difference between this and the other function that we've given to the
// handler lies only in their input parameters. However, that is enough for the
// rust-sdk to figure out which one to call one and only do so, when
// the parameters are available.
async fn on_room_message(
    event: OriginalSyncRoomMessageEvent,
    room: Room,
    //    encryption_info: Option<EncryptionInfo>,
    config: Ctx<Config>,
) {
    // First, we need to unpack the message: We only want messages from rooms we are
    // still in and that are regular text messages - ignoring everything else.
    if let Room::Joined(room) = room {
        let msg_body = match event.content.msgtype {
            MessageType::Text(TextMessageEventContent { body, .. }) => body,
            _ => {
                eprintln!("Bad msgtype");
                return;
            }
        };

        if msg_body.starts_with("!otcbot") {
            let words = msg_body.split(" ");
            match otcbot_cmd().try_get_matches_from(words) {
                Ok(c) => match c.subcommand() {
                    Some(("gm", _)) => {
                        room.send(
                            RoomMessageEventContent::text_plain(format!("Hey {}", event.sender)),
                            None,
                        )
                        .await
                        .unwrap();
                    }
                    Some(("party", _)) => {
                        room.send(
                            RoomMessageEventContent::text_plain("🎉🎊🥳 let's PARTY!! 🥳🎊🎉"),
                            None,
                        )
                        .await
                        .unwrap();
                    }
                    Some(("registry", sub_matches)) => {
                        otcbot_registry(&room, sub_matches, config).await.unwrap();
                    }
                    _ => {
                        unreachable!();
                    } // If all subcommands are defined above, anything else is unreachabe!()
                },
                Err(e) => match e.kind() {
                    // In case of DisplayHelp just return e.to_string
                    clap::error::ErrorKind::DisplayHelp => {
                        room.send(RoomMessageEventContent::text_plain(e.to_string()), None)
                            .await
                            .unwrap();
                    }
                    // Otherwise render long help
                    _ => {
                        room.send(
                            RoomMessageEventContent::text_plain(
                                otcbot_cmd().render_long_help().to_string(),
                            ),
                            None,
                        )
                        .await
                        .unwrap();
                    }
                },
            };
        }
        if msg_body.len() > 0 {
            // Commit message read
            room.read_receipt(&event.event_id).await.unwrap();
        }
    }
}

async fn otcbot_registry(
    room: &Joined,
    sub_matches: &clap::ArgMatches,
    config: Ctx<Config>,
) -> Result<(), ()> {
    match sub_matches.subcommand() {
        Some(("import", import_matches)) => {
            let image_key = import_matches.get_one::<String>("IMAGE").expect("required");
            let image_tag = import_matches.get_one::<String>("TAG").expect("required");
            match config.registry.images.get(image_key) {
                Some(image) => {
                    room.send(
                        RoomMessageEventContent::text_plain(format!(
                            "Got it. Importing {}:{} to {}:{} ...",
                            image.upstream, image_tag, image.downstream, image_tag
                        )),
                        None,
                    )
                    .await
                    .unwrap();
                    // Simulate typing
                    room.typing_notice(true).await.unwrap();
                    let mut log: String = String::from("```\notcbot$> skopeo");
                    let from = format!("docker://{}:{}", image.upstream, image_tag);
                    let to = format!("docker://{}:{}", image.downstream, image_tag);

                    let mut command_args = ["copy", from.as_str(), to.as_str(), "-a"];

                    log.push_str(" ");
                    log.push_str(command_args.join(" ").as_str());
                    log.push_str("\n");
                    let command_result = std::process::Command::new("/usr/local/bin/skopeo")
                        .args(command_args)
                        .output()
                        .expect("Skopeo command failed to start");

                    log.push_str("\n");
                    if command_result.status.success() {
                        log.push_str(&String::from_utf8(command_result.stdout).unwrap());
                    } else {
                        log.push_str(&String::from_utf8(command_result.stderr).unwrap());
                    }
                    log.push_str("\n```");
                    let log_msg = RoomMessageEventContent::text_markdown(log.to_string());

                    room.send(log_msg, None).await.unwrap();
                    room.typing_notice(false).await.unwrap();
                }
                None => {
                    room.send(
                        RoomMessageEventContent::text_plain(format!(
                            "Image {} is not configured",
                            image_key
                        )),
                        None,
                    )
                    .await
                    .unwrap();
                }
            }
        }

        _ => unreachable!(), // If all subcommands are defined above, anything else is unreachabe!()
    }
    Ok(())
}

#[cfg(test)]
mod test {
    // use super::*;

    #[test]
    fn test_1_cmd() {
        let cmd = super::otcbot_cmd();
        let matches = cmd.try_get_matches_from(&["!otcbot", "help", "registry"]);
    }
}
